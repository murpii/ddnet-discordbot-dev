import discord


class ComplaintEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="Complaint", colour=2210995)
        embed.add_field(
            name="",
            value=f"Hello {user.mention}, \n\n"
                  "approach the process with clarity and objectivity. "
                  "Here are some steps to help you write an effective complaint: \n\n"
                  "Clearly pinpoint the incident or behavior that has caused you concern. "
                  "Be specific about what happened, when it occurred, and who was involved. "
                  "This will provide a clear context for your complaint. "
                  "Ensure that your complaint is based on objective facts rather than "
                  "personal biases or general dissatisfaction. "
                  "Stick to the specific incident or behavior you are addressing and "
                  "avoid making assumptions or generalizations. \n\n"
                  "Also, upload relevant evidence or supporting information that can strengthen your complaint. "
                  "This may include screenshots, message logs or in-game demos.",
            inline=False,
        )
        return embed


class ComplaintInfoEmbed(discord.Embed):
    def __new__(cls, user):
        return discord.Embed(
            title="Requirements",
            description="Upload relevant evidence or supporting information that can strengthen your complaint. "
                        "This may include screenshots, message logs or in-game demos.",
            colour=2210995,
        )
