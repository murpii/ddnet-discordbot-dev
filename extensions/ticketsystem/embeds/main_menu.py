import discord
from constants import Channels


class MainMenuEmbed(discord.Embed):
    def __new__(cls):
        embed = discord.Embed(
            title="🎫 Welcome to our ticket system!",
            description="If you've been banned and want to appeal the decision, need to request a "
                        "rename, or have a complaint about the behavior of other users or moderators, "
                        "you can create a ticket using the buttons below.",
            colour=34483,
        )
        embed.add_field(
            name="Report",
            value="If you encounter any behavior within the game that violates our rules, such as "
                  "**blocking, fun-voting, cheating, or any other form of misconduct**, you can open a "
                  "ticket in this given category to address the problem. \n\n"
                  "Note:\n"
                  "Refrain from creating a ticket for server issues like DoS attacks or in-game lags",
            inline=False,
        )
        embed.add_field(
            name="Rename Request",
            value="Requirements:\n"
                  "- The original name should have 3k or more points on it \n"
                  "- Your last rename should be __at least one year ago__ \n"
                  "- You must be able to provide proof of owning the points being moved \n"
                  "- The names shouldn't be banned \n"
                  "- If you request a rename and then later change your mind, know that it won't be reverted until at "
                  "least one year has passed. Think carefully.",
            inline=False,
        )
        embed.add_field(
            name="Ban Appeal",
            value="If you've been banned unfairly from our in-game servers, you are eligible to appeal the"
                  " decision. Please note that ban appeals are not guaranteed to be successful, and our "
                  "team reserves the right to deny any appeal at their discretion. \n\n"
                  "Note: Only file a ticket if you've been banned across all servers or from one of "
                  "our moderators.",
            inline=False,
        )
        embed.add_field(
            name="Staff Complaint",
            value="If a staff member's behavior in our community has caused you concern, you have the "
                  "option to make a complaint. Please note that complaints must be "
                  "based on specific incidents or behaviors and not on personal biases or general dissatisfaction.",
            inline=False,
        )
        embed.add_field(
            name="Admin-Mail (No technical support)",
            value="If you have an issue or request related to administrative matters, you can use this option. "
                  "Explain your issue or request in detail and we will review it and assist you accordingly. \n\n"
                  f"**Note: For technical issues or bugs, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead.**",
            inline=False,
        )
        return embed


class MainMenuFollowUp(discord.Embed):
    def __new__(cls):
        return discord.Embed(
            title="If you create tickets with no valid reason or solely to troll, "
                  "you will be given a timeout.",
            description="",
            colour=16776960,
        )
