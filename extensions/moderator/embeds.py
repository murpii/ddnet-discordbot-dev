import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extensions.moderator.manager import MemberInfo


class NoMemberInfoEmbed(discord.Embed):
    def __new__(cls):
        return discord.Embed(
            title="User Info",
            description="No user information found.",
            color=discord.Color.red(),
        )


class MemberInfoEmbed(discord.Embed):
    def __new__(cls, member_info: "MemberInfo"):
        embed = discord.Embed(
            title=":crossed_swords: User Info", color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=member_info.member.display_avatar.url)

        embed.add_field(
            name="Name",
            value=f"{member_info.member.mention}",
            inline=False
        )

        embed.add_field(
            name="Created At",
            value=f"{member_info.member.created_at.strftime('`%Y-%m-%d`')}\n`{member_info.member.created_at.strftime('%H:%M UTC')}`",
            inline=True,
        )

        embed.add_field(
            name="Joined At",
            value=f"{member_info.member.joined_at.strftime('`%Y-%m-%d`')}\n`{member_info.member.joined_at.strftime('%H:%M UTC')}`"
            if hasattr(member_info.member, 'joined_at') else "`Unknown`",
            inline=True
        )

        return embed


class TimeoutsEmbed(discord.Embed):
    def __new__(cls, member_info: "MemberInfo"):
        embed = discord.Embed(
            title="", color=discord.Color.blurple()
        )
        if member_info.timeouts:
            if member_info.timeout_reasons:
                reasons = "\n".join(
                    f"[`{dt.strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason}"
                    for reason, dt in member_info.timeout_reasons
                )
            else:
                reasons = "No reasons provided"

            title = f" Total Timeouts: {member_info.timeouts} "
            embed.add_field(name=title.center(32, '─'), value=reasons, inline=False)
        else:
            embed.add_field(name="Total Timeouts", value="No timeouts found.", inline=False)

        return embed


class BansEmbed(discord.Embed):
    def __new__(cls, member_info: "MemberInfo"):
        embed = discord.Embed(
            title="", color=discord.Color.blurple()
        )
        if member_info.bans:
            if member_info.ban_reasons:
                reasons = "\n".join(
                    f"[`{dt.strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason}"
                    for reason, dt in member_info.ban_reasons
                )
            else:
                reasons = "No reasons provided"

            title = f" Total Bans: {member_info.bans} "
            embed.add_field(name=title.center(32, '─'), value=reasons, inline=False)
        else:
            embed.add_field(name="Bans", value="No bans found.", inline=False)

        return embed


class KicksEmbed(discord.Embed):
    def __new__(cls, member_info: "MemberInfo"):
        embed = discord.Embed(
            title="", color=discord.Color.blurple()
        )
        if member_info.kicks:
            if member_info.kick_reasons:
                reasons = "\n".join(
                    f"[`{dt.strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason}"
                    for reason, dt in member_info.kick_reasons
                )
            else:
                reasons = "No reasons provided"

            title = f" Total Kicks: {member_info.kicks} "
            embed.add_field(name=title.center(32, '─'), value=reasons, inline=False)
        else:
            embed.add_field(name="Kicks", value="No kicks found.", inline=False)

        return embed


class LogEmbed(discord.Embed):
    def __new__(cls, string: str, member: discord.abc.User):
        em = discord.Embed(
            title=":crossed_swords: Discord Moderation",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
            description=string,
        )
        em.set_thumbnail(url=member.display_avatar.url)
        return em