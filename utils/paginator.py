import discord


class Pages:
    """
    Plain page math over a list of items.
    Keeps track of which page is open and hands out the visible slice.
    """

    def __init__(self, items, per_page: int = 10):
        self.items = list(items)
        self.per_page = max(1, per_page)
        self.page = 0  # zero-based index of the currently open page

    @property
    def total_pages(self) -> int:
        if not self.items:
            return 1
        # round up: 11 items with 4 per page -> 3 pages
        return (len(self.items) + self.per_page - 1) // self.per_page

    @property
    def has_prev(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages - 1

    def current(self) -> list:
        """The items visible on the open page"""
        start = self.page * self.per_page
        return self.items[start:start + self.per_page]

    def flip(self, step: int) -> None:
        """Move forward (+1) or back (-1), clamped to the valid page range"""
        self.page = max(0, min(self.page + step, self.total_pages - 1))


class PageButton(discord.ui.Button):
    """Prev/Next button for paginated views. On click, it flips the shared
    Pages object and re-renders the message with a freshly built view"""

    def __init__(self, pages: Pages, step: int, *, label: str, rebuild, disabled: bool):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled)  # noqa
        self.pages = pages
        self.step = step
        self.rebuild = rebuild

    async def callback(self, interaction: discord.Interaction) -> None:
        self.pages.flip(self.step)
        await interaction.response.edit_message(view=self.rebuild())  # noqa


def page_nav_row(pages: Pages, rebuild) -> discord.ui.ActionRow:
    indicator = discord.ui.Button(
        label=f"{pages.page + 1} / {pages.total_pages}",
        style=discord.ButtonStyle.secondary,  # noqa
        disabled=True,
    )
    return discord.ui.ActionRow(
        PageButton(pages, -1, label="Previous", rebuild=rebuild, disabled=not pages.has_prev),
        indicator,
        PageButton(pages, +1, label="Next", rebuild=rebuild, disabled=not pages.has_next),
    )
