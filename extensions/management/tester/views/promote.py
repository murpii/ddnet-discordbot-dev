"""Trial Tester suggestion votes.

The hub button opens PromoteStartView: pick a candidate, write a short
nomination. Submitting creates a private thread in Channels.TESTER_CHAT
holding one persistent vote panel (TrialVoteView). Every Tester is
pulled into the thread and can vote For or Against; the buttons edit the
panel in place, so the tally is always visible.

The Promote button stays enabled: non-admins need more For than Against
votes plus a 3-day minimum, while Admins can promote regardless of both
(the click enforces this). Clicking Promote does
not assign a role directly: the candidate gets a DM (RoleChoiceView)
asking whether they want Trial Tester or Trial Tester (excl.
tournaments); their choice assigns the role and announces it in the
tester chat. Dismiss is always available and closes the vote without
promoting.

Vote state lives in data/tester-hub/votes.json keyed by the panel
message id (see votes.py), so all buttons keep working after restarts:
setup() registers bare TrialVoteView and RoleChoiceView instances whose
custom_ids route the clicks of every panel and DM.
"""
import logging
import time

import discord
from discord.ext import commands, tasks

from constants import Channels, Guilds, Roles
from utils.containers import INFO_ACCENT, NoticeView, separator
from utils.text import clip
from utils.checks import is_staff
from extensions.management.hub import staff_guard
from extensions.management.tester import votes
from extensions.management.tester.bans import TESTER_HUB_ROLES

log = logging.getLogger()

# how long a vote has to run before "Promote" can unlock
PROMOTE_DELAY = 3 * 24 * 60 * 60

ROLE_LABELS = {
    "TRIAL_TESTER": "Trial Tester",
    "TRIAL_TESTER_EXCL_TOURNAMENTS": "Trial Tester (excl. tournaments)",
}


def vote_counts(state: dict) -> tuple:
    in_favour = sum(bool(vote["for"])
                    for vote in state["votes"].values())
    return in_favour, len(state["votes"]) - in_favour


def promote_ready(state: dict) -> tuple:
    """Whether the Promote button may be used, plus the reason if not"""
    if time.time() - state["started_ts"] < PROMOTE_DELAY:
        return False, "the vote has to run for 3 days first"
    in_favour, against = vote_counts(state)
    if in_favour <= against:
        return False, "there are not more \"For\" than \"Against\" votes"
    return True, ""


def names_line(label: str, entries: list) -> str:
    names = ", ".join(entries)
    return f"**{label} ({len(entries)}):** {clip(names, 600) if names else '-'}"


def render_vote_text(state: dict | None) -> str:
    if not state:  # the bare instance registered for persistence
        return "# Trial Tester vote"

    in_favour = [vote["name"] for vote in state["votes"].values() if vote["for"]]
    against = [vote["name"] for vote in state["votes"].values() if not vote["for"]]

    lines = [
        "# Trial Tester vote",
        f"**Candidate:** <@{state['candidate_id']}> ({state['candidate_name']})\n",
        f"Nominated by <@{state['nominator_id']}> <t:{state['started_ts']}:R>",
        f"**Reasoning:**\n{state['reason']}",
        "### Votes",
        names_line("For", in_favour),
        names_line("Against", against),
    ]

    decided = state.get("decided")
    if decided is None:
        unlock_ts = state["started_ts"] + PROMOTE_DELAY
        if time.time() < unlock_ts:
            promote_note = (
                f"Promote unlocks <t:{unlock_ts}:R> if \"For\" outweighs \"Against\" "
                "(Admins can override)"
            )
        else:
            promote_note = "Promote is available once \"For\" outweighs \"Against\""
        lines += [
            "",
            f"-# {promote_note}. \nVoting again replaces your previous vote, "
            "\"Dismiss\" is always available.",
        ]
    elif decided["outcome"] == "dismissed":
        lines += [
            "",
            f"**Outcome:** {state['candidate_name']} was not promoted "
            f"(decided by {decided['by_name']} <t:{decided['ts']}:R>).",
        ]
    elif state.get("role_assigned"):
        lines += [
            "",
            f"**Outcome:** {state['candidate_name']} was promoted and got the "
            f"{ROLE_LABELS[state['role_assigned']]} role "
            f"(decided by {decided['by_name']} <t:{decided['ts']}:R>).",
        ]
    else:
        lines += [
            "",
            f"**Outcome:**\n"
            f"Promotion approved by {decided['by_name']} "
            f"<t:{decided['ts']}:R>.\n"
            f"{state['candidate_name']} picks their "
            "role via DM, the announcement follows in the tester chat.",
        ]
    return "\n".join(lines)


class VoteButton(discord.ui.Button):
    def __init__(self, *, in_favour: bool):
        super().__init__(
            label="For" if in_favour else "Against",
            style=discord.ButtonStyle.success if in_favour else discord.ButtonStyle.danger,  # noqa
            custom_id=f"TesterVote:{'for' if in_favour else 'against'}",
        )
        self.in_favour = in_favour

    async def callback(self, interaction: discord.Interaction) -> None:
        state = votes.get_vote(interaction.message.id)
        if state is None:
            await interaction.response.send_message(
                view=NoticeView("The stored data of this vote is gone."), ephemeral=True
            )
            return
        if state.get("decided"):
            await interaction.response.send_message(
                view=NoticeView("This vote has already concluded."), ephemeral=True
            )
            return

        state["votes"][str(interaction.user.id)] = {
            "for": self.in_favour,
            "name": interaction.user.display_name,
        }
        state["rendered_ready"] = promote_ready(state)[0]
        votes.set_vote(interaction.message.id, state)
        await interaction.response.edit_message(view=TrialVoteView(state))


class RetractVoteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Retract vote",
            style=discord.ButtonStyle.secondary,  # noqa
            custom_id="TesterVote:retract",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        state = votes.get_vote(interaction.message.id)
        if state is None or state.get("decided"):
            await interaction.response.send_message(
                view=NoticeView("There is nothing to retract here."), ephemeral=True
            )
            return
        if state["votes"].pop(str(interaction.user.id), None) is None:
            await interaction.response.send_message(
                view=NoticeView("You have not voted yet."), ephemeral=True
            )
            return

        state["rendered_ready"] = promote_ready(state)[0]
        votes.set_vote(interaction.message.id, state)
        await interaction.response.edit_message(view=TrialVoteView(state))


class PromoteButton(discord.ui.Button):
    """
    Concludes a successful vote. 
    Note: Does not assign a role itself. The candidate picks the role variant via DM (RoleChoiceView).
    """

    def __init__(self):
        super().__init__(
            label="Promote",
            style=discord.ButtonStyle.primary,  # noqa
            custom_id="TesterVote:promote",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        state = votes.get_vote(interaction.message.id)
        if state is None:
            await interaction.response.send_message(
                view=NoticeView("The stored data of this vote is gone."), ephemeral=True
            )
            return
        if state.get("decided"):
            await interaction.response.send_message(
                view=NoticeView("This vote has already concluded."), ephemeral=True
            )
            return

        # admins can force a promotion regardless of the vote weighting and the
        # 3 day minimum. Everyone else needs both.
        if not is_staff(interaction.user, roles=[Roles.ADMIN]):
            in_favour, against = vote_counts(state)
            if in_favour <= against:
                await interaction.response.send_message(
                    view=NoticeView(
                        "Promote is locked: there are not more \"For\" than \"Against\" "
                        "votes. Only Admins can bypass this."
                    ),
                    ephemeral=True,
                )
                return

            unlock_ts = state["started_ts"] + PROMOTE_DELAY
            if time.time() < unlock_ts:
                await interaction.response.send_message(
                    view=NoticeView(
                        "Promote is locked: the vote has to run for 3 days first "
                        f"(unlocks <t:{unlock_ts}:R>). Only Admins can bypass this."
                    ),
                    ephemeral=True,
                )
                return

        try:
            member = (
                    interaction.guild.get_member(state["candidate_id"])
                    or await interaction.guild.fetch_member(state["candidate_id"])
            )
        except discord.NotFound:
            await interaction.response.send_message(
                view=NoticeView("The candidate is no longer on this server."), ephemeral=True
            )
            return

        await interaction.response.defer()

        state["decided"] = {
            "outcome": "promoted",
            "by": interaction.user.id,
            "by_name": interaction.user.display_name,
            "ts": int(time.time()),
        }

        try:
            dm_message = await member.send(view=RoleChoiceView())
        except discord.Forbidden:
            # DMs closed: assign the regular role directly so nothing stalls
            role = interaction.guild.get_role(Roles.TRIAL_TESTER)
            try:
                await member.add_roles(role, reason=f"Trial Tester vote, concluded by {interaction.user}")
            except discord.Forbidden:
                state["decided"] = None  # vote stays open
                await interaction.followup.send(
                    view=NoticeView("I am not allowed to assign the Trial Tester role."),
                    ephemeral=True,
                )
                return

            state["role_assigned"] = "TRIAL_TESTER"
            await announce_promotion(interaction.client, member, "TRIAL_TESTER", chose=False)
            next_steps = (
                f"{member.mention} could not be reached via DM, so they got the "
                "regular Trial Tester role right away. The tester chat has been notified."
            )
        else:
            state["dm_message_id"] = dm_message.id
            next_steps = (
                f"Vote concluded. {member.mention} received a DM to choose between "
                "Trial Tester and Trial Tester (excl. tournaments); as soon as they "
                "pick, the role is assigned and a message is posted in the tester chat."
            )

        votes.set_vote(interaction.message.id, state)
        await interaction.edit_original_response(view=TrialVoteView(state))
        await interaction.followup.send(view=NoticeView(next_steps), ephemeral=True)

        log.info(
            "TesterHub: %s concluded the Trial Tester vote for %s: promoted",
            interaction.user, state["candidate_name"],
        )
        thread = interaction.message.channel
        if isinstance(thread, discord.Thread):
            await thread.edit(archived=True)


class DismissButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Dismiss",
            style=discord.ButtonStyle.secondary,  # noqa
            custom_id="TesterVote:dismiss",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        state = votes.get_vote(interaction.message.id)
        if state is None:
            await interaction.response.send_message(
                view=NoticeView("The stored data of this vote is gone."), ephemeral=True
            )
            return
        if state.get("decided"):
            await interaction.response.send_message(
                view=NoticeView("This vote has already concluded."), ephemeral=True
            )
            return

        state["decided"] = {
            "outcome": "dismissed",
            "by": interaction.user.id,
            "by_name": interaction.user.display_name,
            "ts": int(time.time()),
        }
        votes.set_vote(interaction.message.id, state)

        log.info(
            "TesterHub: %s dismissed the Trial Tester vote for %s",
            interaction.user, state["candidate_name"],
        )
        await interaction.response.edit_message(view=TrialVoteView(state))

        thread = interaction.message.channel
        if isinstance(thread, discord.Thread):
            await thread.edit(archived=True)


class TrialVoteView(discord.ui.LayoutView):
    """The vote panel"""

    def __init__(self, state: dict = None):
        super().__init__(timeout=None)
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 2.0, lambda i: i.user.id
        )

        items = [discord.ui.TextDisplay(render_vote_text(state))]
        if not (state and state.get("decided")):
            items += [
                separator(),
                discord.ui.ActionRow(
                    VoteButton(in_favour=True),
                    VoteButton(in_favour=False),
                    RetractVoteButton(),
                ),
                discord.ui.ActionRow(
                    PromoteButton(),
                    DismissButton(),
                ),
            ]
        self.add_item(discord.ui.Container(*items, accent_colour=INFO_ACCENT))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction, roles=TESTER_HUB_ROLES)


async def announce_promotion(bot, member: discord.Member, role_key: str, *, chose: bool) -> None:
    channel = bot.get_channel(Channels.TESTER_CHAT)
    if channel is None:
        return
    label = ROLE_LABELS[role_key]
    if chose:
        text = f"🎉 {member.mention} accepted the promotion and chose the {label} role. Welcome aboard!"
    else:
        text = (
            f"🎉 {member.mention} was promoted to {label}. Welcome aboard!\n"
            "-# They could not be reached via DM, so they got the regular role."
        )
    await channel.send(view=NoticeView(text), allowed_mentions=discord.AllowedMentions.none())


class RoleChoiceButton(discord.ui.Button):
    def __init__(self, *, excl: bool):
        super().__init__(
            label=ROLE_LABELS["TRIAL_TESTER_EXCL_TOURNAMENTS" if excl else "TRIAL_TESTER"],
            style=discord.ButtonStyle.secondary if excl else discord.ButtonStyle.primary,  # noqa
            custom_id=f"TrialRoleChoice:{'excl' if excl else 'normal'}",
        )
        self.role_key = "TRIAL_TESTER_EXCL_TOURNAMENTS" if excl else "TRIAL_TESTER"

    async def callback(self, interaction: discord.Interaction) -> None:
        # this runs in a DM: find the vote this message belongs to
        all_votes = votes.load_votes()
        panel_id = state = None
        for key, stored in all_votes.items():
            if stored.get("dm_message_id") == interaction.message.id:
                panel_id, state = key, stored
                break

        if state is None:
            await interaction.response.send_message(
                view=NoticeView("The stored data of this promotion is gone. Please contact a Tester."),
                ephemeral=True,
            )
            return
        if state.get("role_assigned"):
            await interaction.response.send_message(
                view=NoticeView("You already picked your role."), ephemeral=True
            )
            return

        guild = interaction.client.get_guild(Guilds.DDNET)
        member = guild.get_member(state["candidate_id"]) if guild else None
        if member is None:
            await interaction.response.send_message(
                view=NoticeView("You no longer seem to be on the DDNet server."), ephemeral=True
            )
            return

        role = guild.get_role(getattr(Roles, self.role_key))
        try:
            await member.add_roles(role, reason="Trial Tester vote, role chosen via DM")
        except discord.Forbidden:
            await interaction.response.send_message(
                view=NoticeView("I am not allowed to assign the role. Please contact a Tester."),
                ephemeral=True,
            )
            return

        state["role_assigned"] = self.role_key
        all_votes[panel_id] = state
        votes.save_votes(all_votes)

        log.info("TesterHub: %s chose the %s role", member, self.role_key)
        await interaction.response.edit_message(
            view=NoticeView(f"You now have the {ROLE_LABELS[self.role_key]} role. Welcome aboard!")
        )
        await announce_promotion(interaction.client, member, self.role_key, chose=True)


class RoleChoiceView(discord.ui.LayoutView):
    """Sent to the candidate via DM after a successful vote"""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "# You have been promoted to Trial Tester!\n"
                    "The DDNet testing team voted in your favour. "
                    "Pick which role you would like:\n"
                    "- **Trial Tester**: the regular role, including access to tournament test maps.\n"
                    "Keep in mind choosing this map will **disqualify** from taking part in them.\n"
                    "- **Trial Tester (excl. tournaments)**: the same role, just without the tournament map access."
                ),
                separator(),
                discord.ui.ActionRow(
                    RoleChoiceButton(excl=False), RoleChoiceButton(excl=True)
                ),
                accent_colour=INFO_ACCENT,
            )
        )


class TrialVotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_panels.start()

    async def cog_unload(self):
        self.refresh_panels.cancel()

    @tasks.loop(minutes=30)
    async def refresh_panels(self):
        for message_id in list(votes.load_votes()):
            # re-read per panel, votes can come in while this loop awaits,
            # and saving a stale snapshot would silently drop them
            state = votes.get_vote(int(message_id))
            if state is None or state.get("decided"):
                continue
            if time.time() - state.get("started_ts", 0) > votes.OPEN_VOTE_MAX_AGE:
                continue  # stale, nobody is going to conclude this one
            ready = promote_ready(state)[0]
            if ready == state.get("rendered_ready", False):
                continue

            thread = self.bot.get_channel(state.get("thread_id"))
            if thread is None:
                continue
            try:
                message = await thread.fetch_message(int(message_id))
                state["rendered_ready"] = ready
                await message.edit(view=TrialVoteView(state))
            except discord.HTTPException:
                continue  # deleted panel or archived thread

            votes.set_vote(int(message_id), state)
            log.info("TrialVotes: refreshed the vote panel %s (ready=%s)", message_id, ready)

    @refresh_panels.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()


class CandidateSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Pick the candidate", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.candidate = self.values[0]
        await interaction.response.defer()


class NominationModal(discord.ui.Modal, title="Suggest a Trial Tester"):
    reason = discord.ui.Label(
        text="Why should they become Trial Tester?",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=500,
        ),
    )

    def __init__(self, candidate: discord.Member):
        super().__init__(timeout=300)
        self.candidate = candidate

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = interaction.client.get_channel(Channels.TESTER_CHAT)
        if channel is None:
            await interaction.edit_original_response(
                view=NoticeView("The tester chat channel was not found.")
            )
            return

        candidate = self.candidate
        try:
            thread = await channel.create_thread(
                name=f"Trial Tester vote: {candidate.display_name}"[:100],
                type=discord.ChannelType.private_thread,  # noqa
                invitable=True,
                auto_archive_duration=10080,  # 7 days, the maximum
                reason=f"Trial Tester suggestion by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView(f"I am not allowed to create private threads in {channel.mention}.")
            )
            return
        except discord.HTTPException as error:
            await interaction.edit_original_response(
                view=NoticeView(f"Could not create the vote thread: {error}")
            )
            return

        state = {
            "candidate_id": candidate.id,
            "candidate_name": candidate.display_name,
            "nominator_id": interaction.user.id,
            "nominator_name": interaction.user.display_name,
            "reason": self.reason.component.value.strip(),
            "started_ts": int(time.time()),
            "thread_id": thread.id,
            "votes": {},
            "decided": None,
            "rendered_ready": False,
            "dm_message_id": None,
            "role_assigned": None,
        }
        panel = await thread.send(
            view=TrialVoteView(state),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        votes.set_vote(panel.id, state)
        ping = await thread.send(
            f"<@&{Roles.TESTER}> <@&{Roles.TESTER_EXCL_TOURNAMENTS}>",
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        await ping.delete()

        log.info(
            "TesterHub: %s suggested %s as Trial Tester (thread %d)",
            interaction.user, candidate, thread.id,
        )
        await interaction.edit_original_response(
            view=NoticeView(f"Vote thread created: {thread.mention}")
        )


class StartVoteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Start the vote", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        candidate = self.view.candidate

        problem = None
        if candidate is None:
            problem = "Pick a candidate first."
        elif not isinstance(candidate, discord.Member):
            problem = "That user is not on this server."
        elif candidate.bot:
            problem = "Bots make poor testers."
        elif any(role.id in (Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
                             Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS) for role in candidate.roles):
            problem = f"{candidate.mention} already is a Tester or Trial Tester."
        elif thread_id := votes.open_vote_thread(candidate.id):
            problem = f"There already is an open vote for {candidate.mention}: <#{thread_id}>"

        if problem:
            await interaction.response.send_message(view=NoticeView(problem), ephemeral=True)
            return
        await interaction.response.send_modal(NominationModal(candidate))


class PromoteStartView(discord.ui.LayoutView):
    """Candidate picker and a button opening the nomination modal"""

    def __init__(self):
        super().__init__(timeout=300)
        self.candidate = None

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Suggest a Trial Tester\n"
                    "Pick a member, then start the vote. This creates a "
                    f"private thread in <#{Channels.TESTER_CHAT}> where every "
                    "Tester is notified and can vote on the promotion."
                ),
                separator(),
                discord.ui.ActionRow(CandidateSelect()),
                discord.ui.ActionRow(StartVoteButton()),
                accent_colour=INFO_ACCENT,
            )
        )
