import logging
import os

import discord

from utils.containers import NoticeView, separator
from utils.misc import connect_url
from utils.text import choice_to_datetime, to_discord_timestamp
from extensions.management.hub import HubButton
from .utils import players

log = logging.getLogger()

DURATION_OPTIONS = [
    ("For 30 minutes", "0"),
    ("For 1 hour", "1"),
    ("For 6 hours", "2"),
    ("For 12 hours", "3"),
    ("For 24 hours", "4"),
    ("For 3 days", "5"),
    ("For 7 days", "6"),
    ("For 14 days", "7"),
    ("For 30 days", "8"),
]


class PfAddModal(discord.ui.Modal, title="Add to watchlist"):
    name = discord.ui.Label(
        text="Player name",
        component=discord.ui.TextInput(max_length=255),
    )
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=1000),  # noqa
    )

    def __init__(self):
        super().__init__(timeout=300)
        self.duration = discord.ui.Label(
            text="Duration",
            component=discord.ui.Select(
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label=label, value=value) for label, value in DURATION_OPTIONS],
            ),
        )
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.component.value.strip()
        reason = self.reason.component.value.strip()
        expiry = choice_to_datetime(int(self.duration.component.values[0]))
        try:
            player = await interaction.client.pfm.add_player(
                name=name, reason=reason, added_by=interaction.user, expiry_date=expiry,
            )
        except ValueError as e:
            await interaction.response.send_message(view=NoticeView(str(e)), ephemeral=True)
            return
        log.info("ModHub: %s added playerfinder watch %r", interaction.user, player.name)
        await interaction.response.send_message(
            view=NoticeView(
                f"Added `{player.name}` -- expires {to_discord_timestamp(player.expiry_date, 'R')}."
            ),
            ephemeral=True,
        )


class PfRemoveModal(discord.ui.Modal, title="Remove from watchlist"):
    name = discord.ui.Label(
        text="Player name",
        component=discord.ui.TextInput(max_length=255),
    )

    def __init__(self):
        super().__init__(timeout=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.component.value.strip()
        try:
            await interaction.client.pfm.del_player(name)
        except ValueError:
            await interaction.response.send_message(
                view=NoticeView(f'No player named "{name}" on the watchlist.'), ephemeral=True
            )
            return
        log.info("ModHub: %s removed playerfinder watch %r", interaction.user, name)
        await interaction.response.send_message(
            view=NoticeView(f"Removed `{name}` from the watchlist."), ephemeral=True
        )


class PfEditModal(discord.ui.Modal, title="Edit watchlist reason"):
    name = discord.ui.Label(
        text="Player name",
        component=discord.ui.TextInput(max_length=255),
    )
    reason = discord.ui.Label(
        text="New reason",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=1000),  # noqa
    )

    def __init__(self):
        super().__init__(timeout=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.component.value.strip()
        new_reason = self.reason.component.value.strip()
        try:
            old_reason, player = await interaction.client.pfm.edit_reason(name, new_reason)
        except ValueError:
            await interaction.response.send_message(
                view=NoticeView(f'No player named "{name}" on the watchlist.'), ephemeral=True
            )
            return
        log.info("ModHub: %s edited playerfinder reason for %r", interaction.user, player.name)
        await interaction.response.send_message(
            view=NoticeView(
                f"Updated reason for `{player.name}`:\n"
                "```diff\n"
                f"-{old_reason}\n"
                f"+{player.reason}\n"
                "```"
            ),
            ephemeral=True,
        )


class PfInfoModal(discord.ui.Modal, title="Watchlist info"):
    name = discord.ui.Label(
        text="Player name",
        component=discord.ui.TextInput(max_length=255),
    )

    def __init__(self):
        super().__init__(timeout=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.component.value.strip()
        player = interaction.client.pfm.find_player(name)
        if player is None:
            await interaction.response.send_message(
                view=NoticeView(f'"{name}" is not on the watchlist.'), ephemeral=True
            )
            return
        text = (
            f"## `{player.name}`\n"
            f"**Reason:** {player.reason}\n"
            f"**Expires:** {to_discord_timestamp(player.expiry_date, 'R')}\n"
            f"**Added by:** {player.added_by}"
        )
        if player.ban_link:
            text += f"\n**Ban link:** {player.ban_link}"
        await interaction.response.send_message(view=NoticeView(text), ephemeral=True)


class PfFindModal(discord.ui.Modal, title="Find online player"):
    name = discord.ui.Label(
        text="Player name (exact)",
        component=discord.ui.TextInput(max_length=255),
    )

    def __init__(self):
        super().__init__(timeout=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = interaction.client.get_cog("Overseer")
        if cog is None or cog.session is None:
            await interaction.followup.send(
                view=NoticeView("Playerfinder is not running, so live search is unavailable."),
                ephemeral=True,
            )
            return

        name = self.name.component.value.strip()
        online = await players(cog.session, cog.master_url)
        servers = online.get(name)
        if not servers:
            await interaction.followup.send(
                view=NoticeView(f'No online player named "{name}" right now.'), ephemeral=True
            )
            return

        lines = [f'Found `{name}` on {len(servers)} server(s):']
        lines.extend(
            f"{i}. {server_name} -- <{connect_url(address)}>"
            for i, (server_name, address) in enumerate(servers[:25], start=1)
        )
        if len(servers) > 25:
            lines.append(f"-# ... and {len(servers) - 25} more (use a less common name)")
        await interaction.followup.send(view=NoticeView("\n".join(lines)), ephemeral=True)


class PfAddButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Add", custom_id="ModHub:pf-add",
            style=discord.ButtonStyle.success, roles="game_mods",  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PfAddModal())


class PfRemoveButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Remove", custom_id="ModHub:pf-remove",
            style=discord.ButtonStyle.danger, roles="game_mods",  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PfRemoveModal())


class PfEditButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Edit reason", custom_id="ModHub:pf-edit", roles="game_mods")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PfEditModal())


class PfInfoButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Query Player", custom_id="ModHub:pf-info", roles="game_mods")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PfInfoModal())


class PfFindButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Find online", custom_id="ModHub:pf-find", roles="game_mods")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PfFindModal())


class PfListButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Print List", custom_id="ModHub:pf-list", roles="game_mods")

    async def run(self, interaction: discord.Interaction) -> None:
        manager = interaction.client.pfm
        if not manager.players:
            await interaction.response.send_message(
                view=NoticeView("The watchlist is empty."), ephemeral=True
            )
            return

        lines = [f"{'Player':<20} {'Added by':<20} {'Expires':<12} Reason", "-" * 80]
        lines.extend(
            f"{player.name:<20} {player.added_by:<20} {str(player.expiry_date):<12} {player.reason}"
            for player in manager.players
        )

        path = "data/player_list.txt"
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        try:
            await interaction.response.send_message(
                file=discord.File(path, "player_list.txt"), ephemeral=True
            )
        finally:
            os.remove(path)


class PfStartButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Start search", custom_id="ModHub:pf-start",
            style=discord.ButtonStyle.success, roles="game_mods",  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Overseer")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("Playerfinder cog is not loaded."), ephemeral=True
            )
            return
        if cog.overseer.is_running():
            await interaction.response.send_message(
                view=NoticeView("The search is already running."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await cog.clean_up()
        cog.overseer.start()
        await interaction.followup.send(view=NoticeView("Initializing search..."), ephemeral=True)


class PfStopButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Stop search", custom_id="ModHub:pf-stop",
            style=discord.ButtonStyle.danger, roles="game_mods",  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Overseer")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("Playerfinder cog is not loaded."), ephemeral=True
            )
            return
        if not cog.overseer.is_running():
            await interaction.response.send_message(
                view=NoticeView("The search is not running."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog.overseer.cancel()
        await cog.clean_up()
        await interaction.followup.send(view=NoticeView("Search stopped."), ephemeral=True)


def playerfinder_action_rows(bot) -> list[discord.ui.Item]:
    """The playerfinder controls for ModHubView"""
    return [
        discord.ui.ActionRow(
            PfAddButton(bot), PfRemoveButton(bot)),
        separator(),
        discord.ui.ActionRow(
            PfEditButton(bot), PfInfoButton(bot), PfListButton(bot), PfFindButton(bot)),
        separator(),
        discord.ui.ActionRow(PfStartButton(bot), PfStopButton(bot)),
    ]
