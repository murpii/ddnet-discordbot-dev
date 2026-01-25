import discord

from extensions.ticketsystem.ticket import Ticket
from utils.text import slugify2
from utils.profile import PlayerProfile


# THIS IS NO LONGER USED -- REPLACED BY views/containers/rename.py
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
            value=(
                "To verify that you own the points being moved, we require **one** of the following:\n\n"
                "**1. Demo files**\n"
                "- Upload **10-20 of your oldest raw demo files** showing finishes on DDNet.\n"
                "- Upload the files **as-is**. Do not zip, bundle, or modify them.\n"
                "- Ghost files are not accepted.\n"
                "-# You can find demo files in your `demos` folder inside the config directory.\n"
                "-# Type `$configdir` if you are unsure where that is.\n\n"
                "**2. Staff confirmation**\n"
                "- A vouch from a known DDNet staff member confirming your identity."
            ),
            inline=False
        )

        embed.set_footer(text="Your request will be reviewed once we receive the necessary information.")
        return embed


class RenameInfoEmbed(discord.Embed):
    """
    Embed for displaying or requesting player rename information.
    This embed summarizes the old and new player profiles if provided, or prompts the user to supply the required names.
    """

    def __new__(cls, ticket: Ticket):
        embed = discord.Embed(title="Provided Infos", colour=2210995)
        embed.add_field(
            name="",
            value=f"**[Current Name](https://ddnet.org/players/{slugify2(ticket.rename_data.old_profile.name)})**\n"
                  f"```{ticket.rename_data.old_profile.name}```"
                  f"Points: `{ticket.rename_data.old_profile.points or 0}` \n"
                  f"Last Finish: `{ticket.rename_data.old_profile.latest_finish or 'None'}` \n"
                  f"First Finish: `{ticket.rename_data.old_profile.first_finish or 'None'}`",
            inline=True
        )
        embed.add_field(
            name="",
            value=f"**[New Name](https://ddnet.org/players/{slugify2(ticket.rename_data.new_profile.name)})**\n"
                  f"```{ticket.rename_data.new_profile.name}```"
                  f"Points: `{ticket.rename_data.new_profile.points or 0}`\n"
                  + (
                      f"\tLast Finish: `{ticket.rename_data.new_profile.latest_finish or 'None'}`\n"
                      f"First Finish: `{ticket.rename_data.new_profile.first_finish or 'None'}`\n"
                      if ticket.rename_data.new_profile.points else ''
                  ),
            inline=True
        )
        return embed
