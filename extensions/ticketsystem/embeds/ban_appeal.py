import discord

from extensions.ticketsystem.manager import Ticket
from utils.text import slugify2
from utils.profile import PlayerProfile

class BanAppealEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="Ban appeal", colour=2210995)
        embed.add_field(
            name="",
            value=f"Hello {user.mention}, \n\n"
            "When writing your appeal, please aim to be clear and straightforward in your explanation. "
            "It's important to be honest about what occurred and take ownership for any actions that may have "
            "resulted in your ban. "
            "Additionally, if you have any evidence, such as screenshots or chat logs that may support your "
            "case, please include it in your appeal.",
        )
        return embed


class BanAppealInfoEmbed(discord.Embed):
    def __new__(cls, ticket: Ticket, profile: PlayerProfile = None):
        if ticket and profile:
            embed = discord.Embed(title="Provided Infos", colour=2210995)
            embed.add_field(
                name="Public IPv4 Address:",
                value=f"```{ticket.appeal_data.address}```**{ticket.appeal_data.dnsbl}**",
                inline=True
            )
            embed.add_field(
                name="In-game Name:",
                value=f"```{ticket.appeal_data.name}```"
                      f"**[Profile](https://ddnet.org/players/{slugify2(profile.name)})** \n"
                      f"Total Points: {profile.points} \n"
                      f"Favorite Server: {profile.favorite_server}",
                inline=True
            )
            embed.add_field(
                name="Ban Reason:",
                value=f"{ticket.appeal_data.reason}",
                inline=False
            )
            embed.add_field(
                name="Appeal Statement:",
                value=f"{ticket.appeal_data.appeal}",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="Infos required:",
                description=f"In order to begin your ban appeal,"
                            f" we will need a few important pieces of information from you. \n\n"
                            f"**Please provide us with:** \n"
                            f"1. Your public IPv4 Address from https://ipinfo.io/ip. \n"
                            f"2. Your in-game player name. \n"
                            f"3. The reason you've been banned for.",
                colour=discord.Colour.yellow()
            )
        return embed