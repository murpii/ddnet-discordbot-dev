import discord
from typing import List, Set

from utils.text import get_embed_from_interaction, extract_ids_from_mentions, user_ids_to_mentions

# CHECKLIST_TASKS = [
#     "1. Map follows all mapping rules (https://ddnet.org/rules)",
#     "2. Checked for possible startline skips",
#     "3. Checked for ways to escape the map",
#     "4. Weapons and powerups can't be kept longer than they should",
#     "5. Checked for big team 0 cheats using towers, boats, hammer boost etc.",
#     "6. Checked for ways to abuse weapons and spec",
#     "7. Looked for entity bugs",
#     "8. Took care of testing bot warnings",
#     "9. No missing or misspelled server settings",
#     "10. Decoration layers are marked as HD",
#     "11. Large assets are as optimized as possible",
# ]

CHECKLIST_TASKS = [
    "1. Map follows all mapping rules (https://ddnet.org/rules)",
    "2. Checked for ways to escape the map",
    "3. Checked for other skips: weapons, /spec, teleporter, team 0, keeping powerups",
    "4. Teleporters are working and used properly",
    "5. Switches are working and used properly",
    "6. Special tiles are only used where necessary",
    "7. Difficulty is kept consistent",
    "8. No spacing issues (for the respective map type)",
    "9. Equal amount of playtime for all players",
    "10. Server settings are working as intended",
    "11. Unfreeze is used conveniently",
    "12. Reviewed testing bot warnings",
    "13. Checked for entity bugs",
    "14. Decoration layers are marked as HD",
    "15. Used assets are as optimized as possible",
    "16. Checked for design bugs",
]

BUTTONS_PER_ROW = 5   # Not really necessary, but can be changed for looks (5 is max)
EMBED_COLOR = discord.Color.blurple()
MENTION_PREFIX = "→ "


class ChecklistView(discord.ui.View):
    """
    A Discord UI view that displays an interactive checklist with buttons.
    Users can check/uncheck tasks, and the embed updates to show completion status.
    """
    def __init__(self):
        super().__init__(timeout=None)
        self.task_completion_users: List[Set[int]] = [set() for _ in range(len(CHECKLIST_TASKS))]

        for task_index in range(len(CHECKLIST_TASKS)):
            button = TaskCheckButton(task_index=task_index)
            self.add_item(button)


    def generate_checklist_embed(self, requesting_user: discord.User = None) -> discord.Embed:
        """
        Generate an embed displaying the current checklist state.

        Args:
            requesting_user: The user who triggered the update

        Returns:
            A Discord embed with the formatted checklist
        """

        unchecked = "[ ]"
        checked = "[x]"
        checklist_lines = []

        for task_index, completed_user_ids in enumerate(self.task_completion_users):
            completion_count = len(completed_user_ids)

            if completion_count == 0:
                status = unchecked
            elif completion_count == 1:
                status = checked
            else:
                status = f"{checked} (x{completion_count})"
            
            task_description = CHECKLIST_TASKS[task_index]

            task_line = f"{status} {task_description}"

            if completed_user_ids:
                user_mentions = user_ids_to_mentions(completed_user_ids)
                checklist_lines.append(f"{task_line}\n{MENTION_PREFIX}{user_mentions}")
            else:
                checklist_lines.append(task_line)

        embed_description = "\n".join(checklist_lines)
        return discord.Embed(
            title="Checklist",
            description=embed_description,
            color=EMBED_COLOR
        )

    def restore_state_from_embed(self, embed: discord.Embed) -> None:
        """
        Restore the checklist state from an existing embed description.

        Args:
            embed: The Discord embed to parse
        """
        if not embed or not embed.description:
            return

        self.task_completion_users = [set() for _ in range(len(CHECKLIST_TASKS))]
        description_lines = embed.description.split("\n")

        current_line_index = 0
        current_task_index = 0

        while current_line_index < len(description_lines) and current_task_index < len(CHECKLIST_TASKS):
            current_line = description_lines[current_line_index]

            if current_line.startswith("["):
                current_line_index = self.process_task_line(
                    description_lines, current_line_index, current_task_index
                )
                current_task_index += 1
            else:
                current_line_index += 1

    def process_task_line(self, lines: List[str], line_index: int, task_index: int) -> int:
        """
        Process a task line and extract user mentions if present.

        Args:
            lines: All description lines
            line_index: Current line index
            task_index: Current task index

        Returns:
            Next line index to process
        """
        next_line_index = line_index + 1

        if (next_line_index < len(lines) and
                lines[next_line_index].strip().startswith(MENTION_PREFIX)):
            mentions_line = lines[next_line_index]
            extracted_user_ids = extract_ids_from_mentions(mentions_line, MENTION_PREFIX)
            self.task_completion_users[task_index].update(extracted_user_ids)

            return next_line_index + 1

        return next_line_index


class TaskCheckButton(discord.ui.Button):
    """
    A button representing a single task in the checklist.
    When clicked, toggles the completion status for the user.
    """
    def __init__(self, task_index: int):
        button_label = str(task_index + 1)
        button_row = task_index // BUTTONS_PER_ROW
        button_id = f"check_task_{task_index}"

        super().__init__(
            label=button_label,
            style=discord.ButtonStyle.secondary,  # type: ignore
            row=button_row,
            custom_id=button_id,
        )
        self.task_index = task_index

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Handle button click to toggle task completion for the user.

        Args:
            interaction: The Discord interaction from the button click
        """
        checklist_view = self.view

        existing_embed = get_embed_from_interaction(interaction)
        if existing_embed:
            checklist_view.restore_state_from_embed(existing_embed)

        task_users = checklist_view.task_completion_users[self.task_index]
        if interaction.user.id in task_users:
            task_users.remove(interaction.user.id)
        else:
            task_users.add(interaction.user.id)

        updated_embed = checklist_view.generate_checklist_embed(interaction.user)
        await interaction.response.edit_message(embed=updated_embed, view=checklist_view)
