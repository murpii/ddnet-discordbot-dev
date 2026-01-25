import discord
from discord import SeparatorSpacing


class CategoryView(discord.ui.LayoutView):
    def __init__(self, category_name: str, text: str, media: list[discord.MediaGalleryItem]):
        super().__init__(timeout=None)
        self.add_item(discord.ui.TextDisplay(text))
        if media:
            self.add_item(discord.ui.Separator(spacing=SeparatorSpacing.large))
            self.add_item(discord.ui.MediaGallery(*media))
        self.add_item(discord.ui.Separator(spacing=SeparatorSpacing.large))


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
