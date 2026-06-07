import discord


class CategoryResultsView(discord.ui.LayoutView):
    def __init__(
            self,
            text: str,
            media_items: list[discord.MediaGalleryItem],
    ):
        super().__init__(timeout=None)

        items: list[discord.ui.Item] = [discord.ui.TextDisplay(text)]

        if media_items:
            items.append(discord.ui.MediaGallery(*media_items))

        self.add_item(
            discord.ui.Container(
                *items,
                accent_colour=2210995,
            )
        )


class StatsResultsView(discord.ui.LayoutView):
    def __init__(self, text: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_colour=0x5865F2,
            )
        )
