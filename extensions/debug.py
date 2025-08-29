from datetime import datetime
import sqlite3

import discord
from discord.ext import commands

from extensions.map_testing.checklist import ChecklistView


class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sessions = bot.session_manager
        self.ticket_manager = bot.ticket_manager

    @commands.command()
    async def sessions(self, ctx: commands.Context):
        await ctx.send(self.sessions)

    @commands.command()
    async def map_channels(self, ctx: commands.Context):
        print(self.bot.map_channels)
    
    @commands.command()
    async def tickets(self, ctx: commands.Context):
        print(self.ticket_manager.tickets)

    @commands.command()
    async def fix_tags(self, ctx):
        channel = ctx.guild.get_channel(1222336261000396961)
        tag_id_eval = 1366449378088325193
        tag_id_open_app = 1366449341081976862
        tag_id_to_remove = 1366449341081976862

        archived_threads = []
        async for thread in channel.archived_threads(limit=None):
            archived_threads.append(thread)

        all_threads = list(channel.threads) + archived_threads

        for thread in all_threads:
            if not isinstance(thread, discord.Thread):
                continue

            thread_tags = thread.applied_tags
            tag_ids = [tag.id for tag in thread_tags]

            if tag_id_eval in tag_ids and tag_id_open_app in tag_ids and tag_id_to_remove in tag_ids:
                new_tags = [tag for tag in thread_tags if tag.id != tag_id_to_remove]

                # Make sure we don't exceed 5 tags (Discord limit)
                new_tags = new_tags[:5]

                needs_unarchive = thread.archived
                # needs_unlock = thread.locked

                try:
                    if needs_unarchive:
                        await thread.edit(archived=False)

                    await thread.edit(applied_tags=new_tags)
                    await ctx.channel.send(f"Updated thread: {thread.name}")

                    if needs_unarchive:
                        await thread.edit(archived=True, locked=True)
                except discord.HTTPException as e:
                    print(f"Failed to update thread {thread.name}: {e}")

    @commands.command()
    async def count_threads(self, ctx: commands.Context, id: int):
        channel = ctx.guild.get_channel(1222336261000396961)
        tag_id_open_app = id
        count = 0

        active_threads = list(channel.threads)
        archived_threads = []
        async for thread in channel.archived_threads(limit=None):
            archived_threads.append(thread)
        all_threads = active_threads + archived_threads

        for thread in all_threads:
            if not isinstance(thread, discord.Thread):
                continue

            thread_tag_ids = [tag.id for tag in thread.applied_tags]

            if tag_id_open_app in thread_tag_ids:
                count += 1

        tag = discord.utils.get(channel.available_tags, id=tag_id_open_app)
        tag_name = tag.name if tag else "Unknown Tag"

        await ctx.send(f"Total amount of threads with tag '{tag_name}': {count}")

    @commands.command()
    async def checklist(self, ctx):
        view = ChecklistView()
        embed = view.generate_embed()
        await ctx.channel.send(embed=embed, view=view)

    @commands.command()
    async def ban_list(self, ctx):
        """
        Reads bans from a SQLite database.

        Returns:
            List[dict]: List of bans with keys: ip, name, expires, reason, moderator
        """
        bans_list = []

        conn = sqlite3.connect("data/ticket-system/db.sqlite")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT ip, name, expires, reason, moderator
            FROM bans
            """
        )

        rows = cursor.fetchall()
        for ip, name, expires, reason, moderator in rows:
            if isinstance(expires, str):
                expires_dt = datetime.fromisoformat(expires)
            else:
                expires_dt = expires

            bans_list.append({
                "ip": ip,
                "name": name,
                "expires": expires_dt,
                "reason": reason,
                "moderator": moderator
            })

        conn.close()
        print(bans_list)


async def setup(bot):
    await bot.add_cog(Debug(bot))
