import discord
from discord import SeparatorSpacing


class PlayerfinderView(discord.ui.LayoutView):
    def __init__(self, page_content: str = "​"):
        super().__init__()

        children = [discord.ui.TextDisplay(page_content)]
        self.container = discord.ui.Container(*children)
        self.add_item(self.container)


class CopycatView(discord.ui.LayoutView):
    def __init__(self, content: str = "*No copycat activity detected.*"):
        super().__init__()
        self.container = discord.ui.Container(
            discord.ui.TextDisplay(content)
        )
        self.add_item(self.container)
