import discord

from utils.checks import is_staff


class UserInfoButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"userinfo:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(
            discord.ui.Button(
                label="User Info",
                style=discord.ButtonStyle.green,  # noqa
                custom_id=f"userinfo:{user_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        # the panel holds moderation controls, so testers stay out
        if not is_staff(interaction.user, roles="mods"):
            await interaction.response.send_message(
                "You do not have permission to do that.", ephemeral=True
            )
            return

        bot = interaction.client
        info = await bot.moddb.fetch_user_info(discord.Object(id=self.user_id))

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.response.send_message(view=NoUserInfoView(), ephemeral=True)
            return

        await interaction.response.send_message(
            view=UserInfoView(bot, info, interaction.user), ephemeral=True
        )
