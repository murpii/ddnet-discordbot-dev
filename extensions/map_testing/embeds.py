import discord
from constants import Roles


class ISubmEmbed(discord.Embed):
    def __new__(cls, isubm) -> discord.Embed:
        embed = discord.Embed(
            title=f"{isubm.name} — Testing",
            description=f"{isubm.author.mention} this is your map's testing channel!\n\n"
                        "⚠️ Post map updates here and remember to follow our mapper rules! ⚠️\n\n"
                        "If possible, include a playthrough of your map, "
                        "so our testers have a better understanding of your idea of a map!",
            color=discord.Color.blurple()
        )
        return embed


class ISubmErrors(discord.Embed):
    def __new__(cls) -> discord.Embed:
        embed = discord.Embed(
            title="ERRORS",
            description=f"⚠️ Your map contains errors, please fix them as soon as possible. ⚠️\n"
                        f"Your map has been automatically moved to WAITING Mapper in the meantime.",
            color=discord.Color.red(),
        )
        return embed


class ISubmThumbnail(discord.Embed):
    def __new__(cls, preview_url: str) -> discord.Embed:
        embed = discord.Embed(
            title="",
            description=f"A full map preview can be found [HERE]({preview_url}).\n\n",
            color=discord.Color.blurple()
        )
        return embed


class TesterControls(discord.Embed):
    def __new__(cls) -> discord.Embed:
        embed = discord.Embed(
            title="Tester Controls",
            description=f"<@&{Roles.TESTER}> Use these options to make changes:\n\n"
                        f"**Keep in mind:**\n"
                        f"Only **two** map updates are possible every **15 minutes**, "
                        f"otherwise the bot gets rate-limited.",
            color=discord.Color.blurple()
        )
        return embed
