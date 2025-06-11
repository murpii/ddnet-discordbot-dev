import discord
from utils.text import slugify2
from utils.profile import PlayerProfile


class RenameEmbed(discord.Embed):
    def __new__(cls, user):
        embed = discord.Embed(title="Player Rename", colour=2210995)
        embed.add_field(
            name="",
            value=f"Hello {user.mention}, \n\n"
            "To initiate the process of moving your in-game points to a different name, \n"
            "we require some essential information from you.",
            inline=False)
        embed.add_field(
            name="Kindly provide answers to the following questions:",
            value="* Have you ever received a rename before? \n"
            "  - If yes, by whom? \n"
            "* To validate the ownership of the points being transferred, "
            "we require you to provide us verifiable evidence of ownership. \n"
            "  - We accept proof in form of old demo files that contain finishes done on DDNet. "
            "The demo files directory can be found in your config directory. "
            "Use $configdir if you're unsure where that is. \n"
            "  - Alternatively, if you have any personal connections to one of our staff members, "
            "you can ask them to vouch for your credibility.",
            inline=False)
        return embed


class RenameInfoEmbed(discord.Embed):
    def __new__(cls, profile_old: PlayerProfile = None, profile_new: PlayerProfile = None):
        if profile_old and profile_new:
            embed = discord.Embed(title="Provided Infos", colour=2210995)
            embed.add_field(
                name="",
                value=f"**[Current Name](https://ddnet.org/players/{slugify2(profile_old.name)})**\n"
                      f"```{profile_old.name}```"
                      f"Points: `{profile_old.points or 0}` \n"
                      f"Last Finish: `{profile_old.latest_finish or 'None'}` \n"
                      f"First Finish: `{profile_old.first_finish or 'None'}`",
                inline=True
            )
            embed.add_field(
                name="",
                value=f"**[New Name](https://ddnet.org/players/{slugify2(profile_new.name)})**\n"
                      f"```{profile_new.name}```"
                      f"Points: `{profile_new.points or 0}`\n"
                      + (
                          f"\tLast Finish: `{profile_new.latest_finish or 'None'}`\n"
                          f"First Finish: `{profile_new.first_finish or 'None'}`\n"
                          if profile_new.points else ''
                      ),
                inline=True
            )
            return embed
        else:
            return discord.Embed(
                title="Additional Infos Required:",
                description="In addition to the required infos above we need to know:\n"
                            "- Your old name \n"
                            "- Your desired new name \n",
                colour=2210995
            )