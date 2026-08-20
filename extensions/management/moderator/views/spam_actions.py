import discord

from extensions.management.moderator.manager import PendingAction, ModAction
from utils.checks import is_staff
from utils.containers import NoticeView, ALERT_ACCENT

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


class SpamDealtButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"spammod:dealt:(?P<state>[01])",
):
    """Checkbox so mods can see an alert was already handled. State lives in the
    message itself, the callback round-trips the components via from_message."""

    def __init__(self, checked: bool = False, moderator: str | None = None):
        self.checked = checked
        if checked:
            label = f"[✓] Resolved by {moderator}" if moderator else "[✓] Resolved"
            style = discord.ButtonStyle.success
        else:
            label = "[ ] Resolved?"
            style = discord.ButtonStyle.secondary
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,  # noqa
                custom_id=f"spammod:dealt:{int(checked)}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["state"] == "1")

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles="discord_mods"):
            await interaction.response.send_message(
                "You do not have permission to do that.", ephemeral=True
            )
            return

        checked = not self.checked
        if checked:
            label = f"[✓] Resolved by {interaction.user.display_name}"
            style = discord.ButtonStyle.success
            accent = discord.Colour.green().value
        else:
            label = "[ ] Resolved?"
            style = discord.ButtonStyle.secondary
            accent = discord.Colour.orange().value

        layout = discord.ui.LayoutView.from_message(interaction.message)
        for item in layout.walk_children():
            if isinstance(item, discord.ui.Container):
                item.accent_colour = accent
            custom_id = getattr(item, "custom_id", None)
            if isinstance(custom_id, str) and custom_id.startswith("spammod:dealt:"):
                item.label = label
                item.style = style
                item.custom_id = f"spammod:dealt:{int(checked)}"

        await interaction.response.edit_message(view=layout)


class SpamModButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"spammod:(?P<action>kick|ban|info):(?P<user_id>\d+)",
):
    def __init__(self, action: str, user_id: int):
        self.action = action
        self.user_id = user_id
        if action == "info":
            label, style = "User Info", discord.ButtonStyle.green
        elif action == "ban":
            label, style = "Ban", discord.ButtonStyle.danger
        else:
            label, style = "Kick", discord.ButtonStyle.secondary
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,  # noqa
                custom_id=f"spammod:{action}:{user_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], int(match["user_id"]))

    async def show_user_info(self, interaction: discord.Interaction):
        bot = interaction.client
        info = await bot.moddb.fetch_user_info(discord.Object(id=self.user_id))

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.response.send_message(view=NoUserInfoView(), ephemeral=True)
            return
        await interaction.response.send_message(
            view=UserInfoView(bot, info, interaction.user), ephemeral=True
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles="discord_mods"):
            await interaction.response.send_message(
                "You do not have permission to do that.", ephemeral=True
            )
            return

        if self.action == "info":
            await self.show_user_info(interaction)
            return

        await interaction.response.send_message(
            view=SpamConfirmView(self.user_id, self.action), ephemeral=True
        )
