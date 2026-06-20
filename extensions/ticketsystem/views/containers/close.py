from typing import Iterable
import discord

from extensions.ticketsystem.ticket import TicketCategory
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from extensions.ticketsystem.views.inner_buttons import (
    CloseBtn,
    LockBtn,
    OptionsBtn,
    ReportClaimBtn,
    RenameRunBtn,
    RenamePrintCMD,
    BanAppealFindBanBtn,
)


class CloseContainer(discord.ui.LayoutView):
    def __init__(self, buttons: Iterable[discord.ui.Button]):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "If you want to close this ticket or opened it by mistake, please click the blue close button below!"
            ),
            large_seperator(),
            discord.ui.ActionRow(*buttons),
            accent_colour=TICKET_ACCENT,
        )

        self.add_item(container)

    @classmethod
    def for_category(cls, category: TicketCategory, locked: bool = False) -> "CloseContainer":
        buttons: list[discord.ui.Button] = [
            CloseBtn(),
        ]

        if category == TicketCategory.REPORT:
            buttons.append(ReportClaimBtn())
        elif category == TicketCategory.RENAME:
            buttons.extend(
                [
                    RenameRunBtn(),
                    RenamePrintCMD(),
                ]
            )
        elif category in (TicketCategory.BAN_APPEAL, TicketCategory.VPN_BAN_APPEAL):
            buttons.append(BanAppealFindBanBtn())
        buttons.append(LockBtn(label="🔓" if locked else "🔒"))
        buttons.append(OptionsBtn())
        return cls(buttons)
