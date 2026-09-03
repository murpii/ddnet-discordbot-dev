import discord

from constants import URLs
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator

REQUIREMENTS = [
    "1. The community, its servers and playerbase should be established.",
    "2. Servers must adhere to the masterserver rules at all times.",
    "3. Servers and staff must maintain a friendly and SFW atmosphere.",
    "4. Servers must be actively administered.",
    "5. There should be a clear way to contact administration and a reporting system in place.",
]


def read_checked_state(message: discord.Message) -> list[bool]:
    checked = [False] * len(REQUIREMENTS)

    def walk(items) -> None:
        for item in items:
            custom_id = getattr(item, "custom_id", None)
            if isinstance(custom_id, str) and custom_id.startswith("community_app:req:"):
                index = int(custom_id.rsplit(":", 1)[1])
                if 0 <= index < len(REQUIREMENTS):
                    checked[index] = getattr(item, "label", None) == "[✓]"
            if accessory := getattr(item, "accessory", None):
                walk([accessory])
            if children := getattr(item, "children", None):
                walk(children)

    walk(message.components)
    return checked


class RequirementToggle(discord.ui.Button):
    """Flip one requirement checkbox between [✓] and [ ]."""

    def __init__(self, index: int, checked: bool):
        super().__init__(
            label="[✓]" if checked else "[ ]",
            style=discord.ButtonStyle.success if checked else discord.ButtonStyle.secondary,  # noqa
            custom_id=f"community_app:req:{index}",
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        checked = read_checked_state(interaction.message)
        # guard against a parse mismatch so an unexpected message never raises IndexError
        checked = (checked + [False] * len(REQUIREMENTS))[:len(REQUIREMENTS)]
        checked[self.index] = not checked[self.index]

        ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)
        await interaction.response.edit_message(view=CommunityAppContainer(ticket, checked=checked))


class CommunityAppContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket | None = None, checked: list[bool] | None = None):
        super().__init__(timeout=None)

        if checked is None:
            checked = [False] * len(REQUIREMENTS)

        header = (
            f"Hello {ticket.creator.mention}, thanks for reaching out!"
            if ticket is not None else "Thanks for reaching out!"
        )

        rules_btn = discord.ui.Button(
            label="Master Server Rules",
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_MASTER_RULES,
        )
        community_btn = discord.ui.Button(
            label="Community Rules",
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_COMMUNITY_RULES,
        )

        items = [
            discord.ui.TextDisplay(
                "# [Community Application](https://-/)\n"
                f"{header}"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Use this ticket to apply for your server community to featured in "
                "DDNet's in-game server browser. Please read the requirements below before you start."
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Requirements\n"
                "Ensure all servers and networks comply with the masterserver rules and community rules. "
                "These are only high-level rule summaries, for full details, "
                "refer to the community server rules and masterserver rules on our website!"
            ),
            discord.ui.ActionRow(rules_btn, community_btn),
            large_seperator(),
            discord.ui.TextDisplay(
                "### Go through the list below like a checklist and confirm each requirement is met!"
            )
        ]

        for index, requirement in enumerate(REQUIREMENTS):
            items.append(
                discord.ui.Section(
                    requirement,
                    accessory=RequirementToggle(index, checked[index]),
                )
            )

        items.extend([
            large_seperator(),
            discord.ui.TextDisplay(
                "## What to include in your application\n"
                "- Your community's name and a short description\n"
                "- How many servers you run and how long they've been online\n"
                "- A way for us to reach you (contact info / who to talk to)\n"
                "- ...\n\n"
                "-# Applications that do not meet the requirements above will be rejected."
            )
        ])

        self.add_item(discord.ui.Container(*items, accent_colour=TICKET_ACCENT))
