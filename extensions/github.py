#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from constants import Channels

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)

_ISSUE_RE = r"(?:(?P<owner>\w+)/)?(?P<repo>[\w-]*)#(?P<id>[5-9]\d|\d{3,})\b"


def filter_empty(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if v}


class GithubException(commands.CommandError):
    pass


class GithubRatelimit(GithubException):
    def __init__(self, reset: int):
        self.timestamp = datetime.fromtimestamp(reset, timezone.utc)
        super().__init__(f"Currently rate limited until {self.timestamp} UTC")


class GithubBase:
    session = None

    async def _fetch(self, url: str) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json, application/vnd.github.antiope-preview+json"
        }
        async with self.session.get(
            f"https://api.github.com/{url}", headers=headers
        ) as resp:
            js = await resp.json()
            if resp.status == 200:
                return js
            elif resp.status == 403:
                reset = int(resp.headers["X-Ratelimit-Reset"])
                log.warning(
                    "We are being rate limited until %s", datetime.fromtimestamp(reset)
                )
                raise GithubRatelimit(reset)
            elif resp.status == 404:
                raise GithubException("Couldn't find that")
            else:
                log.error(
                    "Failed fetching %r from Github: %s (status code: %d %s)",
                    url,
                    js["message"],
                    resp.status,
                    resp.reason,
                )
                raise GithubException("Failed fetching Github")


class Issue(GithubBase):
    def __init__(self, owner: str, repo: str, id: str):
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.id = id

    @classmethod
    async def retrieve(cls, *, owner: str = "ddnet", repo: str = "ddnet", id: str):
        self = cls(owner, repo, id)
        self.data = await self._fetch(f"repos/{owner}/{repo}/issues/{id}")
        return self

    @property
    def link(self) -> str:
        return self.data["html_url"]


class Github(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None
        self.ratelimit = GithubRatelimit(0)

    def ratelimited(self) -> bool:
        return self.ratelimit.timestamp >= datetime.now(timezone.utc)

    async def cog_load(self):
        self.session = GithubBase.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.channel.id != Channels.DEVELOPER
            or message.author.bot
            or self.ratelimited()
        ):
            return

        pattern = r"```(?:\w+\n)?([\s\S]+?)```|`(?:\w+)?(.+?)`"
        content = re.sub(pattern, "", message.content, flags=re.DOTALL)

        matches = re.finditer(_ISSUE_RE, content)
        links = []
        for match in matches:
            try:
                issue = await Issue.retrieve(**filter_empty(match.groupdict()))
            except GithubRatelimit as exc:
                self.ratelimit = exc
                break
            except GithubException:
                continue
            else:
                links.append(issue.link)

        if links:
            await message.channel.send("\n".join(links))


async def setup(bot: "DDNet"):
    await bot.add_cog(Github(bot))
