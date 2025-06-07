import discord
from discord.ui import Button

from extensions.ticketsystem.queries import get_subscriptions, add_subscription, rm_subscription

class SubscribeMenu(discord.ui.View):
    """A user interface for managing subscriptions to ticket categories."""
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="To which categories would you like to subscribe to?",
        options=[
            discord.SelectOption(label="Report", value="report"),
            discord.SelectOption(label="Rename", value="rename"),
            discord.SelectOption(label="Ban Appeal", value="ban-appeal"),
            discord.SelectOption(label="Complaint", value="complaint"),
            discord.SelectOption(label="Admin-Mail", value="admin-mail"),
        ],
        max_values=5,
        custom_id="Subscribe:Menu",
    )
    async def subscriptions(
        self, interaction: discord.Interaction, _: discord.ui.Select
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        selected_values = interaction.data["values"]
        user_id = interaction.user.id

        results = await self.bot.fetch(
            get_subscriptions,
            user_id,
            fetchall=True,
        )

        existing_categories = {sub[0] for sub in results}

        categories_to_add = set(selected_values) - existing_categories
        categories_to_remove = existing_categories - set(selected_values)

        for category in categories_to_add:
            await self.bot.upsert(
                add_subscription,
                user_id,
                category,
            )

        for category in categories_to_remove:
            await self.bot.upsert(
                rm_subscription,
                user_id,
                category,
            )

        category_message = (
            "You have subscribed to the following categories:\n- "
            + "\n- ".join(selected_values)
        )
        await interaction.followup.send(category_message, ephemeral=True)

    @discord.ui.button(
        label="Subscribe All",
        style=discord.ButtonStyle.green,
        custom_id="Subscribe:All",
    )
    async def subscribe_all(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        categories = ["report", "rename", "ban-appeal", "complaint", "admin-mail"]
        user_id = interaction.user.id

        for category in categories:
            await self.bot.upsert(
                add_subscription,
                user_id,
                category,
            )

        await interaction.followup.send(
            "Subscribed you to all ticket categories.", ephemeral=True
        )

    @discord.ui.button(
        label="Unsubscribe All",
        style=discord.ButtonStyle.green,
        custom_id="Unsubscribe:All",
    )
    async def unsubscribe_all(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        user_id = interaction.user.id
        await self.bot.upsert(
            rm_subscription, user_id
        )

        await interaction.followup.send(
            "Unsubscribed you from all ticket categories.", ephemeral=True
        )
