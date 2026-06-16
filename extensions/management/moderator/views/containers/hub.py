import datetime
import logging

import discord
from discord.ext import commands

from constants import Channels, Roles
from utils.activity import build_playing_view, collect_games
from utils.misc import log_to
from utils.text import to_discord_timestamp, clip
from utils.containers import INFO_ACCENT, separator, NoticeView, paged_pairs_view
from extensions.management.hub import HubButton, staff_guard
from extensions.management.moderator.views.containers.channel_tools import SlowmodeView, PurgeView, LockView
from extensions.management.moderator.views.containers.messaging import EchoPanel, EditMessageModal, DeleteMessageModal
from extensions.management.moderator.player_finder.controls import playerfinder_action_rows

log = logging.getLogger()

PLAYING_OVERVIEW = " overview"
DISCORD_ROLES = [Roles.ADMIN, Roles.DISCORD_MODERATOR]
SHARED_ROLES = [Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]


class PlayingModal(discord.ui.Modal, title="Who is playing?"):
    def __init__(self, bot, games: dict):
        super().__init__(timeout=300)
        self.bot = bot

        # collect_games keys are (name, app_id); the same name can appear
        # with and without an app ID, so merge the player counts per name.
        counts: dict[str, int] = {}
        for (name, _app_id), members in games.items():
            counts[name] = counts.get(name, 0) + len(members)

        options = [
            discord.SelectOption(
                label="All games (overview)",
                value=PLAYING_OVERVIEW,
                description="Every game with player counts and app IDs.",
            )
        ]
        most_played = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
        options.extend(
            discord.SelectOption(
                label=clip(name, 100),
                value=name[:100],
                description=f"{count} playing",
            )
            for name, count in most_played[:24]
        )
        self.game = discord.ui.Label(
            text="Game",
            description="Pick a game to see who is playing it, or the overview of everything.",
            component=discord.ui.Select(
                placeholder="Select a game",
                min_values=1,
                max_values=1,
                options=options,
                required=False,
            ),
        )
        self.add_item(self.game)

        self.search = discord.ui.Label(
            text="Search by name instead (optional)",
            description="Part of the name or an application ID is enough; overrides the dropdown.",
            component=discord.ui.TextInput(max_length=100, required=False),
        )
        self.add_item(self.search)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        typed = self.search.component.value.strip()
        picked = self.game.component.values[0] if self.game.component.values else None
        if picked == PLAYING_OVERVIEW:
            picked = None

        await interaction.response.send_message(
            view=build_playing_view(self.bot, typed or picked),
            ephemeral=True,
        )


class UserLookupModal(discord.ui.Modal, title="User lookup"):
    query = discord.ui.Label(
        text="User ID or exact username",
        component=discord.ui.TextInput(max_length=100),
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.query.component.value.strip()
        await interaction.response.defer(ephemeral=True, thinking=True)

        user = None
        if raw.isdigit():
            user = await self.bot.get_or_fetch_member(guild=interaction.guild, user_id=int(raw))
        else:
            user = interaction.guild.get_member_named(raw)

        if user is None:
            await interaction.edit_original_response(
                view=NoticeView(f'No user found for "{raw}". Use their ID or exact name.')
            )
            return

        info = await self.bot.moddb.fetch_user_info(user)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.edit_original_response(view=NoUserInfoView())
            return

        await interaction.edit_original_response(view=UserInfoView(self.bot, info))


class BlacklistAddModal(discord.ui.Modal, title="Blacklist a word"):
    trigger = discord.ui.Label(
        text="Word or phrase",
        component=discord.ui.TextInput(max_length=100),
    )
    response = discord.ui.Label(
        text="DM sent to the user (empty = default)",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=False,
            max_length=300,
        ),
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("Blacklist")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The blacklist is not loaded."), ephemeral=True
            )
            return

        success, message = await cog.add_word(self.trigger.component.value, self.response.component.value)
        if success:
            log.info("ModHub: %s blacklisted %r", interaction.user, self.trigger.component.value)
        await interaction.response.send_message(view=NoticeView(message), ephemeral=True)


class BlacklistRemoveModal(discord.ui.Modal, title="Remove a blacklisted word"):
    trigger = discord.ui.Label(
        text="Word or phrase to remove",
        component=discord.ui.TextInput(max_length=100),
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("Blacklist")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The blacklist is not loaded."), ephemeral=True
            )
            return

        success, message = await cog.remove_word(self.trigger.component.value)
        if success:
            log.info("ModHub: %s un-blacklisted %r", interaction.user, self.trigger.component.value)
        await interaction.response.send_message(view=NoticeView(message), ephemeral=True)


class UserLookupButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="User Lookup", custom_id="DiscordHub:user",
            style=discord.ButtonStyle.primary, roles=SHARED_ROLES,  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(UserLookupModal(self.bot))


class SlowmodeButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Slowmode", custom_id="DiscordHub:slowmode", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=SlowmodeView(), ephemeral=True)


class PurgeButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Purge", custom_id="DiscordHub:purge", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=PurgeView(), ephemeral=True)


class LockButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Lock / Unlock", custom_id="DiscordHub:lock", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=LockView(), ephemeral=True)


class EchoButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Echo Message", custom_id="DiscordHub:echo", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=EchoPanel(), ephemeral=True)


class EditMessageButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Edit Message", custom_id="DiscordHub:msg-edit", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(EditMessageModal(self.bot))


class DeleteMessageButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Delete Message", custom_id="DiscordHub:msg-delete", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(DeleteMessageModal(self.bot))


class BlacklistShowButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Show list", custom_id="DiscordHub:bl-list", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("Blacklist")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The blacklist is not loaded."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            view=paged_pairs_view(
                "Blacklisted words", cog.words.items(),
                empty_note="The blacklist is empty.",
            ),
            ephemeral=True,
        )


class BlacklistAddButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Add word", custom_id="DiscordHub:bl-add", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BlacklistAddModal(self.bot))


class BlacklistRemoveButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Remove word", custom_id="DiscordHub:bl-remove", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BlacklistRemoveModal(self.bot))


class RaidActionButton(HubButton):
    def __init__(self, bot, *, what: str, pause: bool):
        self.what = what  # "invites" | "dms"
        self.pause = pause
        label = f"Pause {what} (24h)" if pause else f"Resume {what}"
        style = discord.ButtonStyle.danger if pause else discord.ButtonStyle.success
        super().__init__(
            bot, label=label.replace("dms", "DMs"),
            custom_id=f"DiscordHub:{what}-{'pause' if pause else 'resume'}",
            style=style, roles=DISCORD_ROLES,
        )

    async def run(self, interaction: discord.Interaction) -> None:
        until = discord.utils.utcnow() + datetime.timedelta(hours=24) if self.pause else None
        kwargs = {f"{self.what}_disabled_until": until}

        try:
            await interaction.guild.edit(
                reason=f"{'Paused' if self.pause else 'Resumed'} by {interaction.user} via moderation hub",
                **kwargs,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                view=NoticeView("I am missing the Manage Server permission for that."),
                ephemeral=True,
            )
            return

        word = "DMs" if self.what == "dms" else "invites"
        if self.pause:
            outcome = f"{word.capitalize()} paused until {to_discord_timestamp(until, 'f')}."
        else:
            outcome = f"{word.capitalize()} resumed."

        log.info("ModHub: %s -- %s", interaction.user, outcome)
        await interaction.response.send_message(view=NoticeView(outcome), ephemeral=True)

        await log_to(
            self.bot, Channels.LOG_MOD_ACTIONS,
            view=NoticeView(f"{interaction.user.mention}: {outcome}"),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class WhoIsPlayingButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Activity Scan", custom_id="DiscordHub:playing", roles=SHARED_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        games = collect_games(self.bot)
        if not games:
            await interaction.response.send_message(
                view=build_playing_view(self.bot), ephemeral=True
            )
            return
        await interaction.response.send_modal(PlayingModal(self.bot, games))


class RecentJoinsButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Recent joins", custom_id="DiscordHub:joins", roles=DISCORD_ROLES)

    async def run(self, interaction: discord.Interaction) -> None:
        members = [m for m in interaction.guild.members if m.joined_at]
        members.sort(key=lambda m: m.joined_at, reverse=True)
        members = members[:15]

        now = discord.utils.utcnow()
        lines = ["## 15 most recent joins"]
        for member in members:
            line = (
                f"{member.mention} joined {to_discord_timestamp(member.joined_at, 'R')}, "
                f"account created {to_discord_timestamp(member.created_at, 'R')}"
            )
            if (now - member.created_at) < datetime.timedelta(days=7):
                line += " ⚠️"
            lines.append(line)
        lines.append("-# ⚠️ = account younger than 7 days")

        await interaction.response.send_message(
            view=NoticeView("\n".join(lines)), ephemeral=True
        )


class ModHubView(discord.ui.LayoutView):
    """
    The moderator hub in Channels.MOD_HUB.
    Exposes the playerfinder watchlist controls and is where future moderator helper tools go.
    The Discord-server tools live on a separate message in the same channel (DiscordModHubView, found below)
    """

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("# Moderator Hub"),
                separator(),
                discord.ui.TextDisplay(
                    "## Playerfinder\n"
                    "Watchlist for flagged players. Add or remove names, edit a reason, "
                    "look one up, dump the full list, search who is online right now, or "
                    "start/stop the live search."
                ),
                *playerfinder_action_rows(bot),
                accent_colour=INFO_ACCENT,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction)


class DiscordModHubView(discord.ui.LayoutView):
    """The Discord moderation tools, kept on a separate message in Channels.MOD_HUB"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("# Discord Moderation"),
                separator(),
                discord.ui.TextDisplay(
                    "## Lookups\n"
                    "Look up a user's moderation history and name changes (contains Ban / "
                    "Timeout / Kick / Remove Entry controls), or see who is playing what "
                    "right now.\n\n"
                    "-# Available to **Moderators** and **Discord Moderators**. Also /info, /ban, "
                    "/unban, /timeout, /kick and the \"Ban user\" context menu."
                ),
                discord.ui.ActionRow(UserLookupButton(bot), WhoIsPlayingButton(bot)),
                separator(),
                discord.ui.TextDisplay(
                    "## Channel tools\n"
                    "Slowmode, bulk-delete messages, and lock a channel for @everyone.\n"
                    "-# Slowmode is also available as /slowmode (run in the target channel)."
                ),
                discord.ui.ActionRow(SlowmodeButton(bot), PurgeButton(bot), LockButton(bot)),
                separator(),
                discord.ui.TextDisplay(
                    "## Messaging\n"
                    "Send a message as the bot, or edit/delete an existing message "
                    "by its URL.\n"
                    "-# Available as right-click context menu: \"Echo a message\", \"Reply to this message\" and "
                    "\"Edit this message\"."
                ),
                discord.ui.ActionRow(
                    EchoButton(bot), EditMessageButton(bot), DeleteMessageButton(bot)
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Word blacklist\n"
                    "Messages containing blacklisted words are deleted automatically."
                ),
                discord.ui.ActionRow(
                    BlacklistShowButton(bot), BlacklistAddButton(bot), BlacklistRemoveButton(bot)
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Anti-raid & insights\n"
                    "Pause invites or DMs server-wide for 24 hours, and check the newest joins."
                ),
                discord.ui.ActionRow(
                    RaidActionButton(bot, what="invites", pause=True),
                    RaidActionButton(bot, what="dms", pause=True),
                    RecentJoinsButton(bot),
                ),
                discord.ui.ActionRow(
                    RaidActionButton(bot, what="invites", pause=False),
                    RaidActionButton(bot, what="dms", pause=False),
                ),
                accent_colour=INFO_ACCENT,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction, roles=SHARED_ROLES)
