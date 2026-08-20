import time
from typing import Iterable, List, Optional

import discord

MARK_TTL_SECONDS = 60
BULK_LIMIT = 100

marked_ids: dict[int, float] = {}


def mark_bot_deleted(message_ids: Iterable[int]) -> None:
    expiry = time.monotonic() + MARK_TTL_SECONDS
    for message_id in message_ids:
        marked_ids[message_id] = expiry
    drop_expired_marks()


def bot_deleted(message_id: int) -> bool:
    expiry = marked_ids.pop(message_id, None)
    return expiry is not None and expiry > time.monotonic()


def drop_expired_marks() -> None:
    now = time.monotonic()
    for message_id in [mid for mid, expiry in marked_ids.items() if expiry <= now]:
        del marked_ids[message_id]


def messages_by_channel(messages: List[discord.Message]) -> dict:
    grouped = {}
    for message in messages:
        grouped.setdefault(message.channel, []).append(message)
    return grouped


async def delete_one_by_one(messages: List[discord.Message]) -> int:
    deleted = 0
    for message in messages:
        try:
            await message.delete()
        except discord.HTTPException:
            continue  # already gone, or we cannot moderate here
        deleted += 1
    return deleted


async def delete_messages(
        messages: List[discord.Message],
        *,
        reason: Optional[str] = None,
) -> int:
    if not messages:
        return 0

    mark_bot_deleted(message.id for message in messages)

    deleted = 0
    for channel, group in messages_by_channel(messages).items():
        for start in range(0, len(group), BULK_LIMIT):
            batch = group[start:start + BULK_LIMIT]
            try:
                await channel.delete_messages(batch, reason=reason)
            except (discord.HTTPException, discord.ClientException):
                deleted += await delete_one_by_one(batch)
            else:
                deleted += len(batch)
    return deleted
