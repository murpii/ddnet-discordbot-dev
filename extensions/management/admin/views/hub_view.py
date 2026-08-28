import contextlib
import datetime
import logging
import os

import discord
import psutil
from discord.ext import commands

from constants import Channels, Guilds, Roles
from utils.containers import INFO_ACCENT, separator, NoticeView, paged_pairs_view
from utils.text import to_discord_timestamp
from extensions.management.hub import HubButton, staff_guard
from extensions.management.admin.rename import process_rename, RenameButtons
from extensions.management.admin.views.extension_picker import ExtensionSelectView
from extensions.management.admin.views.templates import TemplateEditView, TemplateRebuildView
from extensions.management.admin.views.guides import GuidesMenuView

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()


def mod_hub_link() -> str:
    """Channel link to the moderation hub, or a plain description while
    Channels.MOD_HUB is not configured."""
    if Channels.MOD_HUB:
        return f"<#{Channels.MOD_HUB}>"
    return "the moderation hub channel"


class ActivityModal(discord.ui.Modal, title="Change bot activity"):
    kind = discord.ui.Label(
        text="Activity type",
        component=discord.ui.Select(
            placeholder="Select an activity type",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Listening", value="listening"),
                discord.SelectOption(label="Playing", value="playing"),
                discord.SelectOption(label="Watching", value="watching"),
            ],
            required=True,
        ),
    )
    text = discord.ui.Label(
        text="Activity text",
        component=discord.ui.TextInput(max_length=100),
    )

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        kind = self.kind.component.values[0]
        what = self.text.component.value

        if kind == "playing":
            activity = discord.Game(name=what)
        else:
            activity_type = (
                discord.ActivityType.listening if kind == "listening"
                else discord.ActivityType.watching
            )
            activity = discord.Activity(type=activity_type, name=what)

        await self.bot.change_presence(activity=activity)
        log.info("AdminHub: %s set activity to %s: %s", interaction.user, kind, what)
        await interaction.response.send_message(
            view=NoticeView(f"Activity changed to {kind}: {what}"), ephemeral=True
        )


class ShutdownConfirmView(discord.ui.LayoutView):
    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=60)
        self.bot = bot
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "**Shut down the bot?**\nIt will stay offline until restarted from the host."
                ),
                discord.ui.ActionRow(ConfirmShutdownButton(bot), CancelShutdownButton()),
                accent_colour=INFO_ACCENT,
            )
        )


class ConfirmShutdownButton(discord.ui.Button):
    def __init__(self, bot: "DDNet"):
        super().__init__(label="Shut down", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        log.info("AdminHub: shutdown confirmed by %s", interaction.user)
        await interaction.response.edit_message(view=NoticeView("Shutting down. Bye!"))
        await self.bot.close()


class CancelShutdownButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=NoticeView("Shutdown cancelled."))


class RenameModal(discord.ui.Modal, title="Rename a player"):
    old_name = discord.ui.Label(
        text="Old name",
        component=discord.ui.TextInput(max_length=64),
    )
    new_name = discord.ui.Label(
        text="New name",
        component=discord.ui.TextInput(max_length=64),
    )

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        old_name = self.old_name.component.value.strip()
        new_name = self.new_name.component.value.strip()

        # We can't rename people where both names have team ranks in common
        failsafe_query = """
                         SELECT TRUE
                         FROM record_teamrace
                         WHERE Name = %s
                           AND ID IN (SELECT ID FROM record_teamrace WHERE Name = %s)
                         LIMIT 1; \
                         """
        if await self.bot.fetch(failsafe_query, old_name, new_name):
            await interaction.response.send_message(
                view=NoticeView("Old Name and New Name have team ranks in common, unable to rename."),
                ephemeral=True,
            )
            return

        # Renames normally require 3k+ points, ask for confirmation below that.
        points_query = """
                       SELECT TRUE
                       FROM record_points
                       WHERE Name = %s
                         AND Points > 3000
                       LIMIT 1; \
                       """
        if not await self.bot.fetch(points_query, old_name):
            await interaction.response.send_message(
                content="**Old name has less than 3000 points, continue?**",
                view=RenameButtons(self.bot, old_name, new_name),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await process_rename(self.bot, interaction, old_name, new_name)


class AutoResponseAddModal(discord.ui.Modal, title="Add an auto-response"):
    trigger = discord.ui.Label(
        text="Trigger(s) -- separate several with comma+space",
        component=discord.ui.TextInput(max_length=100),
    )
    response = discord.ui.Label(
        text="Response(s) -- comma+space picks one at random",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=500,
        ),
    )

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        trigger = self.trigger.component.value.strip()
        response = self.response.component.value.strip()

        cog = interaction.client.get_cog("AutoResponses")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("Auto-responses are not loaded."), ephemeral=True
            )
            return

        ok, message = await cog.add_response(trigger, response)
        if ok:
            log.info("AdminHub: %s added auto-response %r", interaction.user, trigger)
        await interaction.response.send_message(view=NoticeView(message), ephemeral=True)


class AutoResponseRemoveModal(discord.ui.Modal, title="Remove an auto-response"):
    trigger = discord.ui.Label(
        text="Exact trigger of the entry to remove",
        component=discord.ui.TextInput(max_length=100),
    )

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        trigger = self.trigger.component.value.strip()

        cog = interaction.client.get_cog("AutoResponses")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("Auto-responses are not loaded."), ephemeral=True
            )
            return

        ok, message = await cog.remove_response(trigger)
        if ok:
            log.info("AdminHub: %s removed auto-response %r", interaction.user, trigger)
        await interaction.response.send_message(view=NoticeView(message), ephemeral=True)


class BotStatusButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(
            bot, label="Bot Status", custom_id="AdminHub:status",
            style=discord.ButtonStyle.primary,  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        process = psutil.Process(os.getpid())
        memory = process.memory_full_info().uss / 1024 ** 2
        started = datetime.datetime.fromtimestamp(process.create_time(), tz=datetime.timezone.utc)

        blacklist_cog = self.bot.get_cog("Blacklist")
        tickets = getattr(getattr(self.bot, "ticket_manager", None), "tickets", {})
        players = getattr(getattr(self.bot, "pfm", None), "players", [])

        lines = [
            "## Bot status",
            f"Latency: {round(self.bot.latency * 1000)} ms",
            f"Memory: {memory:.1f} MiB",
            f"Started: {to_discord_timestamp(started, 'R')}",
            f"Extensions loaded: {len(self.bot.extensions)}",
            f"Open tickets: {len(tickets)}",
            f"Tracked playerfinder players: {len(players)}",
        ]
        if blacklist_cog is not None:
            lines.append(f"Blacklisted words: {len(blacklist_cog.words)}")

        await interaction.response.send_message(view=NoticeView("\n".join(lines)), ephemeral=True)


class ActivityButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Change Activity", custom_id="AdminHub:activity")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ActivityModal(self.bot))


class ClearCacheButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Clear Cache", custom_id="AdminHub:cache")

    async def run(self, interaction: discord.Interaction) -> None:
        # automod's requests-cache sqlite (data/cache/)
        from extensions.management.moderator.automod import session
        session.cache.clear()
        log.info("AdminHub: %s cleared the sqlite cache", interaction.user)
        await interaction.response.send_message(
            view=NoticeView("Cleared the sqlite request cache."), ephemeral=True
        )


class ExtensionActionButton(HubButton):
    """Opens the extension picker"""

    def __init__(self, bot: "DDNet", action: str):
        self.action = action  # "load" | "unload" | "reload"
        super().__init__(bot, label=action.capitalize(), custom_id=f"AdminHub:ext-{action}")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Select an extension to {self.action}:",
            view=ExtensionSelectView(self.bot, self.action),
            ephemeral=True,
        )


class SyncCommandsButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Sync Commands", custom_id="AdminHub:sync")

    async def run(self, interaction: discord.Interaction) -> None:
        # slash sync is heavily rate-limited, this stays manual on purpose
        await interaction.response.defer(ephemeral=True, thinking=True)
        synced_global = await self.bot.tree.sync()
        synced_guild = await self.bot.tree.sync(guild=discord.Object(Guilds.DDNET))
        log.info("AdminHub: %s synced slash commands", interaction.user)
        await interaction.edit_original_response(
            view=NoticeView(
                f"Slash commands synced. Global: {len(synced_global)}, guild: {len(synced_guild)}"
            )
        )


class ShutdownButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(
            bot, label="Shutdown", custom_id="AdminHub:shutdown",
            style=discord.ButtonStyle.danger,  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=ShutdownConfirmView(self.bot), ephemeral=True)


class RenameButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(
            bot, label="Rename Player", custom_id="AdminHub:rename",
            style=discord.ButtonStyle.primary,  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RenameModal(self.bot))


class AutoResponseListButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Show list", custom_id="AdminHub:ar-list")

    async def run(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("AutoResponses")
        pairs = cog.pairs() if cog else []
        await interaction.response.send_message(
            view=paged_pairs_view(
                "Auto-responses", pairs,
                empty_note="No auto-responses configured.",
            ),
            ephemeral=True,
        )


class AutoResponseAddButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Add", custom_id="AdminHub:ar-add")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AutoResponseAddModal(self.bot))


class AutoResponseRemoveButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Remove", custom_id="AdminHub:ar-remove")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AutoResponseRemoveModal(self.bot))


class TemplateEditButton(HubButton):
    """Opens the section picker"""

    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Edit Text", custom_id="AdminHub:tpl-edit")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=TemplateEditView(), ephemeral=True)


class TemplateRebuildButton(HubButton):
    """Opens the rebuild flow"""

    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Rebuild Channel", custom_id="AdminHub:tpl-rebuild")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=TemplateRebuildView(self.bot), ephemeral=True)


class ManageGuidesButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Manage Guides", custom_id="AdminHub:guides")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=GuidesMenuView(), ephemeral=True)


class ImportBansButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Import Bans", custom_id="AdminHub:import-bans")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.bot.moddb.import_existing_bans(interaction.guild)
        except ValueError as error:
            result = str(error)
        log.info("AdminHub: %s ran import bans -- %s", interaction.user, result)
        await interaction.edit_original_response(view=NoticeView(result))


class ReloadBlacklistButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Reload Blacklist", custom_id="AdminHub:bl-reload")

    async def run(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("Blacklist")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The blacklist is not loaded."), ephemeral=True
            )
            return
        await cog.load_words()
        await interaction.response.send_message(
            view=NoticeView(f"Blacklist reloaded from the database: {len(cog.words)} words."),
            ephemeral=True,
        )


class NeglectedReportsModal(discord.ui.Modal, title="Close neglected reports"):
    hours = discord.ui.Label(
        text="Close Report tickets older than (hours)",
        component=discord.ui.TextInput(placeholder="e.g. 48", max_length=5),
    )

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.hours.component.value.strip()
        if not raw.isdigit() or int(raw) <= 0:
            await interaction.response.send_message(
                view=NoticeView("Please enter a whole number of hours greater than 0."),
                ephemeral=True,
            )
            return

        hours = int(raw)
        tickets = self.bot.ticket_manager.neglected_report_tickets(hours)
        if not tickets:
            await interaction.response.send_message(
                view=NoticeView(f"No open Report tickets are older than {hours} hours."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            view=ConfirmCloseNeglectedView(self.bot, hours, len(tickets)), ephemeral=True
        )


class ConfirmCloseNeglectedButton(discord.ui.Button):
    def __init__(self, bot: "DDNet", hours: int):
        super().__init__(label="Close them", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot
        self.hours = hours

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        manager = self.bot.ticket_manager
        # recompute the set now, it may have shifted since the modal was shown
        tickets = manager.neglected_report_tickets(self.hours)
        closed, failed = await manager.bulk_close_neglected(tickets, closer=interaction.user)
        log.info(
            "AdminHub: %s bulk-closed %d neglected report(s) (%d failed, older than %dh)",
            interaction.user, closed, failed, self.hours,
        )
        summary = f"Closed {closed} neglected Report ticket(s)."
        if failed:
            summary += f" {failed} could not be closed, check the logs."
        with contextlib.suppress(discord.NotFound):
            await interaction.edit_original_response(view=NoticeView(summary))


class CancelCloseNeglectedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=NoticeView("Cancelled. No tickets were closed.")
        )


class ConfirmCloseNeglectedView(discord.ui.LayoutView):
    def __init__(self, bot: "DDNet", hours: int, count: int):
        super().__init__(timeout=120)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Close {count} neglected Report ticket(s)?**\n"
                    f"This closes every open Report ticket older than {hours} hours and DMs each "
                    f"creator the neglect apology. This cannot be undone."
                ),
                discord.ui.ActionRow(
                    ConfirmCloseNeglectedButton(bot, hours), CancelCloseNeglectedButton()
                ),
                accent_colour=INFO_ACCENT,
            )
        )


class CloseNeglectedReportsButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Close Neglected Reports", custom_id="AdminHub:close-neglected")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(NeglectedReportsModal(self.bot))


class TicketCleanupButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(bot, label="Ticket DB Cleanup", custom_id="AdminHub:ticket-cleanup")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.ticket_manager.cleanup_database()
        log.info("AdminHub: %s ran the ticket DB cleanup", interaction.user)
        await interaction.edit_original_response(view=NoticeView(result))


class AdminHubView(discord.ui.LayoutView):
    """The persistent admin hub message and buttons are admin gated"""

    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("# Admin Commands Hub"),
                separator(),
                discord.ui.TextDisplay(
                    "## Bot management\n"
                    "Status, presence, cache, and shutdown."
                ),
                discord.ui.ActionRow(
                    BotStatusButton(bot), ActivityButton(bot),
                    ClearCacheButton(bot), ShutdownButton(bot),
                ),
                discord.ui.TextDisplay(
                    "### Extensions\n"
                    "Load, unload or reload one of the bot's extensions."
                ),
                discord.ui.ActionRow(
                    ExtensionActionButton(bot, "load"),
                    ExtensionActionButton(bot, "unload"),
                    ExtensionActionButton(bot, "reload"),
                ),
                discord.ui.TextDisplay(
                    "### Maintenance\n"
                    "Slash command sync, ban import, blacklist reload, cleaning orphaned "
                    "ticket rows, and bulk-closing Report tickets that have gone unanswered "
                    "for a chosen number of hours (closes them with the neglect apology)."
                ),
                discord.ui.ActionRow(
                    SyncCommandsButton(bot), ImportBansButton(bot),
                    ReloadBlacklistButton(bot), TicketCleanupButton(bot),
                    CloseNeglectedReportsButton(bot),
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Messaging\n"
                    "The messaging tools (echo, edit and delete) "
                    f"live in the Mod Hub: {mod_hub_link()}\n"
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Auto-responses\n"
                    "Words the bot automatically replies to."
                ),
                discord.ui.ActionRow(
                    AutoResponseListButton(bot),
                    AutoResponseAddButton(bot),
                    AutoResponseRemoveButton(bot),
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Content\n"
                    "**Channel templates (welcome / testing-info):**\n"
                    "Edit and preview a section, then rebuild the channel to apply it.\n\n"
                    "**Guide commands (`$`-prefix commands):**\n"
                    "Add, Edit or Remove guide commands."
                ),
                discord.ui.ActionRow(
                    TemplateEditButton(bot), TemplateRebuildButton(bot), ManageGuidesButton(bot),
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Player rename\n"
                    "Renames a player in the DDNet database.\n"
                    "-# Also available as /rename (same checks and confirmation), available to admins only."
                ),
                discord.ui.ActionRow(RenameButton(bot)),
                accent_colour=INFO_ACCENT,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction, roles=[Roles.ADMIN])
