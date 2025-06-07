#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import enum
import logging
import re
from datetime import datetime, timezone
import discord
from discord.ext import commands

from constants import Channels

log = logging.getLogger(__name__)

_ISSUE_RE = r"(?:(?P<owner>\w+)/)?(?P<repo>[\w-]*)#(?P<id>[5-9]\d|\d{3,})\b"
_REF_RE = r"[-\w]+"


def filter_empty(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if v}


class BuildStatus(enum.Enum):
    UNKNOWN = "❔"
    PENDING = "🟡"
    FAILED = "🔴"
    SUCCESS = "🟢"

    def __str__(self) -> str:
        return self.value


class GithubException(commands.CommandError):
    pass


class GithubRatelimit(GithubException):
    def __init__(self, reset: int):
        self.timestamp = datetime.fromtimestamp(reset, timezone.utc)
        super().__init__(f"Currently rate limited until {self.timestamp} UTC")


class GithubBase:
    bot = None
    session = None

    async def _fetch(self, url: str) -> dict:
        headers = {
            "Accept:": "application/vnd.github.v3+json, application/vnd.github.antiope-preview+json"
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


class Commit(GithubBase):
    def __init__(self, owner: str = "ddnet", repo: str = "ddnet", ref: str = "master"):
        self.url = f"repos/{owner}/{repo}/commits/{ref}/check-suites"
        self.master = ref == "master"

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        if match := re.match(_ISSUE_RE, argument):
            issue = await Issue.retrieve(**filter_empty(match.groupdict()))
            return await issue.get_pr_head()

        if match := re.match(_REF_RE, argument):
            return cls(ref=argument)

        raise GithubException("Invalid reference")

    async def get_status(self) -> BuildStatus:
        data = await self._fetch(self.url)
        if data["total_count"] == 0:
            return BuildStatus.UNKNOWN

        pending = False
        for suite in data["check_suites"]:
            if self.master and suite["head_branch"] != "master":
                continue

            if suite["conclusion"] not in ("success", "neutral", None):
                return BuildStatus.FAILED

            if suite["status"] in ("pending", "queued"):
                pending = True

        return BuildStatus.PENDING if pending else BuildStatus.SUCCESS


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

    async def get_pr_head(self) -> Commit:
        if "pull_request" not in self.data:
            raise GithubException("Given issue is not a PR")

        data = await self._fetch(f"repos/{self.owner}/{self.repo}/pulls/{self.id}")
        return Commit(self.owner, self.repo, data["head"]["sha"])


def is_ratelimited(ctx: commands.Context) -> bool:
    if ctx.cog.ratelimited():
        raise ctx.cog.ratelimit
    return True


class Github(commands.Cog):
    def __init__(self, bot):
        self.bot = GithubBase.bot = bot
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
            or message.content
            and message.content[0] == self.bot.command_prefix
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

    @commands.command(usage="[pr|commit]")
    @commands.check(is_ratelimited)
    async def build_status(self, ctx: commands.Context, commit: Commit = Commit()):
        """Show the build status of a PR/commit"""
        status = await commit.get_status()
        await ctx.send(status)

    @build_status.error
    async def build_status_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, GithubException):
            await ctx.send(error)

        if isinstance(error, GithubRatelimit):
            self.ratelimit = error


async def setup(bot: commands.bot):
    await bot.add_cog(Github(bot))
