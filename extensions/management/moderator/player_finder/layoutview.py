import discord


class PlayerfinderView(discord.ui.LayoutView):
    # Have to send a ZWSP otherwise discord complains
    def __init__(self, page_content: str = "​"):
        super().__init__()

        children = [discord.ui.TextDisplay(page_content)]
        self.container = discord.ui.Container(*children)
        self.add_item(self.container)


class CustomView(discord.ui.LayoutView):
    def __init__(self, content: str = "*No activity detected.*"):
        super().__init__()
        self.container = discord.ui.Container(
            discord.ui.TextDisplay(content)
        )
        self.add_item(self.container)
