import aiohttp

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

MASTER_URL = "https://master1.ddnet.org/ddnet/15/servers.json"


@dataclass
class Icon:
    """
    Icon information for a community.

    Attributes:
        sha256: SHA-256 checksum of the icon asset, if provided.
        url: HTTP(S) URL where the icon can be fetched.
    """
    sha256: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Community:
    """
    Represents a community listed in the master JSON.

    Attributes:
        id: Stable identifier of the community (e.g., 'ddnet').
        name: Human-readable name of the community.
        has_finishes: True if the community tracks finishes; None if unspecified.
        icon: Community icon (hash + URL), if present.
        contact_urls: Contact or invite URLs (Discord, website, etc.).
    """
    id: str
    name: str
    has_finishes: Optional[bool] = None
    icon: Optional[Icon] = None
    contact_urls: List[str] = field(default_factory=list)


@dataclass
class Skin:
    """
    Player skin information.

    Attributes:
        name: Skin name reported by the client (empty if default/unknown).
        color_body: Optional body color integer (engine-specific).
        color_feet: Optional feet color integer (engine-specific).
    """
    name: str = ""
    color_body: Optional[int] = None
    color_feet: Optional[int] = None


@dataclass
class Client:
    """
    Represents one connected client (player or spectator).

    Attributes:
        name: The client's in-game name (as reported).
        clan: Clan tag/name if set; empty string otherwise.
        country: Numeric country code (ISO-3166-like). -1/None means unknown.
        score: Score as reported by the server (-9999 often means N/A).
        is_player: True=player, False=spectator, None=not reported/unknown.
        skin: Skin info, if available.
        afk: True if the client is marked AFK; False/None otherwise.
        team: Team number depending on game type (0 default in DDrace).
    """
    name: str
    clan: str = ""
    country: Optional[int] = None
    score: Optional[int] = None
    is_player: Optional[bool] = None
    skin: Optional[Skin] = None
    afk: Optional[bool] = None
    team: Optional[int] = None


@dataclass
class MapInfo:
    """
    Information about the currently running map.

    Attributes:
        name: Map name currently active on the server.
        sha256: SHA-256 checksum of the map file, if provided.
        size: Map file size in bytes, if provided.
    """
    name: str
    sha256: Optional[str] = None
    size: Optional[int] = None


@dataclass
class Info:
    """
    Operational state and metadata for a server.

    Attributes:
        max_clients: Maximum connections (players + spectators).
        max_players: Maximum number of actual players allowed.
        passworded: True if the server requires a password to join.
        game_type: Reported game type (e.g., 'DDraceNetwork', 'CTF').
        name: Human-readable server name as advertised.
        map: Current map information, if reported.
        version: Server version string reported by the engine.
        client_score_kind: Scoring mode, e.g., 'time' or 'points'.
        requires_login: True if DDNet login is required to join.
        country: Optional country code at info-level if present.
        clients: All connected clients (players + spectators).

    Properties:
        total_clients: Count of connected clients (players + spectators).
        total_players: Estimated number of active players (treats unknown as player).
    """
    max_clients: Optional[int] = None
    max_players: Optional[int] = None
    passworded: Optional[bool] = None
    game_type: str = ""
    name: str = ""
    map: Optional[MapInfo] = None
    version: Optional[str] = None
    client_score_kind: Optional[str] = None
    requires_login: Optional[bool] = None
    country: Optional[int] = None  # some servers include this at info-level
    clients: List[Client] = field(default_factory=list)

    @property
    def total_clients(self) -> int:
        """Total number of connected clients (players + spectators)."""
        return len(self.clients)

    @property
    def total_players(self) -> int:
        """
        Estimated number of active players.

        Many listings omit 'is_player' or only mark spectators explicitly;
        treat missing (None) as a player to avoid undercounting.
        """
        return sum(c.is_player is True or c.is_player is None for c in self.clients)


@dataclass
class Server:
    """
    Represents a single server entry from the master list.

    Attributes:
        addresses: List of addresses including protocol, version, IP, and port
            (e.g., 'tw-0.6+udp://5.57.39.137:8304').
        location: Location in the format '<region>:<country>' (e.g., 'eu:de').
        info: Live server information (players, map, limits, version).
        community: Community ID such as 'ddnet', or None if not affiliated.

    Properties:
        region_country: Tuple of (region, country) split from 'location'.
        primary_address: First advertised address, if available.
    """
    addresses: List[str]
    location: str
    info: Info
    community: Optional[str] = None

    @property
    def region_country(self) -> Tuple[Optional[str], Optional[str]]:
        """Split 'location' into (region, country), e.g., 'eu:de' -> ('eu', 'de')."""
        if ":" in self.location:
            r, c = self.location.split(":", 1)
            return r or None, c or None
        return None, None

    @property
    def ddnet_address(self) -> Optional[str]:
        """Return the first (primary) address string, or None if unavailable."""
        return self.addresses[0] if self.addresses else None

    @property
    def normalized_address(self) -> Optional[str]:
        """
        Returns a normalized "host:port" string for the first advertised address.

        Normalizes IPv4 and IPv6 by removing scheme/version prefixes like
        'tw-0.6+udp://', and ensures IPv6 literals are bracketed.

        Examples:
            'tw-0.6+udp://45.141.57.22:8379'        -> '45.141.57.22:8379'
            'tw-0.7+udp://[2a01:4f8:1c1e::1]:8303'  -> '[2a01:4f8:1c1e::1]:8303'
        """
        if not self.addresses:
            return None

        addr = self.addresses[0]
        _, _, _, host, port = parse_address(addr)
        if not host or not port:
            return None

        # Ensure IPv6 uses brackets
        if ":" in host and not host.startswith("["):
            return f"[{host}]:{port}"

        return f"{host}:{port}"

    @property
    def normalized_addresses(self) -> List[str]:
        """
        Returns a list of unique normalized "host:port" strings for this server.
        IPv4 + IPv6 or genuinely different endpoints.

        Example:
            IPv4 only:
                ['45.141.57.22:8379']

            IPv4 + IPv6:
                ['45.141.57.22:8379', '[2a01:4f8:1c1e::1]:8379']
        """
        seen = set()
        out = []

        for addr in self.addresses:
            _, _, _, host, port = parse_address(addr)
            if not host or not port:
                continue

            # Normalize IPv6
            if ":" in host and not host.startswith("["):
                norm = f"[{host}]:{port}"
            else:
                norm = f"{host}:{port}"

            if norm not in seen:
                seen.add(norm)
                out.append(norm)

        return out


@dataclass
class MasterList:
    """
    Root container for the entire master JSON.

    Attributes:
        communities: All communities known to the master server.
        servers: All discovered servers (across all communities).
    """
    communities: List[Community] = field(default_factory=list)
    servers: List[Server] = field(default_factory=list)


def _get(d: Dict[str, Any], key: str, default=None):
    """
    Safely get a key from a dict with a fallback that normalizes explicit None.

    Args:
        d: Source dictionary.
        key: Key to read.
        default: Fallback value when key is missing or explicitly None.

    Returns:
        The value for 'key' if present and not None; otherwise 'default'.
    """
    v = d.get(key, default)
    return v if v is not None else default


def parse_icon(d: Optional[Dict[str, Any]]) -> Optional[Icon]:
    """
    Parse icon metadata.

    Args:
        d: Dict with 'sha256' and 'url' keys, or None.

    Returns:
        Icon or None.
    """
    return Icon(sha256=_get(d, "sha256"), url=_get(d, "url")) if d else None


def parse_community(d: Dict[str, Any]) -> Community:
    """
    Parse a community entry.

    Args:
        d: Dict describing a community.

    Returns:
        Community instance.
    """
    return Community(
        id=_get(d, "id", ""),
        name=_get(d, "name", ""),
        has_finishes=_get(d, "has_finishes"),
        icon=parse_icon(_get(d, "icon")),
        contact_urls=list(_get(d, "contact_urls", [])) or []
    )


def parse_skin(d: Optional[Dict[str, Any]]) -> Optional[Skin]:
    """
    Parse skin data.

    Args:
        d: Dict with skin fields, or None.

    Returns:
        Skin instance or None.
    """
    if not d:
        return None
    return Skin(
        name=_get(d, "name", ""),
        color_body=_get(d, "color_body"),
        color_feet=_get(d, "color_feet"),
    )


def parse_client(d: Dict[str, Any]) -> Client:
    """
    Parse a connected client entry.

    Args:
        d: Dict describing one client.

    Returns:
        Client instance
    """
    return Client(
        name=_get(d, "name", ""),
        clan=_get(d, "clan", ""),
        country=_get(d, "country"),
        score=_get(d, "score"),
        is_player=_get(d, "is_player"),
        skin=parse_skin(_get(d, "skin")),
        afk=_get(d, "afk"),
        team=_get(d, "team"),
    )


def parse_map(d: Optional[Dict[str, Any]]) -> Optional[MapInfo]:
    """
    Parse map information.

    Args:
        d: Dict with map attributes, or None.

    Returns:
        MapInfo instance or None.
    """
    if not d:
        return None
    return MapInfo(
        name=_get(d, "name", ""),
        sha256=_get(d, "sha256"),
        size=_get(d, "size"),
    )


def parse_info(d: Dict[str, Any]) -> Info:
    """
    Parse the 'info' block for a server.

    Args:
        d: Dict describing server info.

    Returns:
        Info instance.
    """
    return Info(
        max_clients=_get(d, "max_clients"),
        max_players=_get(d, "max_players"),
        passworded=_get(d, "passworded"),
        game_type=_get(d, "game_type", ""),
        name=_get(d, "name", ""),
        map=parse_map(_get(d, "map")),
        version=_get(d, "version"),
        client_score_kind=_get(d, "client_score_kind"),
        requires_login=_get(d, "requires_login"),
        country=_get(d, "country"),
        clients=[parse_client(x) for x in _get(d, "clients", [])],
    )


def parse_server(d: Dict[str, Any]) -> Server:
    """
    Parse one server listing.

    Args:
        d: Dict describing a server entry.

    Returns:
        Server instance.
    """
    return Server(
        addresses=list(_get(d, "addresses", [])) or [],
        location=_get(d, "location", ""),
        community=_get(d, "community"),
        info=parse_info(_get(d, "info", {})),
    )


def parse_master(data: Dict[str, Any]) -> MasterList:
    """
    Parse the entire master JSON payload.

    Args:
        data: Root dictionary loaded from JSON.

    Returns:
        MasterList instance containing communities and servers.
    """
    return MasterList(
        communities=[parse_community(x) for x in _get(data, "communities", [])],
        servers=[parse_server(x) for x in _get(data, "servers", [])],
    )


def find_player(master: MasterList, player_name: str) -> Optional[Tuple[Server, Client]]:
    """
    Locate a specific player in the master list and return both the server
    they are currently on and their corresponding Client object.

    Args:
        master: The parsed MasterList containing all servers and clients.
        player_name: The exact or case-insensitive name of the player to search for.

    Returns:
        A tuple (Server, Client) if the player is found on any server.
        None if the player is not present on any server.
    """
    needle = player_name.lower()

    for server in master.servers:
        for client in server.info.clients:
            if client.name.lower() == needle:
                return server, client

    return None


def find_server_by_ip(master: MasterList, ip_port: str) -> Optional[Server]:
    """
    Find a server either by raw address match or by normalized host:port match.
    """
    for server in master.servers:
        if ip_port in server.addresses:
            return server

        norm = server.normalized_address
        if norm and norm == ip_port:
            return server

    return None


def find_servers_by_community(master: MasterList, community_id: str) -> List[Server]:
    """
    All servers that belong to a specific community (e.g. 'ddnet').
    """
    cid = community_id.lower()
    return [s for s in master.servers if (s.community or "").lower() == cid]


def find_servers_by_region(master: MasterList, region: Optional[str] = None, country: Optional[str] = None) -> List[
    Server]:
    """
    Filter servers by region and/or country code from the 'location' field.

    Args:
        region: 'eu', 'na', 'as', 'sa', etc. If None, don't filter by region.
        country: 'de', 'us', 'ru', etc. If None, don't filter by country.

    Returns:
        List of Server.
    """
    rnorm = region.lower() if region else None
    cnorm = country.lower() if country else None

    def ok(s: Server) -> bool:
        r, c = s.region_country
        if rnorm and (r or "").lower() != rnorm:
            return False
        return not cnorm or (c or "").lower() == cnorm

    return [s for s in master.servers if ok(s)]


def find_servers_by_gametype(master: MasterList, game_type: str) -> List[Server]:
    """
    All servers whose info.game_type matches (case-insensitive exact).
    """
    gt = game_type.lower()
    return [s for s in master.servers if (s.info.game_type or "").lower() == gt]


def find_servers_by_map(master: MasterList, map_name: str, exact: bool = False) -> List[Server]:
    """
    Servers running a given map (exact or substring, case-insensitive).

    Args:
        map_name: Target map string.
        exact: If True, require exact name match; otherwise substring match.

    Returns:
        List of Server.
    """
    needle = map_name.lower()
    out: List[Server] = []
    for s in master.servers:
        m = s.info.map.name.lower() if s.info.map and s.info.map.name else ""
        if (m == needle) if exact else (needle in m):
            out.append(s)
    return out


def count_players(master: MasterList, community_id: Optional[str] = None) -> int:
    """
    Total player count across all servers (or a single community).

    Args:
        community_id: Limit to a community ID (e.g., 'ddnet'), or None for all.

    Returns:
        Sum of Info.total_players across the selected servers.
    """
    servers = find_servers_by_community(master, community_id) if community_id else master.servers
    return sum(s.info.total_players for s in servers)


class AddressParseError(ValueError):
    pass


def parse_address(addr: str) -> Tuple[str, str, str, str, int]:
    if "://" not in addr:
        raise AddressParseError("Missing scheme separator '://'.")
    scheme, rest = addr.split("://", 1)

    tw_tag = None
    version = None
    transport = None

    if scheme:
        parts = scheme.split("+")
        left = parts[0] if parts else ""
        transport = parts[1] if len(parts) > 1 else None

        if "-" in left:
            tw_tag, version = left.split("-", 1)
        else:
            raise AddressParseError("Missing 'tw-x.x' in scheme.")

    if not transport:
        raise AddressParseError("Missing transport (e.g. '+udp').")

    host_port = rest

    if host_port.startswith("["):
        end = host_port.find("]")
        if end == -1:
            raise AddressParseError("Unclosed IPv6 bracket.")
        host = host_port[1:end]
        after = host_port[end + 1:]
        if not after.startswith(":"):
            raise AddressParseError("Missing port after IPv6 literal.")
        try:
            port = int(after[1:])
        except ValueError as e:
            raise AddressParseError("Invalid port.") from e
    elif ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError as e:
            raise AddressParseError("Invalid port.") from e
    else:
        raise AddressParseError("Missing port.")

    if not host:
        raise AddressParseError("Missing host.")

    return tw_tag, version, transport, host, port


async def fetch_master_list(session: aiohttp.ClientSession) -> MasterList:
    """
    HTTP-fetch the master JSON and parse it into objects.

    Args:
        session: An aiohttp ClientSession to perform the request.

    Returns:
        MasterList containing communities and servers.

    Raises:
        aiohttp.ClientError: On network/HTTP errors.
        ValueError: If the response cannot be parsed as JSON.
    """
    async with session.get(MASTER_URL, timeout=10) as resp:
        resp.raise_for_status()
        raw = await resp.json()
        return parse_master(raw)
