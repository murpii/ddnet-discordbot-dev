import logging

import discord
from discord.ext import commands

from constants import Guilds
from extensions.ticketsystem.utils import fetch_rank_from_demo

log = logging.getLogger("tickets")


class TicketListeners(commands.Cog):
    """Holds the ticket system's gateway event listeners"""

    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.ticket_manager = bot.ticket_manager

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.ticket_manager.load_tickets()

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.TextChannel, after: discord.TextChannel):
        if after.guild.id != Guilds.DDNET:
            return

        before_cat = before.category.name if before.category else None
        after_cat = after.category.name if after.category else None

        before_c = self.ticket_manager.is_ticket_category(before.category)
        after_c = self.ticket_manager.is_ticket_category(after.category)

        if before.id not in self.ticket_manager.tickets and not after_c:
            return

        if before.id in self.ticket_manager.tickets and not after_c:
            await self.ticket_manager.del_ticket(after)
            log.info(
                f"Ticket Channel '{after.name}' has been detached from '{before_cat or 'No category'}' "
                f"to '{after_cat or 'No category'}' and is no longer considered as a ticket."
            )
        elif not before_c:
            try:
                await self.ticket_manager.create_ticket(after)
                log.info(
                    f"Ticket Channel '{after.name}' has been moved from '{before_cat or 'No category'}' "
                    f"to '{after_cat or 'No category'}' and is now considered as a ticket."
                )
            except ValueError as e:
                log.error(e)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != Guilds.DDNET:
            return

        try:
            entry = await anext(
                channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete), None
            )
            if not entry or entry.user.bot:
                return
            ticket = self.ticket_manager.tickets[channel.id]
        except discord.Forbidden:
            log.warning("Missing permissions to read audit logs.")
            return
        except KeyError:
            return

        await self.ticket_manager.del_ticket(channel=channel, ticket=ticket)
        log.info(
            "Ticket channel named %s was manually removed by %s.",
            channel.name, entry.user
        )

    @commands.Cog.listener("on_message")
    async def del_system_pin_message(self, message: discord.Message):
        if (
                isinstance(message.channel, discord.TextChannel)
                and (
                message.guild.id == Guilds.DDNET
                and self.ticket_manager.is_ticket_category(message.channel.category)
                and message.type is discord.MessageType.pins_add
        )
        ):
            await message.delete()

    @commands.Cog.listener('on_message')
    async def fetch_demo_rank(self, message: discord.Message):
        if (
                not isinstance(message.channel, discord.TextChannel)
                or not message.guild
                or message.guild.id != Guilds.DDNET
                or not message.channel.category
                or not self.ticket_manager.is_ticket_category(message.channel.category)
                or not message.attachments
        ):
            return

        ranks = await fetch_rank_from_demo(self.bot, message, self.session)
        if ranks:
            response = "✅ Found record for:\n" + "\n".join(
                f"- `{demo}` (Timestamp: `{timestamp}`)" for demo, timestamp in ranks
            )
            await message.channel.send(response)
