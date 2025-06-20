import discord


class ButtonLinks(discord.ui.View):
    """
    This view displays either a quick join button or a contact URL button depending on the context.
    """
    def __init__(
            self,
            ticket: bool,
            addr: str = None,
            network: str = None,
            contact_url: str = None
    ):
        super().__init__(timeout=None)
        quick_join = discord.ui.Button(
            label='Join Server',
            style=discord.ButtonStyle.url,  # type: ignore
            url=f"https://ddnet.org/connect-to/?addr={addr}/"
        )
        invite = discord.ui.Button(
            label=f'{network} Contact URL',
            style=discord.ButtonStyle.url,  # type: ignore
            url=contact_url
        )
        if not ticket:
            self.add_item(quick_join)
            return
        if network != "DDraceNetwork":
            self.add_item(invite)
        else:
            self.add_item(quick_join)