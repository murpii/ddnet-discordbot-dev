import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds, Roles, Channels


def predicate(interaction: discord.Interaction) -> bool:
    return Roles.ADMIN in [role.id for role in interaction.user.roles] or interaction.user.id in Roles.WIKI_CURATORS


@app_commands.guilds(discord.Object(Guilds.DDNET))
class Assign(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="wikicontributor",
        description="Assigns the Wiki Contributor role to a user if they don’t have it, or removes it if they do.")
    @app_commands.describe(
        member="@mention the user to promote")
    @app_commands.check(predicate)
    async def wiki_contributor(self, interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        wiki_contributor = interaction.guild.get_role(Roles.WIKI_CONTRIBUTOR)

        if wiki_contributor in member.roles:
            await member.remove_roles(wiki_contributor)
            await interaction.followup.send(
                f"Removed the Wiki Contributor from user {member.mention}."
            )
        else:
            await member.add_roles(wiki_contributor)
            await interaction.followup.send(
                f"{member.mention} has been assigned the Wiki Contributor role."
            )

    @app_commands.command(
        name="tester", description="Assigns the Tester role to a user if they don’t have it, or removes it if they do.")
    @app_commands.describe(user="@mention the trial tester to promote")
    @app_commands.checks.has_role(Roles.ADMIN)
    @app_commands.choices(role=[
            app_commands.Choice(name="Tester", value="Tester"),
            app_commands.Choice(name="Tester excl. Tournaments", value="Tester excl. Tournaments")
    ])
    async def tester(self, interaction: discord.Interaction, user: discord.Member, role: str):
        tester_role = interaction.guild.get_role(
            Roles.TESTER if role == "Tester" else Roles.TESTER_EXCL_TOURNAMENTS
        )
        action = "Added" if tester_role not in user.roles else "Removed"

        (
            await user.add_roles(tester_role)
            if action == "Added"
            else await user.remove_roles(tester_role)
        )

        await interaction.response.send_message(  # noqa
            f"{action} {role} role from/to {user.mention}", ephemeral=True
        )

    @app_commands.command(
        name="trial_tester",
        description="Assigns the Trial Tester role to a user if they don’t have it, or removes it if they do.")
    @app_commands.describe(user="@mention the user to promote")
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS)
    @app_commands.choices(role=[
            app_commands.Choice(name="Trial Tester", value="Trial Tester"),
            app_commands.Choice(name="Trial Tester excl. Tournaments", value="Trial Tester excl. Tournaments")
    ])
    async def trial_tester(self, interaction: discord.Interaction, user: discord.Member, role: str):
        trial_tester_role = interaction.guild.get_role(
            Roles.TRIAL_TESTER
            if role == "Trial Tester"
            else Roles.TRIAL_TESTER_EXCL_TOURNAMENTS
        )
        action = "Added" if trial_tester_role not in user.roles else "Removed"

        (
            await user.add_roles(trial_tester_role)
            if action == "Added"
            else await user.remove_roles(trial_tester_role)
        )
        await interaction.response.send_message(  # noqa
            f"{action} {role} role from/to {user.mention}", ephemeral=True
        )

    @commands.Cog.listener("on_raw_reaction_add")
    @commands.Cog.listener("on_raw_reaction_remove")
    async def handle_reaction(self, payload: discord.RawReactionActionEvent):
        # Map Testing Info event listener
        # Assigns the Testing role to a user if they don’t have it, or removes it if they do.
        if payload.user_id == self.bot.user.id:
            return

        if payload.guild_id != Guilds.DDNET:
            return

        guild = self.bot.get_guild(payload.guild_id)

        if payload.channel_id == Channels.TESTING_INFO:
            member = guild.get_member(payload.user_id)
            testing_role = guild.get_role(Roles.TESTING)

            if payload.event_type == "REACTION_ADD" and testing_role not in member.roles:
                await member.add_roles(testing_role)
            elif payload.event_type == "REACTION_REMOVE" and testing_role in member.roles:
                await member.remove_roles(testing_role)


async def setup(bot):
    await bot.add_cog(Assign(bot))
