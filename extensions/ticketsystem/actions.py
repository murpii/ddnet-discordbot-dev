import discord

from .cooldown import global_cooldown
from .ticket import Ticket, TicketCategory
from .views.containers.ban_appeal.ban_appeal_change import BanAppealChangeContainer
from .views.containers.ban_appeal.vpn_ban_appeal_change import (
    VpnBanAppealChangeContainer,
)
from .views.containers.close import CloseContainer
from .views.containers.rename.rename_change import RenameChangeContainer

CHANGE_CONTAINERS = {
    TicketCategory.RENAME: RenameChangeContainer,
    TicketCategory.BAN_APPEAL: BanAppealChangeContainer,
    TicketCategory.VPN_BAN_APPEAL: VpnBanAppealChangeContainer,
}


async def apply_category_change(
        interaction: discord.Interaction,
        manager,
        ticket: Ticket,
        category_enum: TicketCategory,
) -> None:
    if container_cls := CHANGE_CONTAINERS.get(category_enum):
        view = container_cls(ticket)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()
        # lock the ticket while we wait for the extra info, and refresh the close
        # bar so its lock button shows the new state
        if not ticket.locked:
            await manager.toggle_ticket_lock(ticket=ticket, send_msg=False)
            await ticket.close_message.edit(
                view=CloseContainer.for_category(ticket.category, locked=ticket.locked)
            )
        return

    await manager.update_ticket(interaction, ticket=ticket, category=category_enum)


async def invite_entity(channel: discord.TextChannel, entity) -> str:
    target = entity
    if isinstance(entity, discord.User):  # picked someone who isn't a member here
        target = channel.guild.get_member(entity.id)
        if target is None:
            return f"{entity.mention} is not a member of this server."

    await channel.set_permissions(target, view_channel=True, send_messages=True)
    suffix = " role" if isinstance(entity, discord.Role) else ""
    return f"{entity.mention}{suffix} has been added to the channel."


async def rename_ticket_channel(ticket: Ticket, new_name: str) -> str:
    prefix = ticket.state.value  # "", "✅" or "☑"
    cleaned = new_name.strip()
    if prefix and cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix):].strip()
    if not cleaned:
        return "Please provide a name."

    on_cooldown, wait = global_cooldown.check(ticket.channel.id)
    if on_cooldown:
        minutes = int(wait // 60) + 1
        return (
            f"Discord only allows 2 channel renames every 10 minutes. "
            f"Try again in about {minutes} minute(s)."
        )
    global_cooldown.update_cooldown(ticket.channel.id)

    await ticket.channel.edit(name=f"{prefix}{cleaned}"[:100])
    return f"Channel renamed to **{ticket.channel.name}**."
