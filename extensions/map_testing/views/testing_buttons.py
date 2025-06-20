# type: ignore
import logging
import datetime
from datetime import timedelta

import discord
from discord.ui import Button
from discord.ext import commands

# from extensions.map_testing.log import TestLog
from extensions.map_testing.embeds import MapReleased
from extensions.map_testing.map_states import MapState
from extensions.map_testing.cooldown import global_cooldown, cooldown_response
from extensions.map_testing.scores import add_score
from extensions.map_testing.views.modals.change_mapper_m import CMappersModal
from extensions.map_testing.views.modals.change_subm_owner_m import CSubmissionOwner
from extensions.map_testing.views.modals.server_selection_m import CServerSelect
from extensions.map_testing.views.rating_selection import RatingSelect
from constants import Roles
from utils.checks import is_staff
from utils.text import to_discord_timestamp

log = logging.getLogger("mt")


class ButtonOnCooldown(commands.CommandError):
    """
    Exception raised when a button is on cooldown.
    Args:
        retry_after (float): The time in seconds until the button can be pressed again.
    """
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


class TestingMenu(discord.ui.View):
    """Represents the buttons in map channel thread menus.

    This class provides a user interface for map channel related changes,
    such as changing the state, renaming the map or mappers.

    Args:
        bot: The bot instance used to manage the interactions.
    """

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, lambda i: i.user.id)
        self.map_testing = self.bot.get_cog("SubmissionHandler")

    async def interaction_check(self, interaction: discord.Interaction):
        """|coro|
        Verifies if a button interaction can proceed based on cooldown status.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.

        Returns:
            bool: True if the interaction is permitted, False if it is still on cooldown.
        """
        if retry_after := self.cooldown.update_rate_limit(interaction):  # noqa
            await interaction.response.send_message("Hey! Don't spam the buttons.", ephemeral=True)
            return False

        if not is_staff(
                interaction.user,
                roles=[
                    Roles.ADMIN,
                    Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
                    Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS
                ]
        ):
            await interaction.response.send_message("You're missing the required Role to do that!", ephemeral=True)
            return False

        # Check cooldown (2 channel updates every 15 minutes)
        return not await cooldown_response(interaction)

    @discord.ui.button(label="Ready", style=discord.ButtonStyle.green, custom_id="TestingMenu:ready")
    async def mt_ready(self, interaction: discord.Interaction, _: Button):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa

        # Handle already ready or invalid map states
        if map_channel.state == MapState.READY:
            await interaction.response.send_message("Map is already set to `Ready`.", ephemeral=True)
            return

        if map_channel.state == MapState.WAITING:
            await interaction.response.send_message(
                "Unable to ready a map in `WAITING`. Reset the channel first, then try again.",
                ephemeral=True
            )
            return

        if interaction.user in map_channel.votes and self.bot.user not in map_channel.votes:
            await interaction.response.send_message(
                "You cannot ready the map again. The map needs to be tested by a different tester before fully evaluated.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Please select a Map Rating:",
            view=RatingSelect(self.bot),
            ephemeral=True
        )

    @discord.ui.button(label="Waiting Mapper", style=discord.ButtonStyle.primary, custom_id="TestingMenu:waiting")
    async def mt_waiting(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa

        if map_channel == MapState.WAITING:
            await interaction.response.send_message(content="Map is already in waiting mapper.")
            return

        await map_channel.set_state(state=MapState.WAITING)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/WAITING",
            string=f"\"{map_channel.name}\" has been moved to WAITING."
        )
        await map_channel.changelog_paginator.update_changelog()
        add_score(interaction.user.id, "WAITING")

        query = """
                INSERT INTO discordbot_waiting_maps (channel_id)
                VALUES (%s)
                ON DUPLICATE KEY UPDATE timestamp = CURRENT_TIMESTAMP; \
                """
        await self.bot.upsert(query, map_channel.id)

        await interaction.followup.send(content="Map channel has been moved to waiting mapper.")
        embed = discord.Embed(
            title=f"",
            description=f"{map_channel.mapper_mentions}\nYour map channel has been moved to WAITING MAPPER.\n"
                        f"Kindly review the issues highlighted by our Testers.",
            color=discord.Color.dark_purple()
        )
        await map_channel.send(embed=embed)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="TestingMenu:decline")
    async def mt_decline(self, interaction: discord.Interaction, _: Button):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa

        if map_channel.state == MapState.DECLINED:
            await interaction.response.send_message(content="Map has already been declined.", ephemeral=True)
            return

        if map_channel.state == MapState.RELEASED:
            await interaction.response.send_message(content="Unable to decline already released maps.", ephemeral=True)
            return

        await interaction.response.send_modal(DeclineReasonModal(self.bot))  # noqa

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:reset")
    async def mt_reset(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa

        # await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa
        await map_channel.set_state(state=MapState.TESTING, reset_votes=True)
        global_cooldown.update_cooldown(interaction.channel.parent.id)
        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/RESET",
            string=f"\"{map_channel.name}\" has been RESET."
        )
        await map_channel.changelog_paginator.update_changelog()

        # Unsure if we want to keep track of this. It's really just for debugging purposes.
        # add_score(interaction.user.id, "WAITING")

        # Interaction user response (ephemeral)
        await interaction.followup.send(
            content="Moved channel back to TESTING.",
        )

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"{map_channel.mapper_mentions} Your map channel has been moved back to TESTING.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)

    @discord.ui.button(label="Set to Released", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:released")
    async def mt_released(self, interaction: discord.Interaction, _: Button):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)

        if map_channel.state == MapState.RELEASED:
            await interaction.response.send_message(content="Map is already set to RELEASED.", ephemeral=True)
            return

        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa

        await map_channel.set_state(state=MapState.RELEASED)
        global_cooldown.update_cooldown(interaction.channel.parent.id)
        
        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/RELEASED",
            string=f"\"{map_channel.name}\" has been manually set to RELEASED."
        )
        await map_channel.changelog_paginator.update_changelog()

        message = await map_channel.send(
            embed=MapReleased(
                map_channel, 
                to_discord_timestamp(discord.utils.utcnow() + timedelta(weeks=2), style="F")
            )
        )

        await interaction.response.send_message(
            content=f"Map channel set to RELEASED: {message.jump_url}",
            ephemeral=True
        )

    @discord.ui.button(label="Change Map Name", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:CName")
    async def mt_change_name(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.send_modal(CMapNameModal(self.bot))  # noqa

    @discord.ui.button(label="Change Mappers", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:CMappers")
    async def mt_change_mappers(self, interaction: discord.Interaction, _: Button):
        await interaction.response.send_modal(CMappersModal(self.bot))

    @discord.ui.button(label="Change Submission Owner", style=discord.ButtonStyle.secondary,
                       custom_id="TestingMenu:COwner")
    async def mt_change_channel_owner(self, interaction: discord.Interaction, _: Button):
        if not is_staff(
                interaction.user,
                roles=[
                    Roles.ADMIN,
                    Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
                    Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS
                ]
        ):
            await interaction.response.send_message("You're missing the required Role to do that!", ephemeral=True)
            return

        await interaction.response.send_modal(CSubmissionOwner(self.bot))

    @discord.ui.button(label="Change Server", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:CServer")
    async def mt_change_server(self, interaction: discord.Interaction, _: Button):
        await interaction.response.send_message(
            "Please select a server:",
            view=CServerSelect(self.bot),
            ephemeral=True
        )

    @discord.ui.button(label="Archive", style=discord.ButtonStyle.danger, custom_id="TestingMenu:archive")
    async def mt_archive(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa

        tlog = ... # await TestLog.from_map_channel(map_channel)
        await interaction.edit_original_response(content="Archiving...")
        arch = await self.map_testing.archive_testlog(tlog)
        if arch:
            await map_channel.delete()
            log.info("Successfully archived channel #%s", map_channel)
        else:
            await interaction.edit_original_response(
                content="Failed to archive... contact an Admin."
            )
            log.error("Failed archiving channel #%s", map_channel)