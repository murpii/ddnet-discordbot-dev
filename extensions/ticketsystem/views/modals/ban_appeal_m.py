import contextlib

import discord
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from extensions.ticketsystem.channel import build_ticket_channel
from constants import URLs
from extensions.ticketsystem.lang.ban_appeal_m import (
    ban_appeal_m,
    BAN_APPEAL_GATE,
    BAN_APPEAL_CLOUDFLARE,
)
from extensions.ticketsystem.utils import find_active_bans
from extensions.ticketsystem.views.containers.ban_appeal.gate import GateContainer, NoticeContainer
from extensions.ticketsystem.views.containers.ban_appeal.mod_review import ModReviewContainer
from extensions.ticketsystem.views.containers.base import large_seperator
from extensions.ticketsystem.ticket import Ticket, AppealData, TicketCategory
from utils.checks import check_public_ip, check_ip
from utils.profile import PlayerProfile
from utils.text import to_discord_timestamp

log = logging.getLogger("tickets")


class BanAppealModal(discord.ui.Modal, title="Ban Appeal Ticket"):
    session = None

    def __init__(
            self,
            bot,
            language="en",
            ticket: Ticket | None = None,
            category: TicketCategory = TicketCategory.BAN_APPEAL,
    ):
        self.bot = bot
        self.language = language
        self.ticket_manager = bot.ticket_manager
        self.api_key = self.bot.config.get("DNSBL_API", "KEY")
        self.is_blocked: Optional[str] = None
        self.button: discord.ui.Button | None = None

        # which appeal category this modal opens: regular ban appeal or VPN ban appeal.
        self.category = category

        # change ticket category related
        self.ticket: Ticket | None = ticket
        self.origin_message: discord.Message | None = None

        modal = ban_appeal_m.get(language, ban_appeal_m["en"])
        title = "VPN Ban Appeal Ticket" if category == TicketCategory.VPN_BAN_APPEAL else modal["title"]
        super().__init__(title=title, timeout=None)

        privacy_note = modal.get("privacy_note") or ban_appeal_m["en"]["privacy_note"]
        self.add_item(discord.ui.TextDisplay(privacy_note))

        self.public_ip = discord.ui.TextInput(
            label=modal["ip_label"],
            placeholder=modal["ip_placeholder"],
            max_length=15,
            style=discord.TextStyle.short,  # type: ignore
        )
        self.add_item(self.public_ip)

        self.ingame_name = discord.ui.TextInput(
            label=modal["name_label"],
            placeholder=modal["name_label"],
            max_length=15,
            style=discord.TextStyle.short,  # type: ignore
        )
        self.add_item(self.ingame_name)

        # VPN appeals only need the IP + in-game name & an automatic VPN/proxy block
        # has no ban reason or appeal statement to provide
        self.ban_reason: discord.ui.TextInput | None = None
        self.appeal: discord.ui.TextInput | None = None
        if category != TicketCategory.VPN_BAN_APPEAL:
            self.ban_reason = discord.ui.TextInput(
                label=modal["reason_label"],
                placeholder=modal["reason_placeholder"],
                max_length=20,
                style=discord.TextStyle.short,  # type: ignore
            )
            self.add_item(self.ban_reason)

            self.appeal = discord.ui.TextInput(
                label=modal["appeal_label"],
                placeholder=modal["appeal_placeholder"],
                max_length=500,
                style=discord.TextStyle.long,  # type: ignore
            )
            self.add_item(self.appeal)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the submission of the ban appeal modal.

        Validates the provided IP and ban status before opening a appeal channel
        The appeal is refused outright when the IP isn't flagged (DNSBL=white)
        or has no active ban; when the matching ban is about to expire the user is asked
        to confirm they still want to proceed.

        Args:
            interaction: The interaction created when the modal is submitted.
        """
        success, message = check_public_ip(self.public_ip.value)
        if not success:
            content = f"**IP Check Failed:**\n{message}"
            if self.ban_reason is not None:
                content += f"\n\n**Your provided reason:**\n{self.ban_reason.value}"
            await interaction.response.send_message(content, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        dnsbl, cloudflare = await check_ip(self.public_ip.value, self.session, self.api_key)
        profile = await PlayerProfile.from_database(self.bot, self.ingame_name.value)
        data = AppealData(
            address=self.public_ip.value,
            dnsbl=dnsbl,
            cloudflare=cloudflare,
            name=self.ingame_name.value,
            reason=self.ban_reason.value if self.ban_reason else "",
            appeal=self.appeal.value if self.appeal else "",
            profile=profile
        )

        # refuse appeals for IPs that aren't actually banned or aren't flagged
        # "DEBUG" bypasses the gate to allow manual testing (see check_public_ip).
        if self.public_ip.value != "DEBUG" and not await self.gate(interaction, data):
            return

        await self.open_ticket(interaction, data)

    async def gate(self, interaction: discord.Interaction, data: AppealData) -> bool:
        """Decide whether an appeal may be opened for the provided IP.

        Returns True when the caller should go ahead and open the ticket.
        Returns False when the appeal was refused.
        """
        lang = BAN_APPEAL_GATE.get(self.language, BAN_APPEAL_GATE["en"])

        if self.category == TicketCategory.VPN_BAN_APPEAL:
            if data.dnsbl == "DNSBL=white":
                await interaction.followup.send(
                    view=GateContainer(
                        lang["dnsbl_white_title"],
                        lang["dnsbl_white"].format(ip=data.address),
                        discord.Colour.red(),
                    ),
                    ephemeral=True,
                )
                return False

            if data.cloudflare:
                cf_lang = BAN_APPEAL_CLOUDFLARE.get(self.language, BAN_APPEAL_CLOUDFLARE["en"])
                description = (
                    f"{cf_lang['description']}\n\n"
                    f"**{cf_lang['title']}**\n"
                    f"[{cf_lang['value']}]({URLs.CLOUDFLARE_WARP_DOCS})"
                )
                await interaction.followup.send(
                    view=GateContainer("Cloudflare WARP", description, discord.Colour.red()),
                    ephemeral=True,
                )
                return False

            return True

        # regular ban appeals gate on an active manual ban
        # the DNSBL check lives in the VPN ban appeal flow instead
        active_bans = find_active_bans(data.address)

        # no active ban to appeal (expired bans don't count).
        if not active_bans:
            await interaction.followup.send(
                view=GateContainer(
                    lang["not_banned_title"],
                    lang["not_banned"].format(ip=data.address),
                    discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return False

        # active ban that's about to expire: ask the user to confirm before proceeding.
        # only for fresh appeals. category changes proceed straight away.
        soonest = active_bans[0]
        if self.ticket is None and soonest["expires"] - datetime.now(timezone.utc) <= timedelta(hours=2):
            description = lang["near_expiry"].format(
                ip=data.address,
                expires=to_discord_timestamp(soonest["expires"], style="R"),
                reason=soonest["reason"],
            )
            view = AppealExpiryConfirmView(
                self, data, title=lang["near_expiry_title"], description=description
            )
            view.message = await interaction.followup.send(view=view, ephemeral=True)
            return False

        return True

    async def open_ticket(self, interaction: discord.Interaction, data: AppealData):
        """
        Create the ban-appeal ticket, or convert an existing ticket into one.
        Assumes `interaction` has already been responded to/deferred so followups work.
        """
        # Case: an existing ticket is being changed into a ban appeal.
        if self.ticket:
            await self.ticket_manager.update_ticket(
                interaction,
                ticket=self.ticket,
                category=self.category,
                appeal_data=data,
                button=self.button
            )
            if self.origin_message:
                with contextlib.suppress(discord.NotFound):
                    await self.origin_message.delete()
            ticket = self.ticket
        else:
            ticket = Ticket(
                channel=None,
                creator=interaction.user,
                category=self.category,
                appeal_data=data,
            )
            if await build_ticket_channel(interaction, ticket) is None:
                return  # channel creation failed; create_ticket_channel already told the user

        # regular ban appeals get a private mod review thread that pings the issuing moderator
        if self.category == TicketCategory.BAN_APPEAL:
            await self.create_mod_review_thread(ticket)

    async def create_mod_review_thread(self, ticket: Ticket) -> None:
        """
        Open a __private__, mod only thread inside the ban-appeal ticket.

        1. Pings the moderator(s) who issued the matching ban(s)
        2. the synced sqlite ban list stores the issuer's Discord username, which maps 1:1 to a guild member
        3. asks them to drop their proof so another moderator can review the case

        The thread is private other moderators reach it via the manage threads permission
        """
        channel = ticket.channel
        if channel is None or not ticket.appeal_data:
            return

        guild = channel.guild

        if discord.utils.get(channel.threads, name="Moderator Review") is not None:
            return

        bans = find_active_bans(ticket.appeal_data.address)
        issuer_names = list(dict.fromkeys(b["moderator"] for b in bans if b.get("moderator")))

        resolved: list[discord.Member] = []
        unresolved: list[str] = []
        for name in issuer_names:
            if member := guild.get_member_named(name):
                resolved.append(member)
            else:
                unresolved.append(name)

        try:
            thread = await channel.create_thread(
                name="Moderator Review",
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=10080,  # 7 days, the max
                reason="Ban-appeal moderator review",
            )
        except discord.HTTPException as e:
            log.warning("Failed to create mod review thread in %s: %s", channel.name, e)
            return

        for member in resolved:
            with contextlib.suppress(discord.HTTPException):
                await thread.add_user(member)

        await thread.send(
            view=ModReviewContainer(resolved, unresolved, bans),
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )


class AppealExpiryConfirmView(discord.ui.LayoutView):
    """Confirmation shown when the matching ban is about to expire"""

    def __init__(self, modal: "BanAppealModal", data: AppealData, *, title: str, description: str):
        super().__init__(timeout=300)
        self.modal = modal
        self.data = data
        self.title = title
        self.description = description
        self.message: discord.Message | None = None
        lang = BAN_APPEAL_GATE.get(modal.language, BAN_APPEAL_GATE["en"])

        self.continue_btn = discord.ui.Button(
            label=lang["near_expiry_continue"], style=discord.ButtonStyle.green  # noqa
        )
        self.cancel_btn = discord.ui.Button(
            label=lang["near_expiry_cancel"], style=discord.ButtonStyle.red  # noqa
        )
        self.continue_btn.callback = self.continue_appeal
        self.cancel_btn.callback = self.cancel_appeal

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}"),
                large_seperator(),
                discord.ui.TextDisplay(description),
                discord.ui.ActionRow(self.continue_btn, self.cancel_btn),
                accent_colour=discord.Colour.orange(),
            )
        )

    async def continue_appeal(self, interaction: discord.Interaction):
        lang = BAN_APPEAL_GATE.get(self.modal.language, BAN_APPEAL_GATE["en"])
        await interaction.response.edit_message(view=NoticeContainer(lang["opening"]))
        await self.modal.open_ticket(interaction, self.data)
        self.stop()

    async def cancel_appeal(self, interaction: discord.Interaction):
        lang = BAN_APPEAL_GATE.get(self.modal.language, BAN_APPEAL_GATE["en"])
        await interaction.response.edit_message(view=NoticeContainer(lang["cancelled"]))
        self.stop()

    async def on_timeout(self):
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(
                    view=GateContainer(self.title, self.description, discord.Colour.orange())
                )
