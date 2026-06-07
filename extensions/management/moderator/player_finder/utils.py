import re
from collections import defaultdict


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
