import logging
import re
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from extensions.map_testing.embeds import MapReleased, UnmatchedFilename, UnmatchedSubmOwner, MissingChangelog
from extensions.map_testing.cooldown import global_cooldown
from extensions.map_testing.log import TestLog
from extensions.map_testing.map_channel import MapChannel
from extensions.map_testing.scores import update_scores_topic
from extensions.map_testing.map_states import MapState
from extensions.map_testing.submission import (
    InitialSubmission,
    Submission,
    SubmissionState,
)
from extensions.map_testing.utils import (
    is_testing_channel,
    is_testing_staff,
    by_releases_webhook,
    debug_check
)
from extensions.ticketsystem.queries import rm_mapinfo_from_db, fetch_map_from_db
from utils.checks import has_map
from utils.conn import ddnet_upload, ddnet_delete, upload_submission
from constants import Guilds, Channels, Roles, Emojis
from utils.text import to_discord_timestamp

log = logging.getLogger("mt")


class NotStaffError(app_commands.CheckFailure):
    pass


class NotTestingChannelError(app_commands.CheckFailure):
    pass


def predicate(staff_only=True):
    async def inner(interaction: discord.Interaction) -> bool:
        testing = is_testing_channel(interaction.channel)
        if not testing:
            raise NotTestingChannelError("This isn't a testing channel.")
        if staff_only and not is_testing_staff(interaction.user):
            raise NotStaffError("You're not a Testing team member.")
        return True

    return inner


# noinspection PyShadowingNames
class MapTesting(commands.Cog):
    def __init__(self, bot):
        self.bot = TestLog.bot = bot
        self.session = None

        self.bot.map_channels = {}
        self._active_submissions = set()
        self.update_scores.start()

    async def cog_load(self):
        self.session = TestLog.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        self.auto_archive.cancel()
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def load_map_channels(self):
        for category_id in (
                Channels.CAT_TESTING,
                Channels.CAT_WAITING,
                Channels.CAT_EVALUATED,
        ):
            category = self.bot.get_channel(category_id)
            for channel in category.text_channels:
                if channel.id in (
                        Channels.TESTER_BANS,
                        Channels.TESTING_INFO,
                        Channels.TESTING_SUBMIT,
                        Channels.TESTER_META,
                        Channels.TESTER_CHAT,
                        Channels.TESTER_VOTES
                ):
                    continue

                try:
                    map_channel = await MapChannel.create(self.bot, channel)
                    await map_channel.load_changelogs()
                    self.bot.map_channels[channel.id] = map_channel
                except ValueError as exc:
                    log.error("Failed loading map channel #%s: %s", channel, exc)

    def get_map_channel(self, channel_id: Optional[int] = None, **kwargs) -> Optional[MapChannel]:
        if channel_id is not None:
            return self.bot.map_channels.get(channel_id)
        else:
            return discord.utils.get(self.map_channels, **kwargs)

    @property
    def map_channels(self) -> List[MapChannel]:
        return self.bot.map_channels.values()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_map_channels()
        await self.auto_archive.start()

    @commands.Cog.listener("on_message")
    async def handle_unwanted_message(self, message: discord.Message):
        author = message.author
        # system pin messages by ourselves
        # messages without a map file by non staff in submit maps channel
        if isinstance(author, discord.Member):
            channel = message.channel

            if (
                    is_testing_channel(channel)
                    and message.type is discord.MessageType.pins_add
                    and author.bot
            ) or (
                    channel.id == Channels.TESTING_SUBMIT
                    and not has_map(message)
                    and not is_testing_staff(author)
            ):
                await message.delete()

            # Internal votes channel
            if (
                    message.type is discord.MessageType.thread_created
                    and message.channel.id == Channels.TESTER_VOTES
            ):
                await message.add_reaction(self.bot.get_emoji(Emojis.F3))
                await message.add_reaction(self.bot.get_emoji(Emojis.F4))
                await message.add_reaction(self.bot.get_emoji(Emojis.MMM))

    @commands.Cog.listener("on_raw_reaction_add")
    @commands.Cog.listener("on_raw_reaction_remove")
    async def handle_perms(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != str(SubmissionState.PROCESSED):
            return

        action = payload.event_type
        channel = self.bot.get_channel(payload.channel_id)
        guild = channel.guild
        if action == "REACTION_ADD":
            member = payload.member
        else:
            member = guild.get_member(payload.user_id)
            if member is None:
                return

        if channel.id == Channels.TESTING_SUBMIT:
            message = self.bot.get_message(
                payload.message_id
            ) or await channel.fetch_message(payload.message_id)
            if not has_map(message):
                return

            map_channel = self.get_map_channel(filename=message.attachments[0].filename[:-4])
            if map_channel is None:
                if action == "REACTION_ADD":
                    await message.remove_reaction(payload.emoji, member)
                return

            if map_channel.overwrites_for(member).read_messages:
                if action == "REACTION_REMOVE":
                    await map_channel.set_permissions(member, overwrite=None)
            elif action == "REACTION_ADD":
                await map_channel.set_permissions(member, read_messages=True)

    def get_map_channel_from_ann(self, content: str) -> Optional[MapChannel]:
        map_url_re = (
            r"\[(?P<name>.+)\]\(<?https://ddnet\.org/(?:maps|mappreview)/\?map=.+?>?\)"
        )
        match = re.search(map_url_re, content)

        return match and self.get_map_channel(name=match["name"])

    async def archive_testlog(self, testlog: TestLog) -> bool:
        failed = False

        js = testlog.json()
        with open(f"{testlog.DIR}/json/{testlog.name}.json", "w", encoding="utf-8") as f:
            f.write(js)

        try:
            await ddnet_upload(self.session, "log", BytesIO(js.encode("utf-8")), testlog.name)
        except RuntimeError:
            failed = True

        for asset_type, assets in testlog.assets.items():
            for filename, url in assets.items():
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        log.error(
                            "Failed fetching asset %r: %s", filename, await resp.text()
                        )
                        failed = True
                        continue

                    bytes_ = await resp.read()

                with open(f"{testlog.DIR}/assets/{asset_type}s/{filename}", "wb") as f:
                    f.write(bytes_)

                try:
                    await ddnet_upload(self.session, asset_type, BytesIO(bytes_), filename)
                except RuntimeError:
                    failed = True
                    continue

        return not failed

    @tasks.loop(hours=1)
    async def auto_archive(self):
        now = datetime.now(timezone.utc)
        ann_channel = await self.bot.fetch_channel(Channels.ANNOUNCEMENTS)
        ann_history = [
            msg async for msg in ann_channel.history(
                after=now - timedelta(days=3)
            ) if by_releases_webhook(msg)
        ]
        recent_releases = {self.get_map_channel_from_ann(m.content) for m in ann_history}

        query = """
                SELECT channel_id
                FROM discordbot_waiting_maps
                WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL 60 DAY; \
                """

        records = await self.bot.fetch(query, fetchall=True)
        deleted_waiting_maps = [r[0] for r in records]

        to_archive = []
        for map_channel in self.bot.map_channels:
            map_channel = self.get_map_channel(map_channel)
            # keep the channel until its map is released, including a short grace period
            if map_channel.state in (MapState.TESTING, MapState.READY, MapState.RC) or map_channel in recent_releases:
                continue

            # don't tele waiting maps before 60 days have passed
            if map_channel.state is MapState.WAITING and map_channel.id not in deleted_waiting_maps:
                continue

            # make sure there is no active discussion going on
            # map authors with map releases receive a 2-week period for fixes which may affect the leaderboard
            recent_message = [msg async for msg in map_channel.history(limit=1, after=now - timedelta(days=14))]
            if recent_message:
                continue

            to_archive.append(map_channel)

        for map_channel in to_archive:
            testlog = await TestLog.from_map_channel(map_channel)
            archived = await self.archive_testlog(testlog)

            if archived:
                await map_channel.delete()
                log.info('Successfully auto-archived channel #%s', map_channel)
            else:
                log.error('Failed auto-archiving channel #%s', map_channel)

    @auto_archive.before_loop
    async def before_loop_auto_archive(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def update_scores(self):
        """|asyncio.task|
        Updates the topic of the TESTER channel with the top scores.
        """
        await update_scores_topic(self.bot)

    @update_scores.before_loop
    async def before_update_scores_topic(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != Guilds.DDNET:
            return

        if (map_channel := self.bot.map_channels.pop(channel.id, None)) is None:
            return

        try:
            entry = await anext(
                channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete),
                None
            )
        except discord.Forbidden:
            log.warning("Missing permissions to read audit logs.")
            return

        if entry and entry.target.id == channel.id and entry.user != self.bot.user:
            log.info(
                "Map testing channel %s (%s) was deleted by %s",
                channel.name, channel.id, entry.user
            )

        await self.bot.upsert(rm_mapinfo_from_db, map_channel.id, map_channel.id)
        await ddnet_delete(self.session, map_channel.filename)

    @commands.Cog.listener("on_message")
    async def handle_map_release(self, message: discord.Message):
        if not by_releases_webhook(message):
            return

        map_channel = self.get_map_channel_from_ann(message.content)
        if map_channel is None:
            return

        await map_channel.send(
            embed=MapReleased(
                map_channel,
                to_discord_timestamp(discord.utils.utcnow() + timedelta(weeks=2), style="F")
            )
        )
        await map_channel.set_state(state=MapState.RELEASED)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            self.bot.user,
            category="MapTesting/RELEASED",
            string=f"\"{map_channel.name}\" has been officially released."
        )
        await map_channel.changelog_paginator.update_changelog()

        # Technically not necessary, but doesn't hurt
        global_cooldown.update_cooldown(map_channel.id)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate(staff_only=True))
    @app_commands.command(
        name="twmap-edit", description="Edits a map according to the passed arguments")
    @app_commands.describe(
        options="Options, separate each option with a comma. Use --help option to see all available options.")
    async def twmap_edit(self, interaction: discord.Interaction, options: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        options = [option.strip() for option in options.split(",")]
        map_channel = self.get_map_channel(interaction.channel.id)  # noqa
        pins = await map_channel.pins()

        try:
            stdout, file = await Submission(pins[0]).edit_map(*options)
        except RuntimeError as e:
            await interaction.followup.send(f"{e}")
            return

        if stdout:
            stdout = f"```{stdout}```"

        if file is None:
            await interaction.followup.send(stdout)
        else:
            await map_channel.send(stdout, file=file)

            if interaction.response.is_done():  # noqa
                await interaction.delete_original_response()

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate(staff_only=False))
    @app_commands.command(
        name="optimize",
        description="Shortcut for twmap with the following arguments: --remove-everything-unused and --shrink-layers")
    async def optimize(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        args = ["--remove-everything-unused", "--shrink-tiles-layers"]
        stdout, file = await Submission((await interaction.channel.pins())[0]).edit_map(*args)

        await interaction.channel.send(
            content=f"Optimized version attached, {interaction.user.mention}. Changelog: \n```{stdout}```\n"
            if stdout
            else "Optimized version:",
            file=file,
            allowed_mentions=discord.AllowedMentions(users=False)
        )
        await interaction.delete_original_response()

    @app_commands.command(
        name="promote",
        description="Creates a private thread to discuss the promotion of a Trial Tester")
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.describe(trial_tester="@mention the trial tester to promote")
    async def create_thread(self, interaction: discord.Interaction, trial_tester: discord.Member):
        tester_c = self.bot.get_channel(Channels.TESTER_C)
        if interaction.channel.id != Channels.TESTER_C:
            await interaction.response.send_message(  # noqa
                f"This command can only be used in {tester_c.mention} channel.",
                ephemeral=True
            )
            return

        user_roles = [role.id for role in interaction.user.roles]
        if Roles.TRIAL_TESTER in user_roles:
            await interaction.response.send_message(  # noqa
                f"{trial_tester.global_name} is already a Tester."
            )

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        thread = await interaction.channel.create_thread(
            name=f"Promote {trial_tester.global_name}", message=None, invitable=False
        )
        await thread.send(
            f"<@&{Roles.TESTER}> <@&{Roles.TESTER_EXCL_TOURNAMENTS}>\n"
            f"{interaction.user.mention} suggests to promote {trial_tester.global_name} to Tester. Opinions?"
        )

        await interaction.followup.send(  # noqa
            f"<@{interaction.user.id}> your thread has been created: {thread.jump_url}",
            ephemeral=True,
        )

        log.info(
            f"{interaction.user} (ID: {interaction.user.id}) created a thread in {interaction.channel.name}"
        )

    @twmap_edit.error
    @create_thread.error
    async def on_app_command_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(
            error, (NotStaffError, NotTestingChannelError)
        ) or not isinstance(error, app_commands.CheckFailure):
            msg = error
        else:
            msg = "This is not a map channel."

        await interaction.response.send_message(msg, ephemeral=True)
        interaction.extras["error_handled"] = True

    @optimize.error
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = "This application command can only be used within the map testing category."
        else:
            msg = f"An unexpected error occurred: {error!r}"
            log.error(msg, exc_info=error)

        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)

        interaction.extras["error_handled"] = True

    async def validate_submission(self, isubm: InitialSubmission):
        try:
            isubm.validate()

            if self.get_map_channel(name=isubm.name):
                raise ValueError("A channel for this map already exists")

            released = await self.bot.fetch(fetch_map_from_db, isubm.name)
            if released:
                raise ValueError("A map with that name is already released")
        except ValueError as exc:
            await isubm.respond(exc)
            await isubm.set_state(SubmissionState.ERROR)
        else:
            await isubm.set_state(SubmissionState.VALIDATED)

    @commands.Cog.listener("on_raw_message_edit")
    async def handle_submission_edit(self, payload: discord.RawMessageUpdateEvent):
        # have to work with the raw data here to avoid unnecessary api calls
        data = payload.data
        if "author" in data and int(data["author"]["id"]) == self.bot.user.id:
            return

        if payload.channel_id != Channels.TESTING_SUBMIT:
            return

        if not (
                "attachments" in data
                and data["attachments"]
                and data["attachments"][0]["filename"].endswith(".map")
        ):
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = self.bot.get_message(
            payload.message_id
        ) or await channel.fetch_message(payload.message_id)

        if any(
                str(SubmissionState.PROCESSED) == reaction.emoji
                for reaction in message.reactions
        ):
            return

        isubm = InitialSubmission(self.bot, message)
        await self.validate_submission(isubm)

    @commands.Cog.listener("on_message")
    async def handle_submission(self, message: discord.Message):
        if not has_map(message):
            return

        if message.channel.id == Channels.TESTING_SUBMIT:
            await self.handle_initial_submission(message)
        else:
            await self.handle_map_channel_submission(message)

    async def handle_initial_submission(self, message: discord.Message):
        isubm = InitialSubmission(self.bot, message)
        await self.validate_submission(isubm)

    async def handle_map_channel_submission(self, message: discord.Message):
        map_channel = self.get_map_channel(message.channel.id)
        if map_channel is None:
            return

        subm = Submission(message)
        if not await self.validate_filename(map_channel, subm):
            return

        await self.process_submission(map_channel, subm, message)

    @staticmethod
    async def validate_filename(map_channel, subm):
        if map_channel.filename != str(subm):
            await subm.message.reply(embed=UnmatchedFilename, mention_author=False)
            return False
        return True

    async def process_submission(self, map_channel, subm, message):
        by_mapper = str(message.author.id) in map_channel.mapper_mentions
        if by_mapper:
            await self.handle_mapper_submission(map_channel, subm)
        elif is_testing_staff(message.author) or message.author == self.bot.user:
            await upload_submission(self.session, subm)
        else:
            await subm.set_state(SubmissionState.VALIDATED)

        await self.update_changelog(map_channel, subm, message)
        await self.check_debug(subm, message)
        await self.check_changelog_requirement(message)

    async def handle_mapper_submission(self, map_channel, subm):
        if map_channel.state in (MapState.WAITING, MapState.READY):
            await self.reset_map_state(map_channel)
        elif map_channel.state == MapState.RELEASED:
            await map_channel.send(
                "Post-release updates need to be uploaded manually. "
                "Please reach out to an administrator."
            )
        await upload_submission(self.session, subm)

    async def reset_map_state(self, map_channel):
        new_state = MapState.TESTING if map_channel.state == MapState.WAITING else MapState.RC
        set_by = self.bot.user.mention if new_state == MapState.RC else None
        await map_channel.set_state(state=new_state, set_by=set_by)
        global_cooldown.update_cooldown(map_channel.id)
        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            self.bot.user,
            category="MapTesting/AUTO_RESET",
            string=f"\"{map_channel.name}\" has been moved back to TESTING due to channel updates."
        )
        await map_channel.changelog_paginator.update_changelog()

    @staticmethod
    async def update_changelog(map_channel: MapChannel, subm: InitialSubmission, message: discord.Message):
        if subm.state == SubmissionState.VALIDATED:
            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                message.author,
                category="MapTesting/VERIFY_UPDATE",
                string=f"\"{map_channel.name}\" has received new map updates but need to be verified first."
            )
            await map_channel.changelog_paginator.update_changelog()
            await message.reply(embed=UnmatchedSubmOwner, mention_author=False)  # type: ignore
        elif subm.state == SubmissionState.UPLOADED:
            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                message.author,
                category="MapTesting/UPDATED",
                string=f"\"{map_channel.name}\" has received new map updates."
            )
            await map_channel.changelog_paginator.update_changelog()

    @staticmethod
    async def check_debug(subm: InitialSubmission, message: discord.Message):
        if not await debug_check(subm, message):
            await subm.message.add_reaction("👌")

    @staticmethod
    async def check_changelog_requirement(message: discord.Message):
        if not message.content and not message.author.bot and len(message.attachments) < 2:
            await message.reply(embed=MissingChangelog(message.author), mention_author=False)

    @commands.Cog.listener("on_raw_reaction_add")
    async def handle_submission_approve(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != str(SubmissionState.VALIDATED):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel.id == Channels.TESTING_SUBMIT:
            initial = True
        elif is_testing_channel(channel):
            initial = False
        else:
            return

        user = channel.guild.get_member(payload.user_id)
        if not is_testing_staff(user):
            return

        message = self.bot.get_message(
            payload.message_id
        ) or await channel.fetch_message(payload.message_id)
        if not has_map(message):
            return

        if initial:
            if message.id in self._active_submissions:
                return

            isubm = InitialSubmission(self.bot, message)
            try:
                isubm.validate()
            except ValueError:
                return

            self._active_submissions.add(message.id)
            subm = await isubm.process()
            await isubm.set_state(SubmissionState.PROCESSED)
            self.bot.map_channels[isubm.map_channel.id] = isubm.map_channel
            self._active_submissions.discard(message.id)

        else:
            subm = Submission(message)
            if not await debug_check(subm, message):
                await subm.message.add_reaction("👌")

        await upload_submission(self.session, subm)
        log.info(
            "%s approved submission %r in channel #%s", user, subm.filename, channel
        )

