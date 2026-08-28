import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds, Roles, Channels
from utils.checks import staff_only

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


@app_commands.guilds(discord.Object(Guilds.DDNET))
class Assign(commands.GroupCog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

    @staticmethod
    async def toggle_role(member: discord.Member, role: discord.Role) -> discord.Role | None:
        if role in member.roles:
            await member.remove_roles(role)
            return None

        await member.add_roles(role)
        return role

    @app_commands.command(name="wikicontributor", description="Assigns or removes the Wiki Contributor role.")
    @app_commands.describe(member="@mention the user")
    @staff_only("wiki_curators")
    async def wiki_contributor(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)

        role = interaction.guild.get_role(Roles.WIKI_CONTRIBUTOR)
        if role is None:
            await interaction.followup.send("Wiki Contributor role not found.")
            return

        result = await self.toggle_role(member, role)

        await interaction.followup.send(
            (
                f"Assigned the Wiki Contributor role to {member.mention}."
                if result
                else f"Removed the Wiki Contributor role from {member.mention}."
            ),
            ephemeral=True,
        )

    @commands.Cog.listener("on_raw_reaction_add")
    @commands.Cog.listener("on_raw_reaction_remove")
    async def handle_testing_reaction(self, payload: discord.RawReactionActionEvent):
        if (
                payload.user_id == self.bot.user.id
                or payload.guild_id != Guilds.DDNET
                or payload.channel_id != Channels.TESTING_INFO
        ):
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        testing_role = guild.get_role(Roles.TESTING) if guild else None

        if not all([guild, member, testing_role]):
            return

        await self.toggle_role(member, testing_role)


async def setup(bot: "DDNet"):
    await bot.add_cog(Assign(bot))
