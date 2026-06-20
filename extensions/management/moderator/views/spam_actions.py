import discord

from constants import Roles
from extensions.management.moderator.manager import PendingAction, ModAction
from utils.checks import is_staff
from utils.containers import NoticeView, ALERT_ACCENT

SPAM_ACTION_ROLES = [Roles.ADMIN, Roles.DISCORD_MODERATOR]
BAN_DELETE_SECONDS = 3600
SPAM_REASON = "Spam/scam across multiple channels"


class SpamConfirmView(discord.ui.LayoutView):
    def __init__(self, user_id: int, action: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.action = action

        detail = (
            "Their messages from the last hour will be deleted."
            if action == "ban"
            else "They can rejoin with an invite."
        )

        confirm_btn = discord.ui.Button(
            label=f"Confirm {action}", style=discord.ButtonStyle.danger,  # noqa
        )
        cancel_btn = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.secondary,  # noqa
        )
        confirm_btn.callback = self.confirm
        cancel_btn.callback = self.cancel

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### Confirm {action}\n"
                    f"{action.capitalize()} <@{user_id}> (`{user_id}`)?\n"
                    f"{detail}"
                ),
                discord.ui.ActionRow(confirm_btn, cancel_btn),
                accent_colour=ALERT_ACCENT,
            )
        )

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=NoticeView("Cancelled."))

    async def confirm(self, interaction: discord.Interaction):
        guild = interaction.guild
        db = interaction.client.moddb
        moderator = interaction.user

        if guild is None:
            await interaction.response.edit_message(view=NoticeView("Guild only."))
            return

        member = guild.get_member(self.user_id)

        if self.action == "ban":
            target = member or discord.Object(id=self.user_id)
            db.actions[self.user_id] = PendingAction(moderator, ModAction.BAN, SPAM_REASON)
            try:
                await guild.ban(
                    target, delete_message_seconds=BAN_DELETE_SECONDS, reason=SPAM_REASON
                )
            except discord.Forbidden:
                db.actions.pop(self.user_id, None)
                await interaction.response.edit_message(
                    view=NoticeView("I do not have permission to ban this user.")
                )
                return
            except discord.HTTPException:
                db.actions.pop(self.user_id, None)
                await interaction.response.edit_message(
                    view=NoticeView("Ban failed. Try again later.")
                )
                return
            result = f"<@{self.user_id}> has been banned."
        else:  # kick
            if member is None:
                await interaction.response.edit_message(
                    view=NoticeView("That member is no longer in the server.")
                )
                return
            db.actions[self.user_id] = PendingAction(moderator, ModAction.KICK, SPAM_REASON)
            try:
                await member.kick(reason=SPAM_REASON)
            except discord.Forbidden:
                db.actions.pop(self.user_id, None)
                await interaction.response.edit_message(
                    view=NoticeView("I do not have permission to kick this member.")
                )
                return
            except discord.HTTPException:
                db.actions.pop(self.user_id, None)
                await interaction.response.edit_message(
                    view=NoticeView("Kick failed. Try again later.")
                )
                return
            result = f"<@{self.user_id}> has been kicked."

        await interaction.response.edit_message(view=NoticeView(result))


class SpamModButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"spammod:(?P<action>kick|ban):(?P<user_id>\d+)",
):
    def __init__(self, action: str, user_id: int):
        self.action = action
        self.user_id = user_id
        super().__init__(
            discord.ui.Button(
                label="Ban" if action == "ban" else "Kick",
                style=discord.ButtonStyle.danger if action == "ban" else discord.ButtonStyle.secondary,  # noqa
                custom_id=f"spammod:{action}:{user_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles=SPAM_ACTION_ROLES):
            await interaction.response.send_message(
                "You do not have permission to do that.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            view=SpamConfirmView(self.user_id, self.action), ephemeral=True
        )
