import random
import discord
from constants import Roles


# THIS IS NO LONGER USED -- REPLACED BY views/containers/report.py
class ReportEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="How to properly file a report", color=0xFF0000)
        embed.add_field(
            name=f"",
            value=f"Hello {user.mention}, thanks for reaching out!",
            inline=False,
        )
        embed.add_field(
            name="Follow this Format:",
            value="```prolog\n1. Copy the Server Info by pressing ESC -> Server Info -> Copy Info in-game.```"
                  "```prolog\n2. Paste the Server Info you copied, by either using the keyboard shortcut "
                  'CTRL+V or by right-clicking and selecting "Paste".```'
                  "```prolog\n3. Describe the Problem you are having on the server.```",
        )
        embed.add_field(
            name="What not to report:",
            value="Do NOT file reports about server lags or DoS attacks. \n\n"
                  'Do NOT send moderator complaints here, create a "Complaint" ticket instead. \n\n'
                  "Do NOT add unnecessary videos or demos to your report. \n\n"
                  "Do NOT report players faking a player other than yourself.",
            inline=True,
        )
        return embed


class ReportInfoEmbed(discord.Embed):
    def __new__(cls, guild: discord.Guild):
        staff_members = [
            member for member in guild.members
            if any(role.id in {Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR} for role in member.roles)
        ]
        return discord.Embed(
            title="Example",
            description="```DDNet GER10 [ger10.ddnet.org whitelist] - Moderate \n"
                        "Address: ddnet://37.230.210.231:8320 \n"
                        f"My IGN: {random.choice(staff_members).display_name}\n\n"
                        f"A player named {random.choice(staff_members).display_name} keeps blocking our group! "
                        "We have tried ban-voting him but vote never succeeds.```",
            color=2210995,
        )
