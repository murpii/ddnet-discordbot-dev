import random
import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_staff

from constants import Guilds, Roles

class AutoResponses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tickets = bot.ticket_manager.tickets

    # Command group limited to the DDNet guild
    add = app_commands.Group(
        name="add",
        description="Adds (duh) an item to the Database",
        guild_only=True,
        guild_ids=[Guilds.DDNET]
    )

    @add.command(name="auto-response", description="Auto-response")
    @commands.has_permissions(administrator=True)
    async def add_word_response(self, interaction: discord.Interaction, string: str, response: str):
        """
        This command allows to define a word that, when detected, will trigger a specific response to be sent to users.
        The word and its associated response are stored in the database for future use.

        Args:
            interaction (discord.Interaction): The interaction object representing the command invocation.
            string (str): The string that triggers the response.
            response (str): The response that is sent to the user.

        Examples:
            /auto-response "hello" "Hi there! How can I help you?"
        """
        query = "INSERT INTO discordbot_auto_responses (`Trigger`, `Response`) VALUES (%s, %s)"
        await self.bot.upsert(query, string, response)
        await interaction.response.send_message(f'"{string}" and response "{response}" added to the database.')

    @add.command(name="banned-words")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        string="The string that triggers the response.", response="The response that is sent to the user.")
    async def add_blacklist_word(self, interaction: discord.Interaction, string: str, response: str):
        """
           This command allows to specify a trigger word that,
           when detected, will prompt a specific response to be sent to users.
           The word and its associated response are stored in the database for future reference.

           Args:
               interaction (discord.Interaction): The interaction object representing the command invocation.
               string (str): The string that triggers the response.
               response (str): The response that is sent to the user.

           Examples:
               /banned-words "bad word" "Please refrain from using that language."
           """
        query = "INSERT INTO discordbot_wordlist (`Trigger`, `Response`) VALUES (%s, %s)"
        await self.bot.upsert(query, string, response)
        await interaction.response.send_message(f'"{words}" added to the blacklist with response "{response}".') # noqa

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        """
        Listens for incoming messages and responds or deletes them based on configured auto-responses and blacklisted words.

        Args:
            message (discord.Message): The message object representing the incoming message.
        """

        if message.author.bot or message.guild is None or message.guild.id != Guilds.DDNET:
            return

        query = "SELECT `Trigger`, `Response` FROM discordbot_auto_responses"
        auto_responses = await self.bot.fetch(query, fetchall=True)
        blacklist_query = "SELECT `Trigger`, `Response` FROM discordbot_wordlist"
        blacklist_words = await self.bot.fetch(blacklist_query, fetchall=True)
        message_responded = False

        for words, response in auto_responses:
            words_list = words.lower().split(", ")
            if any(word in message.content.lower() for word in words_list):
                responses = response.split(", ")
                await message.reply(random.choice(responses))
                message_responded = True
                break

        if message_responded:
            return

        # Check for blacklisted words
        for words, blacklist_response in blacklist_words:
            if isinstance(message.channel, discord.DMChannel):
                break

            # Don't do anything in ticket channels or if member is a discord staff member
            if (
                message.channel.id in self.tickets
                or is_staff(message.author, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR])
            ):
                break

            if words.lower() in message.content.lower():
                try:
                    await message.delete()
                    await message.author.send(blacklist_response)
                    break
                except discord.Forbidden:
                    # In case the bot doesn't have permissions to DM the user
                    await message.channel.send(
                      f"{message.author.mention}, your message contained forbidden words."
                    )
                    break


async def setup(bot):
    await bot.add_cog(AutoResponses(bot))
