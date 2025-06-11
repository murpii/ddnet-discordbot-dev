import enum


class MapState(enum.Enum):
    TESTING = ""
    RC = "☑"
    WAITING = "💤"
    READY = "✅"
    DECLINED = "❌"
    RELEASED = "🆙"

    def __str__(self) -> str:
        return self.value