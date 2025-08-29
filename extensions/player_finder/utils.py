import re
from collections import defaultdict


async def group_players_by_server(session, url) -> dict:
    resp = await session.get(url)
    data = await resp.json()

    server_players = defaultdict(list)
    for server in data["servers"]:
        addresses = [format_address(addr) for addr in server["addresses"] if format_address(addr)]
        names = [p["name"] for p in server["info"].get("clients", [])]
        for address in addresses:
            server_players[address].extend(names)
    return server_players


async def filter(session, url) -> list:
    gamemodes = [
        "DDNet", "Test", "Tutorial",
        "Block", "Infection", "iCTF",
        "gCTF", "Vanilla", "zCatch",
        "TeeWare", "TeeSmash", "Foot",
        "xPanic", "Monster",
    ]
    resp = await session.get(url)
    data = await resp.json()
    servers = data.get("servers", [])
    ddnet_ips = []
    for entry in servers:
        sv_list = entry.get("servers")
        for mode in gamemodes:
            server_lists = sv_list.get(mode)
            if server_lists is not None:
                ddnet_ips += server_lists
    return ddnet_ips


def format_address(address):
    if address_match := re.match(r"tw-0.6\+udp://([\d.]+):(\d+)", address):
        ip, port = address_match.groups()
        return f"{ip}:{port}"
    return None


async def players(session, url) -> dict:
    resp = await session.get(url)
    data = await resp.json()
    players = defaultdict(list)

    for server in data["servers"]:
        server_addresses = []
        for address in server["addresses"]:
            fmt_addr = format_address(address)
            if fmt_addr is not None:
                server_addresses.append(fmt_addr)
        if "clients" in server["info"]:
            for player in server["info"]["clients"]:
                for address in server_addresses:
                    players[player["name"]].append(
                        (server["info"]["name"], address)
                    )
    return players