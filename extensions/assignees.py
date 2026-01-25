import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds, Roles, Channels, WIKI_CURATOR_ROLES


@app_commands.guilds(discord.Object(Guilds.DDNET))
class Assign(commands.GroupCog):
    def __init__(self, bot: commands.Bot):
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
    @app_commands.checks.has_any_role(*WIKI_CURATOR_ROLES, Roles.ADMIN)
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

    @app_commands.command(name="mapper", description="Assigns or removes the Mapper role.")
    @app_commands.describe(member="@mention the user")
    @app_commands.checks.has_role(Roles.ADMIN)
    async def mapper(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)

        role = interaction.guild.get_role(Roles.MAPPER)
        if role is None:
            await interaction.followup.send("Mapper role not found.")
            return

        result = await self.toggle_role(member, role)

        await interaction.followup.send(
            (
                f"Assigned the Mapper role to {member.mention}."
                if result
                else f"Removed the Mapper role from {member.mention}."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="developer", description="Assigns or removes the Developer role.")
    @app_commands.describe(member="@mention the user")
    @app_commands.checks.has_role(Roles.ADMIN)
    async def developer(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)

        role = interaction.guild.get_role(Roles.DEV)
        if role is None:
            await interaction.followup.send("Developer role not found.")
            return

        result = await self.toggle_role(member, role)

        await interaction.followup.send(
            (
                f"Assigned the Developer role to {member.mention}."
                if result
                else f"Removed the Developer role from {member.mention}."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="tester", description="Assigns or removes a Tester role.")
    @app_commands.describe(user="@mention the user", role="Select the tester role")
    @app_commands.checks.has_role(Roles.ADMIN)
    @app_commands.choices(role=[
        app_commands.Choice(name="Tester", value="tester"),
        app_commands.Choice(name="Tester excl. Tournaments", value="tester_excl_tournaments")
    ])
    async def tester(self, interaction: discord.Interaction, user: discord.Member, role: str, ):
        role_id = (
            Roles.TESTER
            if role == "tester"
            else Roles.TESTER_EXCL_TOURNAMENTS
        )
        tester_role = interaction.guild.get_role(role_id)

        if tester_role is None:
            await interaction.response.send_message(
                "Tester role not found.",
                ephemeral=True,
            )
            return

        result = await self.toggle_role(user, tester_role)

        await interaction.response.send_message(
            (
                f"Added {tester_role.name} to {user.mention}."
                if result
                else f"Removed {tester_role.name} from {user.mention}."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="trial_tester", description="Assigns or removes a Trial Tester role.", )
    @app_commands.describe(user="@mention the user", role="Select the trial tester role")
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS)
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Trial Tester", value="trial"),
            app_commands.Choice(name="Trial Tester excl. Tournaments", value="trial_excl_tournaments")
        ])
    async def trial_tester(self, interaction: discord.Interaction, user: discord.Member, role: str):
        role_id = (
            Roles.TRIAL_TESTER
            if role == "trial"
            else Roles.TRIAL_TESTER_EXCL_TOURNAMENTS
        )
        trial_role = interaction.guild.get_role(role_id)
        if trial_role is None:
            await interaction.response.send_message(
                "Trial Tester role not found.",
                ephemeral=True,
            )
            return

        result = await self.toggle_role(user, trial_role)

        await interaction.response.send_message(
            (
                f"Added {trial_role.name} to {user.mention}."
                if result
                else f"Removed {trial_role.name} from {user.mention}."
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Assign(bot))
