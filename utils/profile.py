import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


@dataclass(slots=True, kw_only=True)
class PlayerProfile:
    name: str
    points: int
    first_finish: datetime | None
    latest_finish: datetime | None
    favorite_server: str
    last_rename: datetime | None
    next_eligible_rename: datetime

    def __repr__(self) -> str:
        data = asdict(self)
        for key in ("first_finish", "latest_finish", "last_rename", "next_eligible_rename"):
            if data[key] is not None:
                data[key] = str(data[key])
        return json.dumps(data, indent=4)

    @classmethod
    async def from_database(cls, bot: "DDNet", name: str) -> "PlayerProfile":
        fetch_stats = """
                      SELECT (SELECT Points FROM record_points WHERE Name = %s)                                  AS Points,
                             (SELECT Timestamp
                              FROM record_race
                              WHERE Name = %s
                              ORDER BY Timestamp DESC
                              LIMIT 1)                                                                           AS LatestTimestamp,
                             (SELECT Timestamp
                              FROM record_race
                              WHERE Name = %s
                              ORDER BY Timestamp
                              LIMIT 1)                                                                           AS FirstTimestamp \
                      """
        stats = await bot.fetch(fetch_stats, name, name, name, fetchall=False)

        fetch_server = """
                       SELECT Server
                       FROM record_race
                       WHERE Name = %s
                       GROUP BY Server
                       ORDER BY COUNT(*) DESC
                       LIMIT 1 \
                       """
        server = await bot.fetch(fetch_server, name, fetchall=False)

        fetch_eligible = """
                         SELECT MAX(Timestamp) AS LastRename
                         FROM record_rename
                         WHERE Name = %s; \
                         """
        eligible = await bot.fetch(fetch_eligible, name, fetchall=False)

        return cls(
            name=name,
            points=stats[0] if stats else 0,
            latest_finish=stats[1] if stats else None,
            first_finish=stats[2] if stats else None,
            favorite_server=server[0] if server else "N/A",
            last_rename=eligible[0] if eligible else None,
            next_eligible_rename=(eligible[0] + timedelta(days=365)) if eligible and eligible[0] else datetime.now()
        )
