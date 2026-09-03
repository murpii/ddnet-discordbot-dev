import logging
from typing import TYPE_CHECKING

import discord

from extensions.management.admin.templates import (
    load_manifest,
    read_section,
    render,
    save_section,
    section_names,
    send_template,
)
from utils.containers import INFO_ACCENT, NoticeView, OptionSelect, markup_kwargs

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()


class EditSectionModal(discord.ui.Modal):
    text = discord.ui.Label(
        text="Section text -- Discord markdown",
        description="Wrap a block in [embed] ... [/embed] lines to render it inside a container.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=2000,
        ),
    )

    def __init__(self, section: str):
        super().__init__(timeout=600, title=f"Edit {section}"[:45])
        self.section = section
        self.text.component.default = read_section(section)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        save_section(self.section, self.text.component.value)
        log.info("AdminHub: %s edited template section %r", interaction.user, self.section)
        await interaction.response.send_message(
            view=NoticeView(
                f"Saved `{self.section}`. Use Rebuild Channel to apply it."
            ),
            ephemeral=True,
        )


class PreviewSectionButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Preview", style=discord.ButtonStyle.secondary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        section = self.view.section
        if section is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a section first."), ephemeral=True
            )
            return
        # rendered exactly like send_template() sends it
        await interaction.response.send_message(
            **markup_kwargs(render(read_section(section))),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )


class EditSectionButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        section = self.view.section
        if section is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a section first."), ephemeral=True
            )
            return
        await interaction.response.send_modal(EditSectionModal(section))


class TemplateEditView(discord.ui.LayoutView):
    """Ephemeral editor entry. Pick a section, then preview or edit it"""

    def __init__(self):
        super().__init__(timeout=300)
        self.section = None

        options = []
        for section, template in section_names():
            if section in [option.label for option in options]:
                continue
            options.append(
                discord.SelectOption(label=section, description=f"part of '{template}'")
            )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Edit template text\n"
                    "Pick a section, then preview the rendered text or open "
                    "the editor. Placeholders like `{Channels.WELCOME}` are "
                    "replaced with the real IDs when the channel is rebuilt.\n"
                    "Wrap a block in `[embed]` / `[/embed]` lines to render it "
                    "inside a container, `[embed:#RRGGBB]` sets the accent colour."
                ),
                discord.ui.ActionRow(OptionSelect("Pick a section", "section", options)),
                discord.ui.ActionRow(PreviewSectionButton(), EditSectionButton()),
                accent_colour=INFO_ACCENT,
            )
        )


class RebuildChannelButton(discord.ui.Button):
    def __init__(self, bot: "DDNet"):
        super().__init__(label="Purge & Rebuild", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        template = self.view.template
        if template is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a template first."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await send_template(self.bot, template)
        except discord.HTTPException as error:
            result = f"Rebuild of '{template}' failed: {error}"
        log.info("AdminHub: %s rebuilt template %r -- %s", interaction.user, template, result)
        await interaction.edit_original_response(view=NoticeView(result))


class TemplateRebuildView(discord.ui.LayoutView):
    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot
        self.template = None

        options = [
            discord.SelectOption(label=name, description=f"fills Channels.{template['channel']}")
            for name, template in load_manifest().items()
        ]
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Rebuild a template channel\n"
                    "**This purges the channel** and re-sends all of the "
                    "template's messages."
                ),
                discord.ui.ActionRow(OptionSelect("Pick a template", "template", options)),
                discord.ui.ActionRow(RebuildChannelButton(bot)),
                accent_colour=INFO_ACCENT,
            )
        )
