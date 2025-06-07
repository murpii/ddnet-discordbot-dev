BAN_REF_RE = (
    r"!ban (?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}) *"
    r"(?P<name>'[^']*'|\"[^\"]*\"|[^'\"\s]+)? *"
    r"(?P<duration>\d+[a-zA-Z]{1,2}) *"
    r"(?P<reason>.+)"
)