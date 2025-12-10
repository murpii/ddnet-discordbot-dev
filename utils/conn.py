import discord
import logging
from io import BytesIO

log = logging.getLogger("mt")


def source(url, session):
    resp = session.get(url)
    return resp.json()


async def upload_submission(session, subm):
    from extensions.map_testing.submission import SubmissionState
    try:
        await ddnet_upload(session, "map", await subm.buffer(), str(subm))
    except RuntimeError:
        return await subm.set_state(SubmissionState.ERROR)
    await subm.set_state(SubmissionState.UPLOADED)
    try:
        await subm.message.pin()
    except discord.HTTPException:
        pins = await subm.message.channel.pins()
        await pins[-2].unpin()
        await subm.message.pin()


async def ddnet_upload(session, asset_type: str, buf: BytesIO, filename: str):
    from main import config
    url = config.get("DDNET", "UPLOAD")
    headers = {"X-DDNet-Token": config.get("DDNET", "TOKEN")}

    if asset_type == "map":
        name = "map_name"
    elif asset_type == "log":
        name = "channel_name"
    elif asset_type in {"attachment", "avatar", "emoji"}:
        name = "asset_name"
    else:
        raise ValueError("Invalid asset type")

    data = {"asset_type": asset_type, "file": buf, name: filename}
    log.info(data)
    async with session.post(url, data=data, headers=headers) as resp:
        if resp.status != 200:
            fmt = "Failed uploading %s %r to ddnet.org: %s (status code: %d %s)"
            log.error(
                fmt,
                asset_type,
                filename,
                await resp.text(),
                resp.status,
                resp.reason,
            )
            raise RuntimeError("Could not upload file to ddnet.org")

        log.info("Successfully uploaded %s %r to ddnet.org", asset_type, filename)


async def ddnet_delete(session, filename: str):
    from main import config
    url = config.get("DDNET", "DELETE")
    headers = {"X-DDNet-Token": config.get("DDNET", "TOKEN")}
    data = {"map_name": filename}

    async with session.post(url, data=data, headers=headers) as resp:
        if resp.status != 200:
            fmt = "Failed deleting map %r on ddnet.org: %s (status code: %d %s)"
            log.error(fmt, filename, await resp.text(), resp.status, resp.reason)
            raise RuntimeError("Could not delete map on ddnet.org")

        log.info("Successfully deleted map %r on ddnet.org", filename)
