import discord

from datetime import datetime, timedelta


async def cooldown_response(interaction: discord.Interaction) -> bool:
    if isinstance(interaction.channel, discord.Thread):
        channel_id = interaction.channel.parent.id
    else:
        channel_id = interaction.channel.id
    on_cooldown, remaining_time = global_cooldown.check(channel_id)
    if on_cooldown:
        msg = (f"Cooldown active. Try again in {remaining_time:.2f} seconds."
               f"-# Map Channels can be updated twice every 15 minutes. This is a Discord limitation.")
        try:
            await interaction.response.send_message(msg, ephemeral=True)  # noqa
        except discord.errors.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)  # noqa
        return True
    return False


class GlobalCooldown:
    """Tracks and enforces a global cooldown for button presses per channel."""
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