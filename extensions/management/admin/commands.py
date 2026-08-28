import discord
from discord import app_commands
from discord.ext import commands

from extensions.management.admin.views.purge import ChoiceView

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


# noinspection PyUnresolvedReferences
class Admin(commands.Cog):
    """
    Admin slash commands. Most admin tooling lives in the admin hub.
    Only /purge remains a command because it has to
    run inside the channel that should be purged.
    """

    def __init__(self, bot: "DDNet"):
        self.bot = bot

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="purge",
        description="Delete messages after a message ID, optionally only up to a start message ID.",
    )
    @app_commands.describe(
        message_id="End of the range: messages newer than this are deleted (this message itself is kept).",
        start_message_id="Optional newer bound: only delete up to this message (kept). Defaults to the newest message.",
    )
    async def purge(
            self,
            interaction: discord.Interaction,
            message_id: str,
            start_message_id: str = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            end = await interaction.channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            await interaction.followup.send("No message found with that ID.", ephemeral=True)
            return

        start = None
        if start_message_id:
            try:
                start = await interaction.channel.fetch_message(int(start_message_id))
            except (discord.NotFound, ValueError):
                await interaction.followup.send("No message found with that start ID.", ephemeral=True)
                return
            if start.created_at <= end.created_at:
                await interaction.followup.send(
                    "The start message must be newer than the end message.", ephemeral=True
                )
                return

        count = 0
        async for _ in interaction.channel.history(limit=None, after=end, before=start, oldest_first=True):
            count += 1

        if not count:
            await interaction.followup.send("No messages found in that range.", ephemeral=True)
            return

        where = (
            f"between [start]({start.jump_url}) and [end]({end.jump_url})"
            if start is not None
            else f"up until [this message]({end.jump_url})"
        )
        view = ChoiceView(self.bot, end, start)
        await interaction.followup.send(
            content=f"Are you sure you want to delete {count} messages {where}?",
            ephemeral=True,
            view=view,
        )

        await view.wait()
        await interaction.delete_original_response()
