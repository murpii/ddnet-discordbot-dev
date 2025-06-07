import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button
import logging

from bot import DDNet
from constants import Guilds

log = logging.getLogger("renames")

async def process_rename(
        bot: DDNet,
        interaction: discord.Interaction,
        old_name: str,
        new_name: str
):
    rename_query = """
        UPDATE record_race 
        SET Name = %s 
        WHERE Name = %s 
          AND (Map, Time) NOT IN (
            SELECT Map, Time 
            FROM record_teamrace 
            WHERE Name = %s OR Name = %s 
            GROUP BY id 
            HAVING COUNT(*) > 1
        );
    
        UPDATE record_teamrace 
        SET Name = %s 
        WHERE Name = %s 
          AND (Map, Time) NOT IN (
            SELECT Map, Time 
            FROM record_teamrace 
            WHERE Name = %s OR Name = %s 
            GROUP BY id 
            HAVING COUNT(*) > 1
        );
    """

    rows_affected = await bot.upsert(
        rename_query,
        new_name, old_name, old_name,
        new_name, new_name, old_name,
        old_name, new_name
    )

    if rows_affected >= 1:
        await interaction.followup.send(content=f"Query OK, {rows_affected} rows affected.")
    else:
        await interaction.followup.send(content="Query OK, 0 rows affected.")
        log.warning(
            f"Could not rename \"{old_name}\" -> \"{new_name}\". "
            f"No rows affected. Are the provided names correct? "
            f"Invoked by: {interaction.user.name}")
        return

    rename_success = """
        INSERT INTO record_rename (OldName, Name, RenamedBy) 
        VALUES (%s, %s, %s);
    """

    await bot.upsert(rename_success, old_name, new_name, interaction.user.name)
    log.info(f"Renamed \"{old_name}\" -> \"{new_name}\" successfully. Invoked by: {interaction.user.name}")

    await interaction.channel.send(
        f"Renamed `{old_name}` to `{new_name}` successfully. "
        f"Points and ranks may take a couple of hours to reflect the update."
    )


class Rename(commands.Cog):
    def __init__(self, bot: DDNet):
        self.bot: DDNet = bot

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="rename", description="Renames a player in SQL.")
    @app_commands.describe(old_name="The old name", new_name="The new name")
    async def rename(self, interaction: discord.Interaction, old_name: str, new_name: str):
        # We can't rename people where both names have team-ranks in common.
        failsafe_query = """
        SELECT TRUE
        FROM record_teamrace
        WHERE Name = %s
        AND ID IN (SELECT ID FROM record_teamrace WHERE Name = %s)
        LIMIT 1;
        """

        if await self.bot.fetch(failsafe_query, old_name, new_name):
            await interaction.response.send_message(
                content="Old Name and New Name has team ranks in common, unable to rename.",
                ephemeral=True
            )
            return

        # Check if the old name has at least 3k points. This is normally done in rename tickets automatically,
        # but still useful in case renames are done outside of rename tickets

        points_query = """
        SELECT TRUE
        FROM record_points
        WHERE Name = %s AND Points > 3000
        LIMIT 1;
        """

        if not await self.bot.fetch(points_query, old_name):
            await interaction.response.send_message(
                content="**Old name has less than 3000 points, continue?**",
                ephemeral=True,
                view=RenameButtons(self.bot, old_name, new_name)
            )
            return
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
            await process_rename(self.bot, interaction, old_name, new_name)


class RenameButtons(discord.ui.View):
    def __init__(self, bot: DDNet, old_name: str, new_name: str):
        super().__init__(timeout=None)
        self.bot: DDNet = bot
        self.old_name: str = old_name
        self.new_name: str = new_name

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.green,
        custom_id="confirm:run_rename",
    )
    async def confirm(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        await process_rename(self.bot, interaction, self.old_name, self.new_name)


async def setup(bot: DDNet):
    await bot.add_cog(Rename(bot))