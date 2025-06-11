import json
import logging
from constants import Channels

log = logging.getLogger("mt")


def add_score(user_id: int, button_name: str):
    """
    Track a button press by a specific user.

    Args:
        user_id (int): The Discord user ID
        button_name (str): One of "READY", "DECLINED", "RESET", "WAITING"
    """

    score_file = "data/map-testing/scores.json"

    button_name = button_name.upper()
    if button_name not in {"READY", "DECLINED", "RESET", "WAITING"}:
        raise ValueError(f"Invalid button name: {button_name}")

    try:
        with open(score_file, "r", encoding="utf-8") as f:
            scores = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        scores = {}

    user_id_str = str(user_id)
    if user_id_str not in scores:
        scores[user_id_str] = {btn: 0 for btn in ["READY", "DECLINED", "RESET", "WAITING"]}
    scores[user_id_str][button_name] += 1

    with open(score_file, "w") as f:
        json.dump(scores, f, indent=4)


async def update_scores_topic(bot):
    """
    Updates the topic of the TESTER channel with the top scores.
    """
    score_file = "data/map-testing/scores.json"

    try:
        with open(score_file, "r", encoding="utf-8") as file:
            scores = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"Couldn't read score file: {e}")
        scores = {}

    def format_buttons(actions: dict[str, int]) -> str:
        parts = []
        if actions.get("READY", 0): parts.append(f"R:{actions['READY']}")
        if actions.get("DECLINED", 0): parts.append(f"D:{actions['DECLINED']}")
        if actions.get("WAITING", 0): parts.append(f"W:{actions['WAITING']}")
        if actions.get("RESET", 0): parts.append(f"X:{actions['RESET']}")
        return " ".join(parts)

    scored_list = []
    for user_id, actions in scores.items():
        try:
            breakdown = format_buttons(actions)
            if breakdown:
                scored_list.append((user_id, breakdown))
        except Exception as e:
            logging.warning(f"Skipping user {user_id} due to invalid data: {e}")

    if not scored_list:
        logging.info("No scores to display.")
        return

    scored_list.sort(key=lambda x: x[0])

    topic = "Tester Activity:"
    for user_id, breakdown in scored_list[:30]:
        topic += f" <@{user_id}>: {breakdown} //"

    topic = topic.rstrip("//")

    if channel := bot.get_channel(Channels.TESTER_CHAT):
        try:
            await channel.edit(topic=topic)
        except Exception as e:
            logging.error(f"Failed to update topic: {e}")
    else:
        logging.warning("Tester channel not found.")