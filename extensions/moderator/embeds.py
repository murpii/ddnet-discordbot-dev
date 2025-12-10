import discord
from datetime import datetime, timezone
from utils.text import to_discord_timestamp
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from extensions.moderator.manager import MemberInfo


def full_info(info: "MemberInfo") -> list[discord.Embed]:
    embeds = [MemberInfoEmbed(info)]
    empty_labels = []
    non_empty = []

    for attr, label, embed in [
        ("timeouts", "Timeouts", TimeoutsEmbed),
        ("bans", "Bans", BansEmbed),
        ("kicks", "Kicks", KicksEmbed),
    ]:
        (non_empty if getattr(info, attr) else empty_labels.append(label)) \
            if getattr(info, attr) else None
        if getattr(info, attr):
            non_empty.append(embed(info))

    if empty_labels:
        embeds.append(NoEntries(empty_labels))
    return embeds + non_empty


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
            title=":crossed_swords: User Info", color=discord.Color.blurple(),
            colour=3619648,
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

        if member_info.timed_out and member_info.timed_out > datetime.now(timezone.utc):
            timed_out_str = f"✅ (Ends: {to_discord_timestamp(member_info.timed_out, style='R')})"
        else:
            timed_out_str = "❌"

        embed.add_field(
            name="Status",
            value=(
                f"Banned: {'✅' if member_info.banned else '❌'}\n"
                f"Timed out: {timed_out_str}\n"
                f"Banned from Testing: {'✅' if member_info.banned_from_testing else '❌'}"
            ),
            inline=False
        )

        if member_info.nicknames:
            lines = [
                f"{name}: ({to_discord_timestamp(ts, style='R')})"
                for name, ts in member_info.nicknames
            ]

            embed.add_field(
                name="Past Names",
                value="\n".join(lines),
                inline=False
            )

        return embed


class TimeoutsEmbed(discord.Embed):
    def __new__(cls, member_info: "MemberInfo"):
        embed = discord.Embed(
            title="", color=discord.Color.blurple(),
            colour=3619648,
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
            title="", color=discord.Color.blurple(),
            colour=3619648,
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
            title="", color=discord.Color.blurple(),
            colour=3619648,
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


class NoEntries(discord.Embed):
    def __new__(cls, sections: list[str]):
        return discord.Embed(
            title="",
            description="\n".join(f"No {section.lower()} found." for section in sections),
            color=3619648,
        )


class LogEmbed(discord.Embed):
    def __new__(cls, string: str, member: discord.abc.User):
        em = discord.Embed(
            title=":crossed_swords: Discord Moderation",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
            description=string,
        )
        em.set_thumbnail(url=member.display_avatar.url)
        return em


class ServerInfoEmbed(discord.Embed):
    """
    This embed presents details about a server, including its address, type, region, and affiliation status.
    """

    @classmethod
    def from_server_info(
            cls,
            info: dict | None,
            addr: str,
            ticket: bool = False,
            region: str = None,
    ) -> discord.Embed:
        """
        Generates an embed containing server information and warnings based on the provided server data.

        Args:
            info (dict | None): The server information dictionary, or None if not found.
            addr (str): The address of the server.
            ticket (bool, optional): Whether this is for a ticket context. Defaults to False.
            region (str, optional): The region or country of the server. Defaults to None.

        Returns:
            discord.Embed: The constructed embed containing server information and warnings.
        """
        if info:
            server_name = info.get("name")
            server_type = info.get("server_type")
            if server_type == "DDNet":
                server_type = "DDrace"
            network = info.get("network")
            icon = info.get("icon")

            embed = cls(
                title=f"{server_name} Server Info",
                color=discord.Color.orange() if network != "DDraceNetwork" else discord.Color.green()
            )
        else:
            network = None
            server_type = None
            icon = None
            embed = cls(
                title="",
                description=f"⚠️ {addr} is not a DDNet or Community server.",
                color=discord.Color.red()
            )

        if info and network != "DDraceNetwork":
            warning = "This server is **NOT** affiliated with DDNet.\n"
            if ticket and network is not None:
                warning += "Click the contact URL button and ask for help there instead."
                embed.add_field(
                    name="⚠️ Warning",
                    value=warning.strip(),
                    inline=False
                )
                return embed
            else:
                embed.add_field(
                    name="⚠️ Warning",
                    value=warning.strip(),
                    inline=False
                )

        if info:
            embed.add_field(name="Address", value=addr, inline=True)
            embed.add_field(name="Country", value=region, inline=True)
            embed.add_field(name="Server Type", value=server_type, inline=True)
            if icon:
                embed.set_thumbnail(url=icon)

        return embed
