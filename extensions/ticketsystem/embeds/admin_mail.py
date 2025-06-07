import discord

class AdminMailEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="Admin-Mail", colour=2210995)
        embed.add_field(
            name="",
            value=f"Hello {user.mention}, \n\n"
            "please describe your request or issue in as much detail as possible. "
            "The more information you provide, the better we can understand and address your "
            "specific concern. Feel free to include any relevant background, specific requirements, "
            "or any other details that can help us assist you effectively. Your thorough description "
            "will enable us to provide you with the most appropriate help.",
            inline=False,
        )
        return embed