import discord


class ServerInfoEmbed(discord.Embed):
    """Server lookup result: type, region, current map, live player count, and
    whether the server is DDNet-affiliated."""

    @classmethod
    def from_server_info(
            cls,
            info: dict | None,
            *,
            ticket: bool = False,
            region: str = None,
    ) -> discord.Embed:
        if not info:
            return cls(
                description="⚠️ That server is not a DDNet or Community server.",
                color=discord.Color.red(),
            )

        server_type = info.get("server_type")
        if server_type == "DDNet":
            server_type = "DDrace"
        network = info.get("network")
        is_ddnet = network == "DDraceNetwork"

        title = f"{info.get('name')} Server Info"
        players = info.get("players")
        max_players = info.get("max_players")
        if players is not None and max_players:
            title += f" ({players}/{max_players})"

        embed = cls(
            title=title,
            color=discord.Color.green() if is_ddnet else discord.Color.orange(),
        )

        if not is_ddnet:
            warning = "This server is **NOT** affiliated with DDNet."
            if ticket and network is not None:
                warning += "\nClick the contact URL button and ask for help there instead."
            embed.add_field(name="⚠️ Warning", value=warning, inline=False)

        embed.add_field(name="Country", value=region, inline=True)
        embed.add_field(name="Server Type", value=server_type, inline=True)
        if game_map := info.get("map"):
            embed.add_field(name="Map", value=game_map, inline=True)

        if icon := info.get("icon"):
            embed.set_thumbnail(url=icon)

        return embed


class ServerLinksView(discord.ui.View):
    def __init__(
            self,
            addr: str,
            *,
            network: str = None,
            is_ddnet: bool = False,
            ticket: bool = False,
            contact_url: str = None,
    ):
        super().__init__(timeout=None)
        if not ticket or is_ddnet:
            self.add_item(discord.ui.Button(
                label="Join Server",
                style=discord.ButtonStyle.url,  # noqa
                url=f"https://ddnet.org/connect-to/?addr={addr}/",
            ))
        elif contact_url:
            self.add_item(discord.ui.Button(
                label=f"{network} Contact URL",
                style=discord.ButtonStyle.url,  # noqa
                url=contact_url,
            ))
