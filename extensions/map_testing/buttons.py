import contextlib
import json
import logging
import datetime
from typing import Optional, Union, Any
import io

import discord
from discord.ui import Button
from discord.ext import commands

from extensions.map_testing import TestLog
from extensions.map_testing.map_channel import MapState
from extensions.map_testing.submission import Submission
from extensions.map_testing.cooldown import global_cooldown
from constants import Roles, URLs

from utils.text import slugify2
from utils.checks import is_staff
from utils.misc import rating
from utils.conn import ddnet_delete

log = logging.getLogger("mt")

def has_map(message: discord.Message) -> bool:
    return any(
        attachment.filename.endswith(".map")
        for attachment in message.attachments
    )


async def cooldown(interaction: discord.Interaction) -> bool:
    if isinstance(interaction.channel, discord.Thread):
        channel_id = interaction.channel.parent.id
    else:
        channel_id = interaction.channel.id
    on_cooldown, remaining_time = global_cooldown.check(channel_id)
    if on_cooldown:
        msg = (f"Cooldown active. Try again in {remaining_time:.2f} seconds."
               f"-# Map Channels can be updated twice every 15 minutes. This is a Discord limitation.")
        try:
            await interaction.response.send_message(msg, ephemeral=True)  # noqa
        except discord.errors.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)  # noqa
        return True
    return False


async def send_message(
        msg_type: Union[discord.Message, discord.Interaction],
        content: Union[discord.Embed, str],
        file: Optional[discord.File] = None,
) -> None:
    if isinstance(msg_type, discord.message.Message):
        msg = await msg_type.reply(embed=content, mention_author=False)
        if file:
            await msg.reply(file=file, mention_author=False)
    elif isinstance(msg_type, discord.Interaction):
        if file:
            await msg_type.channel.send(content=content, file=file)
            await msg_type.delete_original_response()
        else:
            await msg_type.edit_original_response(content=content)


async def debug_check(subm: Any, msg_type: Union[discord.Message, discord.Interaction], r_event: bool = False) -> bool:
    debug_output = await subm.debug_map()

    if not debug_output:
        return False

    if isinstance(msg_type, discord.message.Message):
        if len(debug_output) < 1900:
            msg = discord.Embed(
                title="⚠️ Map Bugs found! ⚠️",
                description=f"Debug Output:\n```{debug_output}```\n"
                            f"Please address the issues, otherwise we're unable to release your map!\n"
                            f"If you're unable to resolve the bugs yourself, don't hesitate to ask!",
                color=discord.Color.dark_red()
            )
            file = None
        else:
            msg = discord.Embed(
                title="⚠️ Map Bugs found! ⚠️",
                description=f"Debug Output is too long, see the attached file. "
                            f"Please address the issues, otherwise we're unable to release your map!\n"
                            f"If you're unable to resolve the bugs yourself, don't hesitate to ask!",
                color=discord.Color.dark_red()
            )
            file = discord.File(io.StringIO(debug_output), filename="debug_output.txt")  # noqa

    if isinstance(msg_type, discord.Interaction):
        msg = "Unable to ready map. Fix the map :lady_beetle:'s first: " if r_event else "Map :lady_beetle: : \n"
        if len(debug_output) < 1900:
            msg = f"{msg}```{debug_output}```"
            file = None
        else:
            msg = f"{msg}Debug output is too long, see attached text file."
            file = discord.File(io.StringIO(debug_output), filename="debug_output.txt")  # noqa

    await send_message(msg_type, msg, file)
    return True


def add_score(user_id: int, button_name: str):
    """Track a button press by a specific user.

    Args:
        user_id (int): The Discord user ID.
        button_name (str): One of "READY", "DECLINED", "RESET", "WAITING".
    """

    score_file = "data/map-testing/scores.json"

    button_name = button_name.upper()
    if button_name not in {"READY", "DECLINED", "RESET", "WAITING"}:
        raise ValueError(f"Invalid button name: {button_name}")

    try:
        with open(score_file, "r", encoding="utf-8") as f:
            scores = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        scores = {}

    user_id_str = str(user_id)
    if user_id_str not in scores:
        scores[user_id_str] = {btn: 0 for btn in ["READY", "DECLINED", "RESET", "WAITING"]}
    scores[user_id_str][button_name] += 1

    with open(score_file, "w") as f:
        json.dump(scores, f, indent=4)


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
        if await cooldown(interaction):
            return False
        
        return True

    @discord.ui.button(label="Ready", style=discord.ButtonStyle.green, custom_id="TestingMenu:ready")
    async def mt_ready(self, interaction: discord.Interaction, _: Button):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

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

        if interaction.user.mention in map_channel.votes and self.bot.user.mention not in map_channel.votes:
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
        await interaction.response.defer(thinking=True, ephemeral=True) # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

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
        INSERT INTO 
            discordbot_waiting_maps (channel_id) 
        VALUES 
            (%s)
        ON DUPLICATE KEY UPDATE 
            timestamp = CURRENT_TIMESTAMP;
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
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

        if map_channel.state == MapState.DECLINED:
            await interaction.response.send_message(content="Map has already been declined.", ephemeral=True)
            return

        if map_channel.state == MapState.RELEASED:
            await interaction.followup.send_message(content="Unable to decline already released maps.", ephemeral=True)
            return

        await interaction.response.send_modal(DeclineReasonModal(self.bot))  # noqa

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:reset")
    async def mt_reset(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa

        # await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
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

        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        # await map_channel.set_state(state=MapState.RELEASED)
        # global_cooldown.update_cooldown(interaction.channel.parent.id)
        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/RELEASED",
            string=f"\"{map_channel.name}\" has been manually set to RELEASED."
        )
        await map_channel.changelog_paginator.update_changelog()

        grace_period_end = discord.utils.utcnow() + datetime.timedelta(weeks=2)
        grace_period_timestamp = f"<t:{int(grace_period_end.timestamp())}:F>"  # Full date/time

        em = discord.Embed(
            title="📢 Map Released!",
            color=discord.Color.dark_gray(),
            description=(
                f"{map_channel.mapper_mentions} your map has just been released! 🎉\n\n"
                "You now have a **2-week grace period** to identify and resolve any unnoticed bugs or skips. "
                "After this period, only **design** and **quality of life** fixes will be allowed, provided "
                "they do **not** affect leaderboard rankings.\n\n"
                "⚠️ Significant gameplay changes may result in **rank removals**.\n\n"
                "Good luck with your map!\n"
            )
        )
        em.add_field(
            name="🕒 Grace Period Ends",
            value=grace_period_timestamp,
            inline=False
        )
        em.set_footer(text="Make sure to review your map thoroughly before the grace period ends!")
        await map_channel.send(embed=em)

        await interaction.response.send_message(
            content="Map channel set to RELEASED.",
            ephemeral=True
        )
        
    @discord.ui.button(label="Change Map Name", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:CName")
    async def mt_change_name(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.send_modal(CMapNameModal(self.bot))  # noqa

    @discord.ui.button(label="Change Mappers", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:CMappers")
    async def mt_change_mappers(self, interaction: discord.Interaction, _: Button):
        await interaction.response.send_modal(CMappersModal(self.bot))

    @discord.ui.button(label="Change Submission Owner", style=discord.ButtonStyle.secondary, custom_id="TestingMenu:COwner")
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
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

        tlog = await TestLog.from_map_channel(map_channel)
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


class ButtonLinks(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        rules = discord.ui.Button(
            label='Mapping Rules',
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_MAPPING_RULES
        )
        guidelines = discord.ui.Button(
            label='Mapping Guidelines',
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_MAPPING_GUIDELINES
        )
        self.add_item(rules)
        self.add_item(guidelines)


class RatingSelect(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        options = rating()
        self.select = discord.ui.Select(placeholder="Choose a rating...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def ready_callback(self, interaction: discord.Interaction, rating: str = None):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

        file = None
        eph_msg = None
        embed = None
        add = ""

        # Handle map in TESTING state
        if map_channel.state == MapState.TESTING:
            await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
            await map_channel.set_state(state=MapState.RC, set_by=interaction.user.mention)
            global_cooldown.update_cooldown(interaction.channel.parent.id)

            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                interaction.user,
                category="MapTesting/RC",
                string=f"\"{map_channel.name}\" has been set to RELEASE CANDIDATE."
            )
            await map_channel.changelog_paginator.update_changelog()
            add_score(interaction.user.id, "READY")

            user_roles = {role.id for role in interaction.user.roles}

            if user_roles.intersection({Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS}):
                embed = discord.Embed(
                    title="⭐ Channel state set to Release Candidate!",
                    description="First ready set by Trial Tester. "
                    "Map needs to be tested again by an official tester before fully evaluated.\n\n"
                    f"Suggested rating: {rating}",
                    colour=discord.Color.yellow()
                )
            else:
                embed = discord.Embed(
                    title="⭐ Channel state set to Release Candidate!",
                    description="First ready set. "
                    "It needs to be tested again by a different tester before fully evaluated.\n\n"
                    f"Suggested {rating}",
                    colour=discord.Color.yellow()
                )

            eph_msg = "Map channel state has been changed to RC."

        elif map_channel.state == MapState.RC:
            await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
            pins = await map_channel.pins()
            subm = Submission(pins[0])
            add = "Optimized:"

            if await debug_check(subm, interaction, r_event=True):
                if not interaction.response.is_done():  # noqa
                    await interaction.delete_original_response()
                return

            await map_channel.set_state(state=MapState.READY, set_by=interaction.user.mention)
            global_cooldown.update_cooldown(interaction.channel.parent.id)
            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                interaction.user,
                category="MapTesting/READY",
                string=f"\"{map_channel.name}\" has been set to state READY."
            )
            await map_channel.changelog_paginator.update_changelog()
            add_score(interaction.user.id, "READY")

            if pins[0].content.startswith("Optimized"):
                em_msg = f"Optimized version: {pins[0].jump_url}\n"
            else:
                stdout, file = await subm.edit_map("--remove-everything-unused", "--shrink-tiles-layers")
                em_msg = (
                    f"Optimized version attached.\nChangelog:\n```{stdout}```\n" if stdout
                    else "Optimized version attached.\n"
                )

            if unoptimized_map := next(
                (pin for pin in pins if has_map(pin)), None
            ):
                em_msg += f"Unoptimized version: {unoptimized_map.jump_url}"

            embed = discord.Embed(
                title=f"⭐ {map_channel.name} is now ready to be released!",
                description=f"{rating}\n"
                            f"\n\n"
                            f"{em_msg}",
                colour=discord.Color.green()
            )

            eph_msg = "Map channel has been set to READY."

        await map_channel.send(content=add, embed=embed)
        if file:
            await map_channel.send(file=file)
        await interaction.edit_original_response(content=eph_msg)

    async def callback(self, interaction: discord.Interaction):
        selected_rating = self.select.values[0]
        selected_label = next(option.label for option in rating() if option.value == selected_rating)
        await self.ready_callback(interaction, selected_label)


class DeclineReasonModal(discord.ui.Modal, title="Decline Reason"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    decline_reason = discord.ui.TextInput(
        label="Your Decline Reason",
        placeholder="You can leave this blank. The modal exist so you can provide the decline reason anonymously.",
        max_length=500,
        required=False,
        style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        await map_channel.set_state(state=MapState.DECLINED)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            self.bot.user if self.decline_reason.value == "" else interaction.user,
            category="MapTesting/DECLINE",
            string=f"\"{map_channel.name}\" has been DECLINED."
        )
        await map_channel.changelog_paginator.update_changelog()

        # Interaction user response (ephemeral)
        await interaction.followup.send(
            content=f"Declined submission \"{map_channel.name}\" successfully..",
            ephemeral=True
        )

        embed = discord.Embed(
            title="Submission has been declined.",
            description=f"{map_channel.mapper_mentions}\nUnfortunately, your map submission has been declined. "
                        "Don't worry though—take a look at the feedback from our Testers, and consider playing "
                        "our latest releases to gain more experience and better understanding what we're looking for!\n\n"
        )

        if self.decline_reason.value:
            embed.add_field(
                name="The reason provided:",
                value=self.decline_reason.value,
                inline=False
            )

        # Map channel response
        await map_channel.send(content=f"Mention: {map_channel.mapper_mentions}", embed=embed)

        add_score(interaction.user.id, "DECLINED")

        log.info("%s declined submission #%s", interaction.user, interaction.channel)


class CMapNameModal(discord.ui.Modal, title="Change Map Name"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    new_name = discord.ui.TextInput(
        label="The New Map Name",
        placeholder="Back in Time 4",
        max_length=32,
        style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        old_filename = map_channel.filename
        await map_channel.update(name=self.new_name.value)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/CHANGE_NAME",
            string=f"Map name has been changed to: \"{map_channel.name}\"."
        )
        await map_channel.changelog_paginator.update_changelog()

        with contextlib.suppress(RuntimeError):
            await ddnet_delete(self.bot.session, filename=old_filename)
        await interaction.response.send_message(
            f"Changed the map name to `{map_channel.name}`.", ephemeral=True
        )

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"{map_channel.mapper_mentions} The map name has been changed to `{map_channel.name}`.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)


class CMappersModal(discord.ui.Modal, title="Change Mappers"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.map_testing = self.bot.get_cog("SubmissionHandler")

    mappers = discord.ui.TextInput(
        label="Mappers",
        placeholder="Example: Welf, louis, Pipou, Ravie",
        max_length=64,
        style=discord.TextStyle.short)

    @staticmethod
    def get_mapper_urls(mappers: list) -> list:
        return [
            f"[{mapper}](https://ddnet.org/mappers/{slugify2(mapper)})"
            for mapper in mappers
        ]

    async def on_submit(self, interaction: discord.Interaction):
        mappers_list = [mapper.strip() for mapper in self.mappers.value.split(",")]
        mapper_urls = self.get_mapper_urls(mappers_list)
        map_channel = self.map_testing.get_map_channel(interaction.channel.parent.id)
        await map_channel.update(mappers=mappers_list)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/CHANGE_MAPPERS",
            string="Mappers has been changed to: {}.".format(", ".join(mapper_urls))
        )
        await map_channel.changelog_paginator.update_changelog()

        await interaction.response.send_message(
            f'Changed the mapper(s) to {", ".join(mapper_urls)}.',
            ephemeral=True
        )

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f'{map_channel.mapper_mentions} Changed the mapper(s) to {", ".join(mapper_urls)}.',
            color=discord.Color.darker_grey(),
        )
        await map_channel.send(embed=embed)


class CServerSelect(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        options = self.servers()
        self.select = discord.ui.Select(placeholder="Choose an option...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    @staticmethod
    def servers() -> list:
        return [
            discord.SelectOption(label="👶 Novice", value="0"),
            discord.SelectOption(label="🌸 Moderate", value="1"),
            discord.SelectOption(label="💪 Brutal", value="2"),
            discord.SelectOption(label="💀 Insane", value="3"),
            discord.SelectOption(label="♿ Dummy", value="4"),
            discord.SelectOption(label="👴 Oldschool", value="5"),
            discord.SelectOption(label="⚡ Solo", value="6"),
            discord.SelectOption(label="🏁 Race", value="7"),
            discord.SelectOption(label="🎉 Fun", value="8"),
        ]

    async def server_callback(self, interaction: discord.Interaction, server: str):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        await map_channel.update(server=server[2:])

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/CHANGE_SERVER",
            string=f"Server has been changed to: \"{map_channel.server}\"."
        )
        await map_channel.changelog_paginator.update_changelog()

        global_cooldown.update_cooldown(interaction.channel.parent.id)
        await interaction.response.send_message(
            f"Changed the Server Type to `{map_channel.server}`.",
            ephemeral=True
        )

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"{map_channel.mapper_mentions} Changed the Server Type to `{map_channel.server}`.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)

    async def callback(self, interaction: discord.Interaction):
        sel_server = self.select.values[0]
        sel_label = next(option.label for option in self.servers() if option.value == sel_server)

        await self.server_callback(interaction, sel_label)


class CSubmissionOwner(discord.ui.Modal, title="Change Submission Owner"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    ident = discord.ui.TextInput(
        label="The users ID.",
        placeholder="Up to 19 digits",
        max_length=19,
        style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        mapper_old = map_channel.mapper_mentions
        user = await self.bot.fetch_user(int(self.ident.value))

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting",
            string=f"\"{map_channel.name}\" ownership has been transferred from "
                   f"{map_channel.mapper_mentions} to \"{user.mention}\"."
        )
        await map_channel.changelog_paginator.update_changelog()
        await map_channel.update(mapper_mentions=user.mention)

        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await interaction.response.send_message(
            f"Changed the submission owner to {map_channel.mapper_mentions}.",
            ephemeral=True)

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"Submission owner changed to {map_channel.mapper_mentions}.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)