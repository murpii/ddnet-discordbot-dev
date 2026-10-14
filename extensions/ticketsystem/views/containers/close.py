from typing import Iterable

import discord

from extensions.ticketsystem.ticket import TicketCategory
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from extensions.ticketsystem.views.inner_buttons import (
    BanAppealFindBanBtn,
    CloseBtn,
    LockBtn,
    OptionsBtn,
    RenameHistoryBtn,
    RenamePrintCMD,
    RenameRunBtn,
    ReportClaimBtn,
)


class CloseContainer(discord.ui.LayoutView):
    def __init__(self, buttons: Iterable[discord.ui.Button]):
        super().__init__(timeout=None)

        buttons = list(buttons)
        # an action row holds at most 5 buttons
        rows = [discord.ui.ActionRow(*buttons[start:start + 5]) for start in range(0, len(buttons), 5)]

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "If you want to close this ticket or opened it by mistake, please click the blue close button below!"
            ),
            large_seperator(),
            *rows,
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
                    RenameHistoryBtn(),
                ]
            )
        elif category in (TicketCategory.BAN_APPEAL, TicketCategory.VPN_BAN_APPEAL):
            buttons.append(BanAppealFindBanBtn())
        buttons.append(LockBtn(label="🔓" if locked else "🔒"))
        buttons.append(OptionsBtn())
        return cls(buttons)
