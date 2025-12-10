import asyncio
import contextlib
import discord
from discord import app_commands
from discord.ext import commands
from typing import Sequence, Union

from constants import Guilds, Forums, ForumTags, Channels
from utils.checks import ddnet_only


def is_questions_thread():
    def predicate(ctx: commands.Context) -> bool:
        return (
                isinstance(ctx.channel, discord.Thread)
                and ctx.channel.parent_id == Forums.QUESTIONS
        )

    return commands.check(predicate)


def is_thread(ctx) -> bool:
    return isinstance(ctx.channel, discord.Thread)


class SolvedReactionCheck:
    def __init__(self, message_id: int, owner: Union[discord.Member, discord.User]):
        self.message_id = message_id
        self.owner = owner

    def __call__(self, reaction: discord.Reaction, member: Union[discord.Member, discord.User]) -> bool:
        return (
                reaction.message.id == self.message_id and
                str(reaction.emoji) == "✅" and
                member == self.owner
        )


class Forum(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.solved_prompts: dict[int, discord.Message] = {}

    @staticmethod
    def owner_exempt_channel_cooldown(rate, per):
        cooldown = commands.CooldownMapping.from_cooldown(rate, per, commands.BucketType.channel)  # type: ignore

        async def predicate(ctx):
            if not is_thread(ctx):
                return False
            thread = ctx.channel
            if ctx.author == thread.owner:
                return True
            bucket = cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            if retry_after:
                raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.channel)  # type: ignore
            return True

        return commands.check(predicate)

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

    @commands.command(name="solved", aliases=["is_solved"])
    @owner_exempt_channel_cooldown(1, 300)
    @is_questions_thread()
    async def solved(self, ctx: commands.Context) -> None:
        """Marks a thread in the #questions forum as solved."""
        if not is_thread(ctx):
            return

        thread = ctx.channel
        owner = thread.owner

        if ctx.author == owner:
            self.solved.reset_cooldown(ctx)
            old_prompt = self.solved_prompts.pop(thread.id, None)
            if old_prompt:
                try:
                    await old_prompt.delete()
                except discord.NotFound:
                    pass

            await ctx.message.add_reaction("✅")
            await ctx.channel.send(content="Marked thread as solved.")
            await self.mark_as_solved(thread, ctx.author)
            return

        await ctx.message.delete()
        prompt = await ctx.send(
            f"{owner.mention} has your question been answered?\n"
            f"Click on the checkmark reaction to mark this thread as solved or use the command $solved."
        )
        await prompt.add_reaction("✅")
        self.solved_prompts[thread.id] = prompt

        try:
            check = SolvedReactionCheck(prompt.id, owner)
            await self.bot.wait_for("reaction_add", timeout=300.0, check=check)
        except asyncio.TimeoutError:
            await prompt.edit(content="Timed out waiting for a response. Not marking as resolved.")
        else:
            try:
                await prompt.edit(content="Marked thread as solved.")
            except discord.NotFound:
                pass

            try:
                await ctx.message.delete()
            except discord.NotFound:
                pass
            await self.mark_as_solved(thread, owner)
        finally:
            self.solved_prompts.pop(thread.id, None)

    @solved.error
    async def on_solved_error(self, ctx, error: commands.CommandOnCooldown) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.message.delete()
            await ctx.author.send(content="You've been rate-limited.", delete_after=60)
            return

    @commands.Cog.listener("on_thread_create")
    async def quality_control(self, thread: discord.Thread) -> None:
        if thread.parent_id != Forums.QUESTIONS:
            return

        if len(thread.name) <= 6:
            em = discord.Embed(
                title=f"Low quality title.",
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

    @commands.hybrid_command(
        name="create_thread",
        with_app_command=True,
        description="Makes the bot create a thread in a given forum.",
        usage="$create_thread <ForumID> <ThreadName> <Text>")
    @commands.check(ddnet_only)
    @commands.has_permissions(ban_members=True)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        forum_channel_id="The forums channel identifier",
        thread_name="The thread title",
        initial_message="The initial message of the thread")
    async def create_thread(self, ctx, forum_channel_id: int, thread_name: str, *, initial_message: str):
        forum_channel = self.bot.get_channel(forum_channel_id)
        if not isinstance(forum_channel, discord.ForumChannel):
            await ctx.send("The provided channel ID is not a forum channel.")
            return

        try:
            await forum_channel.create_thread(name=thread_name, content=initial_message)
            await ctx.send(f'Thread "{thread_name}" created successfully.')
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")


async def setup(bot: commands.bot):
    await bot.add_cog(Forum(bot))
