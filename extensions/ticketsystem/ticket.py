import asyncio
from pprint import pformat
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Union

import discord
from discord import PermissionOverwrite
from utils.profile import PlayerProfile


@dataclass(slots=True, kw_only=True)
class AppealData:
    name: str
    address: str
    dnsbl: str
    reason: str
    appeal: str
    profile: PlayerProfile | None = None

    def __repr__(self) -> str:
        return pformat(asdict(self), width=80, sort_dicts=False)


@dataclass(slots=True, kw_only=True)
class RenameData:
    old_profile: PlayerProfile
    new_profile: PlayerProfile

    def __repr__(self) -> str:
        from pprint import pformat
        data = {
            'old_profile': {
                'name': self.old_profile.name,
                'points': self.old_profile.points,
                'favorite_server': self.old_profile.favorite_server,
            },
            'new_profile': {
                'name': self.new_profile.name,
                'points': self.new_profile.points,
                'favorite_server': self.new_profile.favorite_server,
            }
        }
        return pformat(data, width=80, sort_dicts=False)


class TicketCategory(Enum):
    REPORT = "report"
    RENAME = "rename"
    BAN_APPEAL = "ban-appeal"
    VPN_BAN_APPEAL = "vpn-ban-appeal"
    COMPLAINT = "complaint"
    ADMIN_MAIL = "admin-mail"
    COMMUNITY_APP = "community-app"


class TicketState(Enum):
    UNCLAIMED = ""
    CLAIMED = "✅"
    WAITING_FOR_RESPONSE = "☑"


@dataclass(slots=True, kw_only=True)
class Ticket:
    channel: Optional[discord.TextChannel] = None
    creator: Union[discord.Member, discord.User] = None
    category: TicketCategory
    state: TicketState = TicketState.UNCLAIMED
    start_message: Optional[discord.Message] = None
    close_message: Optional[discord.Message] = None
    rename_data: RenameData | None = None
    appeal_data: AppealData | None = None
    being_closed: bool = False
    locked: bool = False
    lock: asyncio.Lock = field(init=False, repr=False)
    overwrites: dict[discord.Role | discord.Member, PermissionOverwrite] = field(init=False, repr=False)

    def __post_init__(self):
        self.lock = asyncio.Lock()

    def __repr__(self) -> str:
        r = {
            'category': self.category.value,
            'state': self.state.value,
            'being_closed': self.being_closed,
            'locked': self.locked,
            'rename_data': (asdict(self.rename_data) if self.rename_data else None),
            'appeal_data': (asdict(self.appeal_data) if self.appeal_data else None),
        }

        return pformat(r, width=100, sort_dicts=False)

    def get_overwrites(
            self,
            interaction: discord.Interaction
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """Returns the overwrites based on the ticket category"""
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_threads=True, pin_messages=True
            ),
            self.creator: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        config = interaction.client.config
        roles_key = f"{self.category.value}"

        if config.has_option("TICKETS", roles_key):
            role_ids = [
                int(r.strip())
                for r in config.get("TICKETS", roles_key).split(",")
                if r.strip().isdigit()
            ]
            for role_id in role_ids:
                if role_obj := interaction.guild.get_role(role_id):
                    perms = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    # ban appeals open a private mod review thread
                    if self.category == TicketCategory.BAN_APPEAL:
                        perms.manage_threads = True
                    overwrites[role_obj] = perms
        return overwrites

    async def set_state(self, state: TicketState) -> None:
        """|coro|
        Update the state of the ticket channel by modifying its name with a symbol.

        Args:
            state (TicketState): The new state to assign to the ticket channel.
        """
        self.state = state
        prefix = state.value
        if not self.channel.name.startswith(prefix):
            await self.channel.edit(name=f"{prefix}{self.channel.name}")
