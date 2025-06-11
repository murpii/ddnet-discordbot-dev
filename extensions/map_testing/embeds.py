import discord
from constants import Roles


class ISubmEmbed(discord.Embed):
    def __new__(cls, isubm) -> discord.Embed:
        return discord.Embed(
            title=f"{isubm.name} — Testing",
            description=f"{isubm.author.mention} this is your map's testing channel!\n\n"
            "⚠️ Post map updates here and remember to follow our mapper rules! ⚠️\n\n"
            "If possible, include a playthrough of your map, "
            "so our testers have a better understanding of your idea of a map!",
            color=discord.Color.blurple(),
        )


class ISubmErrors(discord.Embed):
    def __new__(cls) -> discord.Embed:
        return discord.Embed(
            title="ERRORS",
            description=f"⚠️ Your map contains errors, please fix them as soon as possible. ⚠️\n"
            f"Your map has been automatically moved to WAITING Mapper in the meantime.",
            color=discord.Color.red(),
        )


class ISubmThumbnail(discord.Embed):
    def __new__(cls, preview_url: str) -> discord.Embed:
        return discord.Embed(
            title="",
            description=f"A full map preview can be found [HERE]({preview_url}).\n\n",
            color=discord.Color.blurple(),
        )


class TesterControls(discord.Embed):
    def __new__(cls) -> discord.Embed:
        return discord.Embed(
            title="Tester Controls",
            description=f"<@&{Roles.TESTER}> Use these options to make changes:\n\n"
            f"**Keep in mind:**\n"
            f"Only **two** map updates are possible every **15 minutes**, "
            f"otherwise the bot gets rate-limited.",
            color=discord.Color.blurple(),
        )


class DebugEmbed(discord.Embed):
    def __new__(cls, dbg_out: str | None = None) -> discord.Embed:
        if dbg_out:
            description = (
                f"Debug Output:\n```{dbg_out}```\n"
                "Please address the issues, otherwise we're unable to release your map!\n"
                "If you're unable to resolve the bugs yourself, don't hesitate to ask!"
            )
        else:
            description = (
                "Debug Output is too long, see the attached file. "
                "Please address the issues, otherwise we're unable to release your map!\n"
                "If you're unable to resolve the bugs yourself, don't hesitate to ask!"
            )

        return discord.Embed(
            title="⚠️ Map Bugs found! ⚠️",
            description=description,
            color=discord.Color.dark_red()
        )
    
    
class MapReleased(discord.Embed):
    def __new__(cls, map_channel, timestamp) -> discord.Embed:
        em = discord.Embed(
            title="📢 Map Released!",
            color=discord.Color.dark_gray(),
            description=(
                f"{map_channel.mapper_mentions} your map has just been released! 🎉\n\n"
                "You now have a **2-week grace period** to identify and resolve any unnoticed bugs or skips. "
                "After this period, only **design** and **quality of life** fixes will be allowed, provided "
                "they do **not** affect leaderboard rankings.\n\n"
                "⚠️ Significant gameplay changes may result in **rank removals**.\n\n"
                "Good luck with your map!\n"
            )
        )
        em.add_field(
            name="🕒 Grace Period Ends",
            value=timestamp,
            inline=False
        )
        em.set_footer(text="Make sure to review your map thoroughly before the grace period ends!")
        return em
    

class UnmatchedFilename(discord.Embed):
    def __new__(cls) -> discord.Embed:
        return discord.Embed(
            title="️⚠️ Map filename must match channel name. ⚠️",
            description="",
            color=discord.Color.dark_red()
        )
    

class UnmatchedSubmOwner(discord.Embed):
    def __new__(cls) -> discord.Embed:
        return discord.Embed(
            title="⚠️ Submission not by channel owner. ⚠️",
            description="Submission needs to be verified first. Click on the \"☑️\" reaction to approve.",
            color=discord.Color.dark_red()
        )
    

class MissingChangelog(discord.Embed):
    def __new__(cls, author: discord.abc.User) -> discord.Embed:
        return discord.Embed(
            title="⚠️ No changelog found! ⚠️",
            description=f"{author.mention}\n Please save our testers some time and "
                        f"include a changelog **ALONGSIDE** your map uploads (**pref. with screenshots**) !",
            color=discord.Color.dark_red()
            )