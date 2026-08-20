import time
from collections import defaultdict, deque


class GlobalCooldown:
    def __init__(self, rate: int, per: float):
        self.rate = rate
        self.per = per
        self.edits: dict[int, deque] = defaultdict(deque)

    def check(self, channel_id: int) -> tuple[bool, float]:
        edits = self.edits[channel_id]
        now = time.monotonic()
        while edits and now - edits[0] > self.per:
            edits.popleft()
        if len(edits) < self.rate:
            return False, 0.0
        return True, self.per - (now - edits[0])

    def update_cooldown(self, channel_id: int) -> None:
        self.edits[channel_id].append(time.monotonic())


global_cooldown = GlobalCooldown(rate=2, per=600.0)
