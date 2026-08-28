import asyncio
import contextlib
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Sequence, Union, TYPE_CHECKING

from constants import Guilds, Forums, ForumTags, Channels

if TYPE_CHECKING:
    from bot import DDNet


def is_questions_thread():
    def predicate(interaction: discord.Interaction) -> bool:
        return (
                isinstance(interaction.channel, discord.Thread)
                and interaction.channel.parent_id == Forums.QUESTIONS
        )

    return app_commands.check(predicate)


def solved_cooldown(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    """The thread owner can always mark their own thread, everyone else waits."""
    thread = interaction.channel
    if isinstance(thread, discord.Thread) and interaction.user.id == thread.owner_id:
        return None
    return app_commands.Cooldown(1, 300)


class SolvedReactionCheck:
    def __init__(self, message_id: int, owner_id: int):
        self.message_id = message_id
        self.owner_id = owner_id

    def __call__(self, reaction: discord.Reaction, member: Union[discord.Member, discord.User]) -> bool:
        return (
                reaction.message.id == self.message_id and
                str(reaction.emoji) == "✅" and
                member.id == self.owner_id
        )


class Forum(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.solved_prompts: dict[int, discord.Message] = {}

    @commands.Cog.listener("on_thread_create")
    async def pin_initial_message(self, thread: discord.Thread) -> None:
        """Pins the first message sent in any thread."""
        if (
                thread.guild.id != Guilds.DDNET
                or thread.category.id in [
            Channels.CAT_TESTING,
            Channels.CAT_WAITING,
            Channels.CAT_EVALUATED,
        ]
        ):
            return

        # thread.starting_message doesn't work for some reason, so I just simply use history instead
        async for msg in thread.history(limit=1, oldest_first=True):
            if thread.archived:  # can't do it earlier, discord api race conditions...
                return
            with contextlib.suppress(Exception):
                await msg.pin()

        # moderator application specific
        if thread.parent_id == Forums.MODERATOR_APPS:
            await thread.send(
                "Make sure to read <#1222337448823099443> and adjust your application accordingly."
            )

    @staticmethod
    async def mark_as_solved(thread: discord.Thread, user: Union[discord.User, discord.Member]) -> None:
        tags: Sequence[discord.ForumTag] = thread.applied_tags

        if all(tag.id != ForumTags.SOLVED for tag in tags):
            tags.append(discord.Object(id=ForumTags.SOLVED))  # type: ignore

        await thread.edit(
            locked=True,
            archived=True,
            applied_tags=tags[:5],
            reason=f"Marked as solved by {user} (ID: {user.id})",  # audit log entry
        )

    @app_commands.command(
        name="solved",
        description="Marks a thread in the questions forum as solved"
    )
    @app_commands.guilds(Guilds.DDNET)
    @is_questions_thread()
    @app_commands.checks.dynamic_cooldown(
        solved_cooldown, key=lambda interaction: interaction.channel_id
    )
    async def solved(self, interaction: discord.Interaction) -> None:
        thread = interaction.channel

        if interaction.user.id == thread.owner_id:
            if old_prompt := self.solved_prompts.pop(thread.id, None):
                with contextlib.suppress(discord.NotFound):
                    await old_prompt.delete()
            await interaction.response.send_message("Marked thread as solved.")
            await self.mark_as_solved(thread, interaction.user)
            return

        await interaction.response.send_message(
            "Asked the thread owner to confirm.", ephemeral=True
        )
        prompt = await thread.send(
            f"<@{thread.owner_id}> has your question been answered?\n"
            f"Click on the checkmark reaction to mark this thread as solved, or use /solved."
        )
        await prompt.add_reaction("✅")
        self.solved_prompts[thread.id] = prompt

        try:
            check = SolvedReactionCheck(prompt.id, thread.owner_id)
            _, member = await self.bot.wait_for("reaction_add", timeout=300.0, check=check)
        except asyncio.TimeoutError:
            await prompt.edit(content="Timed out waiting for a response. Not marking as resolved.")
        else:
            with contextlib.suppress(discord.NotFound):
                await prompt.edit(content="Marked thread as solved.")
            await self.mark_as_solved(thread, member)
        finally:
            self.solved_prompts.pop(thread.id, None)

    @solved.error
    async def on_solved_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = "You've been rate-limited."
        elif isinstance(error, app_commands.CheckFailure):
            message = "This only works inside a thread in the questions forum."
        else:
            raise error

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @commands.Cog.listener("on_thread_create")
    async def quality_control(self, thread: discord.Thread) -> None:
        if thread.parent_id != Forums.QUESTIONS:
            return

        if len(thread.name) <= 6:
            em = discord.Embed(
                title="Low quality title.",
                description=f"{thread.owner.mention}\n"
                            f"Your thread has been automatically closed due to a potentially low quality title. "
                            "Your title should be descriptive of the question you are having.\n\n"
                            "Remake your thread with a new and more descriptive title.",
                colour=discord.Colour.yellow(),
            )
            await thread.send(embed=em)
            await thread.edit(archived=True, locked=True, reason="Low quality title.")
            return

        message = thread.get_partial_message(thread.id)
        with contextlib.suppress(discord.HTTPException):
            await message.pin()

    @app_commands.command(
        name="create_thread",
        description="Makes the bot create a thread in a given forum."
    )
    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        forum="The forum to create the thread in",
        thread_name="The thread title",
        initial_message="The initial message of the thread")
    async def create_thread(
        self,
        interaction: discord.Interaction,
        forum: discord.ForumChannel,
        thread_name: str,
        initial_message: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            await forum.create_thread(name=thread_name, content=initial_message)
        except discord.HTTPException as error:
            await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
            return

        await interaction.followup.send(
            f'Thread "{thread_name}" created successfully.', ephemeral=True
        )


async def setup(bot: "DDNet"):
    await bot.add_cog(Forum(bot))
