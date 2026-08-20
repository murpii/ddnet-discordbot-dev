import re

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) [A-Z] (\w+): (.*)$")
LINE_MARKERS = {"join": "+", "leave": "-"}
ENTER_RE = re.compile(
    r"^player has entered the game\. ClientId=(\d+) addr=<\{(.+?)\}> sixup=(\d)"
)
VERSION_RE = re.compile(r"^cid=(\d+) version=(\d+)")
ENTERED_CHAT_RE = re.compile(r"^\*\*\* '(.*)' entered and joined the game$")
LEFT_CHAT_RE = re.compile(r"^\*\*\* '(.*)' has left the game(?: \((.*)\))?$")
LEAVE_RE = re.compile(r"^leave player='(-?\d+):(.*)'$")
PLAYER_CHAT_RE = re.compile(r"^(-?\d+):(-?\d+):(.*)$")
NAME_WIDTH_CAP = 24
SYSTEM_KEEP_WORDS = ("vote", "kick")
CONTEXT_SEPARATOR = "--"
GAP_ROWS = 3
HIT_GUTTER = ">>> "
CONTEXT_GUTTER = "    "
KIND_GROUPS = {
    "chat": ("chat",),
    "connections": ("join", "leave"),
    "system": ("system",),
}


def parse_player_chat(msg: str):
    match = PLAYER_CHAT_RE.match(msg)
    if not match:
        return None
    cid, team, rest = match.group(1), int(match.group(2)), match.group(3)
    if ": " in rest:
        name, text = rest.split(": ", 1)
    else:
        name, text = rest, ""
    return cid, team, name, text


def render_join_detail(pending: dict) -> str:
    if pending["version"]:
        client = f"client={pending['version']}"
    elif pending["sixup"] == "1":
        client = "0.7 client"  # 0.7 clients don't log a version line
    else:
        client = "client=Unknown"
    return f">> JOINED [{client} | addr={pending['ip'] or '?'}]"


def parse_chat(cat: str, msg: str):
    parsed = parse_player_chat(msg)
    if parsed is None:
        return None
    cid, team, name, text = parsed
    if cat == "teamchat" or team >= 0:
        text = f"[team {team}] {text}"
    return cid, name, text


def keep_system(msg: str) -> bool:
    lowered = msg.lower()
    return any(word in lowered for word in SYSTEM_KEEP_WORDS)


def kept_records(lines):
    pending = None
    leave_reasons = {}
    client_ips = {}  # cid -> addr, so a leave line can show the address it joined with

    def flush():
        nonlocal pending
        if pending is not None:
            yield ("join", pending["date"], pending["time"], pending["cid"],
                   pending["name"] or "?", render_join_detail(pending))
            pending = None

    for raw in lines:
        match = LINE_RE.match(raw.rstrip("\n"))
        if not match:
            continue
        date, time, cat, msg = match.groups()

        if cat == "server":
            enter = ENTER_RE.match(msg)
            if enter:
                yield from flush()
                cid, ip, sixup = enter.groups()
                client_ips[cid] = ip
                pending = {"date": date, "time": time, "cid": cid,
                           "ip": ip, "sixup": sixup, "name": None,
                           "version": None}
            continue

        if cat == "game":
            leave = LEAVE_RE.match(msg)
            if leave:
                yield from flush()
                cid, name = leave.groups()
                reason = leave_reasons.pop(name, "")
                addr = client_ips.pop(cid, "")
                detail = f"<< DISCONNECTED ({reason})" if reason else "<< DISCONNECTED"
                if addr:
                    detail = f"{detail} [addr={addr}]"
                yield ("leave", date, time, cid, name, detail)
            continue

        if cat == "ddnet":
            version = VERSION_RE.match(msg)
            if version and pending and pending["cid"] == version.group(1):
                pending["version"] = version.group(2)
                yield from flush()
            continue

        if cat not in ("chat", "teamchat"):
            continue

        if cat == "chat":
            joined = ENTERED_CHAT_RE.match(msg)
            if joined:  # "*** 'name' entered and joined"
                if pending is not None and pending["name"] is None:
                    pending["name"] = joined.group(1)
                else:
                    yield from flush()
                    yield ("join", date, time, "?", joined.group(1), ">> joined")
                continue
            if msg.startswith("*** "):
                left = LEFT_CHAT_RE.match(msg)
                if left:  # the game leave line carries the id
                    if left.group(2):
                        leave_reasons[left.group(1)] = left.group(2)
                    continue
                if keep_system(msg[4:]):
                    yield from flush()
                    yield ("system", date, time, "?", "***", msg[4:])
                continue  # other system messages dropped

        parsed = parse_chat(cat, msg)
        if parsed is None:
            continue
        cid, name, text = parsed
        yield from flush()
        yield ("chat", date, time, cid, name, text)

    yield from flush()


def format_line(rec, width: int, line_no: int, number_width: int) -> str:
    kind, date, time, cid, name, text = rec
    marker = LINE_MARKERS.get(kind, " ")
    head = f"{marker}{line_no:>{number_width}} <{date} {time}>  [ID:{cid:>2}]  "
    if kind == "chat":
        return f"{head}{name:>{width}}:  {text}"
    return f"{head}{name:>{width}}   {text}"


def link_joins_to_leaves(records: list) -> None:
    open_joins = {}
    for index, rec in enumerate(records):
        kind, cid = rec[0], rec[3]
        if kind == "join" and cid != "?":
            open_joins[cid] = index
        elif kind == "leave":
            join_index = open_joins.pop(cid, None)
            if join_index is not None:
                join = records[join_index]
                records[join_index] = (*join[:5], f"{join[5]} [DISCONNECTED @ line {index + 1}]")
                records[index] = (*rec[:5], f"{rec[5]} [CONNECTED @ line {join_index + 1}]")


def filter_keys(records) -> list[tuple[str, str]]:
    shared = {}

    def share(text: str) -> str:
        return shared.setdefault(text, text)

    return [(share(rec[0]), share(rec[4].lower())) for rec in records]


def build_log(raw_text: str) -> tuple[list[tuple[str, str]], list[str]]:
    records = list(kept_records(raw_text.splitlines()))
    link_joins_to_leaves(records)
    width = min(max((len(rec[4]) for rec in records), default=0), NAME_WIDTH_CAP)
    number_width = len(str(len(records)))
    lines = [
        format_line(rec, width, line_no, number_width)
        for line_no, rec in enumerate(records, start=1)
    ]
    return filter_keys(records), lines


def clean_log(raw_text: str) -> str:
    return "\n".join(build_log(raw_text)[1])


def compile_query(query: str):
    query = query.strip()
    if len(query) > 2 and query.startswith("/") and query.endswith("/"):
        return re.compile(query[1:-1], re.IGNORECASE).search
    lowered = query.lower()
    return lambda line: lowered in line.lower()


def matching_indices(keys, lines, query="", names=(), kind="") -> list[int]:
    test = compile_query(query) if query.strip() else None
    wanted = [name.strip().lower() for name in names if name.strip()]
    kinds = KIND_GROUPS.get(kind, ())
    hits = []
    for index, (line_kind, line_name) in enumerate(keys):
        if kinds and line_kind not in kinds:
            continue
        if wanted and not any(name in line_name for name in wanted):
            continue
        if test and not test(lines[index]):
            continue
        hits.append(index)
    return hits


def mark_hit(line: str, is_hit: bool) -> str:
    return f"{line[:1]}{HIT_GUTTER if is_hit else CONTEXT_GUTTER}{line[1:]}"


def filter_log(keys, lines, *, query="", names=(), kind="",
               before=0, after=0) -> tuple[list[str], int]:
    hits = matching_indices(keys, lines, query, names, kind)
    if not hits:
        return [], 0

    keep = set()
    for index in hits:
        keep.update(range(max(0, index - before), min(len(lines), index + after + 1)))
    with_context = bool(before or after)
    hit_indices = set(hits)
    gap = [CONTEXT_SEPARATOR] * GAP_ROWS if with_context else []

    output = []
    previous = None
    for index in sorted(keep):
        if previous is not None and index != previous + 1:
            output.extend(gap)
        line = lines[index]
        output.append(mark_hit(line, index in hit_indices) if with_context else line)
        previous = index
    return output, len(hits)
