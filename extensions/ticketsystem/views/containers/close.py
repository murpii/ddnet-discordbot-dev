from typing import Iterable
from discord import SeparatorSpacing
import discord

from extensions.ticketsystem.ticket import TicketCategory
from extensions.ticketsystem.views.inner_buttons import (
    CloseBtn,
    LockBtn,
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
                "If you wish to close this ticket or opened this ticket by mistake, "
                "use either the close button below or type `/close`."
            ),
            discord.ui.Separator(
                spacing=SeparatorSpacing.large,
                visible=True,
            ),
            discord.ui.ActionRow(*buttons),
            accent_colour=2210995,
        )

        self.add_item(container)

    @classmethod
    def for_category(cls, category: TicketCategory, locked: bool = False) -> "CloseContainer":
        buttons: list[discord.ui.Button] = [
            CloseBtn(),
            LockBtn(label="🔓 Unlock Ticket" if locked else "🔒 Lock Ticket"),
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
        elif category == TicketCategory.BAN_APPEAL:
            buttons.append(BanAppealFindBanBtn())

        return cls(buttons)
