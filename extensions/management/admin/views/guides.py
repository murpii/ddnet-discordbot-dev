import logging
import re

import discord

from utils.containers import INFO_ACCENT, NoticeView, OptionSelect
from extensions.guides.store import (
    DEFAULT_LANG,
    LANGUAGES,
    STYLES,
    delete_guide,
    get_guide,
    load_guides,
    upsert_guide,
)
from extensions.guides.render import marker_errors, render_guide
from constants import URLs

log = logging.getLogger()

NAME_RE = re.compile(r"^[a-z0-9_-]+$")


def marker_error(text: str, known_names) -> str | None:
    """Combined error message for bad [btn:]/[link:] markers, or None if OK"""
    errors = marker_errors(text, known_names)
    return "\n".join(errors) if errors else None


def guide_options() -> list:
    """SelectOptions for every known guide (capped at 25, Discord's limit)."""
    options = [
        discord.SelectOption(label=name, description=f"{guide.get('style', 'guide')} style")
        for name, guide in list(load_guides().items())[:25]
    ]
    return options or [discord.SelectOption(label="(no guides yet)", value="")]


def lang_options(default: str = DEFAULT_LANG) -> list:
    return [discord.SelectOption(label=lang, value=lang, default=(lang == default)) for lang in LANGUAGES]


GUIDE_STYLE_CHOICES = [
    ("Embed with Logo", "guide", "Container with the bot logo"),
    ("Embed without Logo", "notice", "Container, no logo"),
    ("Plain Text", "plain", "Just text, no embed"),
]


def style_options(default: str | None = None) -> list:
    return [
        discord.SelectOption(label=label, value=value, description=desc, default=(value == default))
        for label, value, desc in GUIDE_STYLE_CHOICES
    ]


def helper_cog(interaction: discord.Interaction):
    return interaction.client.get_cog("Help Commands")


class EditGuideModal(discord.ui.Modal):
    aliases = discord.ui.Label(
        text="Aliases, comma separated (optional)",
        description="Guide-wide. Lowercase letters, digits, _ or -",
        component=discord.ui.TextInput(required=False, max_length=200),
    )
    style = discord.ui.Label(
        text="Style (guide-wide)",
        component=discord.ui.Select(
            min_values=1,
            max_values=1,
            options=style_options(),
        ),
    )
    text = discord.ui.Label(
        text="Guide text -- Discord markdown",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=4000,
        ),
    )

    def __init__(self, name: str, lang: str, bot):
        super().__init__(timeout=600, title=f"Edit {name} [{lang}]"[:45])
        self.name = name
        self.lang = lang
        self.bot = bot
        guide = get_guide(name) or {}
        # prefill with the actual text for THIS language (empty if not written yet)
        self.text.component.default = guide.get("text", {}).get(lang, "")
        # prefill aliases + style with whts currently stored for the guide
        self.aliases.component.default = ", ".join(guide.get("aliases", []))
        current_style = guide.get("style", "guide")
        for option in self.style.component.options:
            option.default = (option.value == current_style)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_aliases = [a.strip().lower() for a in self.aliases.component.value.split(",") if a.strip()]
        new_style = self.style.component.values[0]

        if error := marker_error(self.text.component.value, set(load_guides())):
            await interaction.response.send_message(view=NoticeView(error), ephemeral=True)
            return

        if alias_error := self.validate_aliases(new_aliases):
            await interaction.response.send_message(view=NoticeView(alias_error), ephemeral=True)
            return

        old_aliases = (get_guide(self.name) or {}).get("aliases", [])
        upsert_guide(
            self.name,
            new_aliases,
            new_style if new_style in STYLES else "guide",
            self.lang,
            self.text.component.value,
        )

        note = f"Saved `{self.name}` [{self.lang}]."
        if sorted(new_aliases) != sorted(old_aliases):
            if cog := helper_cog(interaction):
                cog.unregister_guide(self.name)
                if not cog.register_guide(self.name):
                    note += " (Aliases saved, but the live command could not be re-registered. Check the logs.)"

        log.info("AdminHub: %s edited guide %r [%s]", interaction.user, self.name, self.lang)
        await interaction.response.send_message(view=NoticeView(note), ephemeral=True)

    def validate_aliases(self, aliases: list) -> str | None:
        if self.name in aliases:
            return f"`{self.name}` is the command name; it can't also be an alias."
        # the guide's own command owns its current aliases, so don't flag those as collisions
        own = self.bot.get_command(self.name)
        for token in aliases:
            if not NAME_RE.match(token):
                return f"Invalid alias `{token}`. Use only lowercase letters, digits, `_` or `-`."
            cmd = self.bot.get_command(token)
            if cmd is not None and cmd is not own:
                return f"`{token}` is already a registered command. Pick another alias."
        return None


class PreviewGuideButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Preview", style=discord.ButtonStyle.secondary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.view.command
        if not name:
            await interaction.response.send_message(view=NoticeView("Pick a command first."), ephemeral=True)
            return
        # fallback=False: preview the text actually written for THIS language.
        # if it isn't translated yet, say so instead of showing the English text
        result = render_guide(name, self.view.language, fallback=False)
        if result is None:
            await interaction.response.send_message(
                view=NoticeView(f"There is no `{self.view.language}` translation for `{name}` yet."),
                ephemeral=True,
            )
            return
        view, files = result
        kwargs = {"view": view, "ephemeral": True}
        if files:
            kwargs["files"] = files
        await interaction.response.send_message(**kwargs)


class EditGuideButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.view.command
        if not name:
            await interaction.response.send_message(view=NoticeView("Pick a command first."), ephemeral=True)
            return
        await interaction.response.send_modal(EditGuideModal(name, self.view.language, interaction.client))


class GuideEditView(discord.ui.LayoutView):
    """Pick a command + language, then preview or edit that language text"""

    def __init__(self):
        super().__init__(timeout=300)
        self.command = None
        self.language = DEFAULT_LANG
        # TODO: Make this look better. It's ugly as hell right now.
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "# Edit a guide\n"
                    "Pick a command and a language, then **Preview** the result or "
                    "**Edit** that language's text. Edits apply instantly.\n"
                    "-# Aliases and style are guide-wide. The text box is for the picked language.\n"
                    "## Formatting you can use in the text\n"
                    "**Style**:\n"
                    "You can use the usual markdown discord supports.\n\n"
                    "**Mentions**:\n"
                    "You can link to channels/users/roles, by using the constants at the link below.\n\n"
                    "Examples (Pythonic):\n"
                    "`<#{Channels.WELCOME}>` OR `<@&{Roles.Moderator}>`\n"
                    "Alternatively use IDs directly:\n"
                    "`<#CHAN_ID>` OR `<@USER_ID>` OR `<@&ROLE_ID>`"
                ),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="DDNet IDs",
                        url=URLs.CONSTANTS_URL,
                        style=discord.ButtonStyle.link,  # noqa
                    ),
                ),
                discord.ui.TextDisplay(
                    "**Guide buttons**:\n"
                    "`[btn:other_guide:Label]` adds a button that opens another guide (it must exist).\n\n"
                    "**Link buttons**:\n"
                    "`[link:https://example.com:Label]` adds a button that opens a URL."
                ),
                discord.ui.ActionRow(OptionSelect("Pick a command", "command", guide_options())),
                discord.ui.ActionRow(OptionSelect("Pick a language", "language", lang_options())),
                discord.ui.ActionRow(PreviewGuideButton(), EditGuideButton()),
                accent_colour=INFO_ACCENT,
            )
        )


class GuideAddModal(discord.ui.Modal, title="Add a guide"):
    name = discord.ui.Label(
        text="Command name",
        description="Lowercase letters, digits, _ or -",
        component=discord.ui.TextInput(max_length=32),
    )
    aliases = discord.ui.Label(
        text="Aliases, comma separated (optional)",
        component=discord.ui.TextInput(required=False, max_length=200),
    )
    style = discord.ui.Label(
        text="Style",
        component=discord.ui.Select(
            min_values=1,
            max_values=1,
            options=style_options(default="guide"),
        ),
    )
    text = discord.ui.Label(
        text="English text | Discord markdown available",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=4000,
        ),
    )
    attachment = discord.ui.Label(
        text="Attachment (optional)",
        description="File path under data/ (Needs to be added manually)",
        component=discord.ui.TextInput(required=False, max_length=200, placeholder="e.g. deepfly.txt"),
    )

    def __init__(self, bot):
        super().__init__(timeout=600)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.component.value.strip().lower()
        aliases = [a.strip().lower() for a in self.aliases.component.value.split(",") if a.strip()]
        style = self.style.component.values[0]
        attachment = self.attachment.component.value.strip() or None

        if error := self.validate(name, aliases):
            await interaction.response.send_message(view=NoticeView(error), ephemeral=True)
            return

        if marker_err := marker_error(
                self.text.component.value, set(load_guides()) | {name}
        ):
            await interaction.response.send_message(view=NoticeView(marker_err), ephemeral=True)
            return

        upsert_guide(
            name, aliases, style if style in STYLES else "guide",
            DEFAULT_LANG, self.text.component.value, attachment=attachment,
        )

        cog = helper_cog(interaction)
        registered = cog.register_guide(name) if cog else False
        log.info("AdminHub: %s added guide %r (registered=%s)", interaction.user, name, registered)

        note = f"Added guide `{name}`."
        if not registered:
            note += " (Saved, but the live command could not be registered -- check the logs.)"
        await interaction.response.send_message(view=NoticeView(note), ephemeral=True)

    def validate(self, name: str, aliases: list) -> str | None:
        if not NAME_RE.match(name):
            return "Invalid name. Use only lowercase letters, digits, `_` or `-`."
        if name in load_guides():
            return f"A guide named `{name}` already exists."
        return next(
            (
                f"`{token}` is already a registered command. Pick another name/alias."
                for token in [name, *aliases]
                if self.bot.get_command(token) is not None
            ),
            None,
        )


class DeleteGuideButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Delete", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.view.command
        if not name:
            await interaction.response.send_message(view=NoticeView("Pick a command first."), ephemeral=True)
            return

        if cog := self.bot.get_cog("Help Commands"):
            cog.unregister_guide(name)
        removed = delete_guide(name)
        log.info("AdminHub: %s deleted guide %r (existed=%s)", interaction.user, name, removed)
        message = f"Deleted guide `{name}`." if removed else f"No guide named `{name}`."
        await interaction.response.send_message(view=NoticeView(message), ephemeral=True)


class GuideDeleteView(discord.ui.LayoutView):
    """Pick a command, then remove it"""

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        self.command = None

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Delete a guide\n"
                    "Removes the entry from `data/config/guides.json` and unregisters its "
                    "`$`-command immediately."
                ),
                discord.ui.ActionRow(OptionSelect("Pick a command", "command", guide_options())),
                discord.ui.ActionRow(DeleteGuideButton(bot)),
                accent_colour=INFO_ACCENT,
            )
        )


class _MenuEditButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=GuideEditView(), ephemeral=True)


class _MenuAddButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Add", style=discord.ButtonStyle.success)  # noqa
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(GuideAddModal(self.bot))


class _MenuDeleteButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Delete", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=GuideDeleteView(self.bot), ephemeral=True)


class GuidesMenuView(discord.ui.LayoutView):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Manage guides\n"
                    "Edit a guide's text per language, add a new `$`-command, or remove one."
                ),
                discord.ui.ActionRow(_MenuEditButton(), _MenuAddButton(bot), _MenuDeleteButton(bot)),
                accent_colour=INFO_ACCENT,
            )
        )
