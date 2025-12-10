import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button

from run import extensions
from constants import Guilds
from extensions.moderator.automod import session


# noinspection PyUnresolvedReferences
class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status = discord.Status.online
        self.activity = discord.Activity

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="bot-activity", description="Changes the bots activity")
    @app_commands.choices(
        activity=[
            app_commands.Choice(name="Listen", value="listen"),
            app_commands.Choice(name="Playing", value="playing"),
            app_commands.Choice(name="Watch", value="watch")
        ]
    )
    async def activity(self, interaction: discord.Interaction, activity: str, what: str):
        """|coro|
        Updates the bot's activity status based on user input.

        Args:
            interaction (discord.Interaction): The interaction object.
            activity (str): The type of activity to set (e.g., "listen", "playing", "watch").
            what (str): The description of the activity.
        """

        if activity == "listen":
            self.activity = discord.Activity(
                type=discord.ActivityType.listening, name=what
            )
        elif activity == "playing":
            self.activity = discord.Game(name=what)
        elif activity == "watch":
            self.activity = discord.Activity(
                type=discord.ActivityType.watching, name=what
            )
        await self.bot.change_presence(status=self.status, activity=self.activity)
        await interaction.response.send_message(f"Changed my status to {activity}: {what}.", ephemeral=True)

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="shutdown", description="Closes the bots connection to Discord")
    async def shutdown(self, _: discord.Interaction):
        await self.bot.close()

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="clear_cache", description="DEBUG COMMAND: Clears the bots sqlite cache.")
    async def clear_cache(self, interaction: discord.Interaction):
        """|coro|
        Clears the SQLite cache used by the bot.
        This command is intended for debugging purposes.
        """

        session.cache.clear()
        await interaction.response.send_message("Cleared sqlite cache.", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="purge", description="Deletes messages after a specified message ID.")
    @app_commands.describe(message_id="The ID of the message to delete after (not included).")
    async def purge(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            target = await interaction.channel.fetch_message(int(message_id))
        except discord.NotFound:
            await interaction.followup.send("No message found with that ID.", ephemeral=True)
            return

        messages_to_delete = []
        async for msg in interaction.channel.history(limit=None, after=target, oldest_first=True):
            if msg.created_at <= target.created_at:
                continue
            messages_to_delete.append(msg)

        if not messages_to_delete:
            await interaction.followup.send("No messages found after that ID.", ephemeral=True)
            return

        view = ChoiceView(self.bot, len(messages_to_delete))
        await interaction.followup.send(
            content=f"Are you sure you want to delete {len(messages_to_delete)} messages "
                    f"up until [this message]({target.jump_url})?",
            ephemeral=True,
            view=view
        )

        await view.wait()
        await interaction.delete_original_response()


class ChoiceView(discord.ui.View):
    def __init__(self, bot, count):
        super().__init__(timeout=None)
        self.bot = bot
        self.count = count

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green, custom_id="Continue:purge")
    async def confirm(self, interaction: discord.Interaction, _: Button):
        self.stop()
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            await interaction.followup.send(
                "Purging... This might take awhile.",
            )
            await interaction.channel.purge(limit=self.count, reason="Purge")
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have the necessary permissions to purge messages."
            )
            return

        await interaction.edit_original_response(content=f"Deleted {self.count} messages.")

    @discord.ui.button(label="Abort", style=discord.ButtonStyle.red, custom_id="Abort:purge")
    async def cancel(self, _: discord.Interaction):
        self.stop()


# noinspection PyUnresolvedReferences
@app_commands.guilds(discord.Object(Guilds.DDNET))
@app_commands.default_permissions(administrator=True)
class Extensions(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    # Only up to 25 choices possible
    choices = [
        app_commands.Choice(name=cog.split(".")[-1], value=cog) for cog, _ in extensions
    ]

    async def sync_guild(self, interaction: discord.Interaction):
        synced_global = await self.bot.tree.sync()
        synced_guild = await self.bot.tree.sync(guild=discord.Object(Guilds.DDNET))
        await interaction.followup.send(
            content=f"Slash CMDs Synced - Global: {len(synced_global)}, Guild: {len(synced_guild)}",
            ephemeral=True,
        )  # noqa

    @app_commands.command(name="load", description="Loads a cog extension")
    @app_commands.describe(extension="The name of the extension to load")
    @app_commands.choices(extension=choices)
    async def load(self, interaction: discord.Interaction, extension: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            await self.bot.load_extension(extension)
            await interaction.edit_original_response(
                content=f"Loaded {extension} successfully. Syncing app commands... This might take awhile."
            )
            await self.sync_guild(interaction)
        except commands.ExtensionAlreadyLoaded:
            await interaction.followup.send(f"`{extension}` is already loaded!")
        except commands.ExtensionNotFound:
            await interaction.followup.send(f"`{extension}` not found!")
        except commands.ExtensionFailed as e:
            await interaction.followup.send(f"`{extension}` failed to load: {e}")

    @app_commands.command(name="unload", description="Unloads a cog extension")
    @app_commands.describe(extension="The name of the extension to unload")
    @app_commands.choices(extension=choices)
    async def unload(self, interaction: discord.Interaction, extension: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            await self.bot.unload_extension(extension)
            await interaction.edit_original_response(
                content=f"Unloaded {extension} successfully. Syncing app commands... This might take awhile."
            )
            await self.sync_guild(interaction)
        except (commands.ExtensionNotFound, commands.ExtensionNotLoaded):
            await interaction.followup.send(f"`{extension}` not found!")

    @app_commands.command(name="reload", description="Reload a cog extension")
    @app_commands.describe(extension="The name of the extension to reload")
    @app_commands.choices(extension=choices)
    async def reload(self, interaction: discord.Interaction, extension: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            await self.bot.reload_extension(extension)
            await interaction.edit_original_response(
                content=f"Reloaded {extension} successfully. Syncing app commands... This might take awhile."
            )
            await self.sync_guild(interaction)
        except commands.ExtensionNotLoaded:
            await interaction.followup.send(f"`{extension}` is not loaded!")
        except commands.ExtensionNotFound:
            await interaction.followup.send(f"`{extension}` not found!")
        except commands.ExtensionFailed as e:
            await interaction.followup.send(f"`{extension}` failed to load: {e}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
    await bot.add_cog(Extensions(bot))
