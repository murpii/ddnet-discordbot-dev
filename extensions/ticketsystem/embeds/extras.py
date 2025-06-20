import discord

class FollowUpEmbed(discord.Embed):
    """Embed for providing follow-up instructions on ticket closure.
    This embed informs users how to close a ticket if it was opened by mistake or is no longer needed.
    """
    def __new__(cls):
        embed = discord.Embed(title="", colour=16776960)
        embed.add_field(
            name="",
            value="If you wish to close this ticket or opened this ticket by mistake, "
            "use either the close button below or type `/close`.",
            inline=False,
        )
        return embed