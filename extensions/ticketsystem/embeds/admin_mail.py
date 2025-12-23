import discord

from constants import Channels


# THIS IS NO LONGER USED -- REPLACED BY views/containers/admin_mail.py
class AdminMailEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="Admin-Mail", colour=2210995)
        embed.add_field(
            name="",
            value=f"Hello {user.mention},\n"
                  "describe your request or issue in as much detail as possible.\n"
                  "The more information you provide, the better we can understand and address your specific concern.\n"
                  "Feel free to include any relevant background, specific requirements, "
                  "or any other details that can help us assist you effectively. Your thorough description "
                  "will enable us to provide you with the most appropriate help.",
            inline=False,
        )
        return embed


class AdminMailInfoEmbed(discord.Embed):
    def __new__(cls):
        return discord.Embed(
            title="Note",
            description=f"For technical issues, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead.",
            colour=2210995,
        )
