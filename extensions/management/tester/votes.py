import json
import os
import time

VOTES_DIR = "data/tester-hub"
VOTES_FILE = os.path.join(VOTES_DIR, "votes.json")
OPEN_VOTE_MAX_AGE = 14 * 24 * 60 * 60


def load_votes() -> dict:
    try:
        with open(VOTES_FILE, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_votes(votes: dict) -> None:
    os.makedirs(VOTES_DIR, exist_ok=True)
    with open(VOTES_FILE, "w", encoding="utf-8") as file:
        json.dump(votes, file, indent=4)


def get_vote(message_id: int) -> dict | None:
    return load_votes().get(str(message_id))


def set_vote(message_id: int, state: dict) -> None:
    votes = load_votes()
    votes[str(message_id)] = state
    save_votes(votes)


def open_vote_thread(candidate_id: int) -> int | None:
    return next(
        (
            state.get("thread_id")
            for state in load_votes().values()
            if (
                state.get("candidate_id") == candidate_id
                and not state.get("decided")
                and time.time() - state.get("started_ts", 0)
                < OPEN_VOTE_MAX_AGE
        )
        ),
        None,
    )
