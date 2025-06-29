import discord
from utils.text import slugify2
from utils.profile import PlayerProfile


class RenameEmbed(discord.Embed):
    """
    Embed for guiding users through the player rename process.
    This embed provides instructions and required information for users who wish to move their in-game points to a different name.
    """

    def __new__(cls, user: discord.abc.User):
        embed = discord.Embed(
            title="Player Rename Request",
            colour=2210995,
            description=f"Hi **{user.mention}**,\n"
                        f"to transfer your in-game points to a new name, we need a few details first."
        )

        embed.add_field(
            name="Step 1: Past Renames",
            value="1. Have you ever received a rename before?\n"
                  "  - If yes, please mention who processed it.",
            inline=False
        )

        embed.add_field(
            name="Step 2: Proof of Ownership",
            value="To verify that you own the points being moved, we accept **one** of the following:\n\n"
                  "**1.** Demo files showing your finishes on DDNet (check your `demos` folder in the config directory, "
                  "use `$configdir` if you're unsure where that is).\n\n"
                  "**2.** A personal vouch from a known DDNet staff member confirming your identity.",
            inline=False
        )

        embed.set_footer(text="Your request will be reviewed once we receive the necessary information.")
        return embed


class RenameInfoEmbed(discord.Embed):
    """
    Embed for displaying or requesting player rename information.
    This embed summarizes the old and new player profiles if provided, or prompts the user to supply the required names.
    """
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