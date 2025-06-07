import discord

class FollowUpEmbed(discord.Embed):
    def __new__(cls):
        embed = discord.Embed(title="", colour=16776960)
        embed.add_field(
            name="",
            value="If you wish to close this ticket or opened this ticket by mistake, "
            "use either the close button below or type `/close`.",
            inline=False,
        )
        return embed