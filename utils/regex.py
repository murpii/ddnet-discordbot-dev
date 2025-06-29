BAN_REF_RE = (
    r"!ban "
    r"(?P<IP>\d{1,3}(?:\.\d{1,3}){3}) *"
    r"(?P<name>'[^']*'|\"[^\"]*\"|[^'\"\s]+)? *"
    r"(?P<duration>\d+[a-zA-Z]{1,2}) *"
    r"(?P<reason>.+)"
)


BAN_RE = (
    r"(?P<author>\w+) banned (?P<banned_user>.+?) `(?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})` until "
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)