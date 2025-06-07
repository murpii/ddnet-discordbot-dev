from datetime import datetime, timedelta


class GlobalCooldown:
    def __init__(self, rate, per):
        self.rate = rate
        self.per = per
        self.cooldowns = {}

    def check(self, channel_id):
        now = datetime.now()
        if channel_id in self.cooldowns:
            last_used, rate = self.cooldowns[channel_id]
            if now - last_used < timedelta(seconds=self.per) and rate >= self.rate:
                remaining_time = self.per - (now - last_used).total_seconds()
                return True, remaining_time
        return False, 0

    def update_cooldown(self, channel_id):
        now = datetime.now()
        if channel_id in self.cooldowns:
            last_used, rate = self.cooldowns[channel_id]
            if now - last_used >= timedelta(seconds=self.per):
                self.cooldowns[channel_id] = (now, 1)
            else:
                self.cooldowns[channel_id] = (last_used, rate + 1)
        else:
            self.cooldowns[channel_id] = (now, 1)

global_cooldown = GlobalCooldown(rate=2, per=700)