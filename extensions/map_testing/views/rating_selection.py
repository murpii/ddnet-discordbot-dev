import discord

from extensions.map_testing.submission import Submission
from extensions.map_testing.map_channel import MapState
from extensions.map_testing.scores import add_score
from extensions.map_testing.cooldown import global_cooldown
from extensions.map_testing.utils import debug_check
from utils.misc import rating
from utils.checks import has_map
from constants import Roles


class RatingSelect(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        options = rating()
        self.select = discord.ui.Select(placeholder="Choose a rating...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def ready_callback(self, interaction: discord.Interaction, rating: str = None):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa

        file = None
        eph_msg = None
        embed = None
        add = ""

        # Handle map in TESTING state
        if map_channel.state == MapState.TESTING:
            await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
            await map_channel.set_state(state=MapState.RC, set_by=interaction.user.mention)
            global_cooldown.update_cooldown(interaction.channel.parent.id)

            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                interaction.user,
                category="MapTesting/RC",
                string=f"\"{map_channel.name}\" has been set to RELEASE CANDIDATE."
            )
            await map_channel.changelog_paginator.update_changelog()
            add_score(interaction.user.id, "READY")

            user_roles = {role.id for role in interaction.user.roles}

            if user_roles.intersection({Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS}):
                embed = discord.Embed(
                    title="⭐ Channel state set to Release Candidate!",
                    description="First ready set by Trial Tester. "
                    "Map needs to be tested again by an official tester before fully evaluated.\n\n"
                    f"Suggested rating: {rating}",
                    colour=discord.Color.yellow()
                )
            else:
                embed = discord.Embed(
                    title="⭐ Channel state set to Release Candidate!",
                    description="First ready set. "
                    "It needs to be tested again by a different tester before fully evaluated.\n\n"
                    f"Suggested {rating}",
                    colour=discord.Color.yellow()
                )

            eph_msg = "Map channel state has been changed to RC."

        elif map_channel.state == MapState.RC:
            await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
            pins = await map_channel.pins()
            subm = Submission(pins[0])
            add = "Optimized:"

            if await debug_check(subm, interaction, r_event=True):
                if not interaction.response.is_done():  # noqa
                    await interaction.delete_original_response()
                return

            await map_channel.set_state(state=MapState.READY, set_by=interaction.user.mention)
            global_cooldown.update_cooldown(interaction.channel.parent.id)
            await map_channel.changelog_paginator.add_changelog(
                map_channel,
                interaction.user,
                category="MapTesting/READY",
                string=f"\"{map_channel.name}\" has been set to state READY."
            )
            await map_channel.changelog_paginator.update_changelog()
            add_score(interaction.user.id, "READY")

            if pins[0].content.startswith("Optimized"):
                em_msg = f"Optimized version: {pins[0].jump_url}\n"
            else:
                stdout, file = await subm.edit_map("--remove-everything-unused", "--shrink-tiles-layers")
                em_msg = (
                    f"Optimized version attached.\nChangelog:\n```{stdout}```\n" if stdout
                    else "Optimized version attached.\n"
                )

            if unoptimized_map := next(
                (pin for pin in pins if has_map(pin)), None
            ):
                em_msg += f"Unoptimized version: {unoptimized_map.jump_url}"

            embed = discord.Embed(
                title=f"⭐ {map_channel.name} is now ready to be released!",
                description=f"{rating}\n"
                            f"\n\n"
                            f"{em_msg}",
                colour=discord.Color.green()
            )

            eph_msg = "Map channel has been set to READY."

        await map_channel.send(content=add, embed=embed)
        if file:
            await map_channel.send(file=file)
        await interaction.edit_original_response(content=eph_msg)

    async def callback(self, interaction: discord.Interaction):
        selected_rating = self.select.values[0]
        selected_label = next(option.label for option in rating() if option.value == selected_rating)
        await self.ready_callback(interaction, selected_label)
