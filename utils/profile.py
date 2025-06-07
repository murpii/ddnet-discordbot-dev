from dataclasses import dataclass
from datetime import datetime, timedelta
import json


@dataclass(slots=True, kw_only=True)
class PlayerProfile:
    name: str
    points: int
    first_finish: datetime or None
    latest_finish: datetime or None
    favorite_server: str
    last_rename: datetime or None
    next_eligible_rename: datetime

    def __repr__(self):
        return json.dumps(
            {
                "name": self.name,
                "points": self.points,
                "first_finish": str(self.first_finish) if self.first_finish else None,
                "latest_finish": str(self.latest_finish) if self.latest_finish else None,
                "favorite_server": self.favorite_server,
                "last_rename": str(self.last_rename) if self.last_rename else None,
                "next_eligible_rename": str(self.next_eligible_rename) if self.next_eligible_rename else None
            },
            indent=4
        )

    @classmethod
    async def from_database(cls, bot, name: str) -> "PlayerProfile":
        fetch_stats = """
        SELECT
            (SELECT Points FROM record_points WHERE Name = %s) AS Points,
            (SELECT Timestamp FROM record_race WHERE Name = %s ORDER BY Timestamp DESC LIMIT 1) AS LatestTimestamp,
            (SELECT Timestamp FROM record_race WHERE Name = %s ORDER BY Timestamp LIMIT 1) AS FirstTimestamp
        """
        stats = await bot.fetch(fetch_stats, name, name, name, fetchall=False)

        fetch_server = """
        SELECT Server FROM record_race
        WHERE Name = %s
        GROUP BY Server
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """
        server = await bot.fetch(fetch_server, name, fetchall=False)

        fetch_eligible = """
        SELECT MAX(Timestamp) AS LastRename
        FROM record_rename
        WHERE Name = %s;
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