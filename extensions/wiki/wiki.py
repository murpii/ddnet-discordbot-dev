import contextlib
import difflib
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from constants import Channels, URLs
from utils.containers import NoticeView
from utils.misc import resolve_active_thread
from utils.text import clip, to_discord_timestamp

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

STATE_FILE = "data/wiki/wiki_state.json"


async def fetch_json(session: aiohttp.ClientSession, **params) -> dict:
    """One GET against the wiki API. "formatversion=2" makes MediaWiki return modern, flat JSON"""
    params.update(format="json", formatversion="2")
    query = {key: str(value) for key, value in params.items()}

    async with session.get(URLs.WIKI_API, params=query) as resp:
        resp.raise_for_status()
        data = await resp.json()

    if "error" in data:
        raise ValueError(f"Wiki API error: {data['error'].get('info', 'unknown error')}")
    return data


def page_url(title: str, section: str = "") -> str:
    """Link to a wiki page, optionally to a specific section."""
    url = URLs.WIKI_PAGE_URL + quote(title.replace(" ", "_"))
    if section:
        url += "#" + quote(section.replace(" ", "_"))
    return url


def format_section_link(title: str, section: str) -> str:
    """[`Title - Section`](link), a plain title link if section is empty"""
    label = f"{title} - {section}" if section else title
    return f"[`{label}`]({page_url(title, section)})"


def count_changed_lines(old_text: str, new_text: str) -> tuple:
    """\"added\" and \"removed\" line counts between two revisions"""
    added = removed = 0
    for line in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


class Wiki(commands.Cog):
    """Searches the DDNet wiki and links the articles and sections where the keywords appear."""

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def search(self, query: str, max_results: int = 5) -> str:
        data = await fetch_json(
            self.session,
            action="query", list="search",
            srsearch=query, srlimit="10",
            srprop="sectiontitle",
        )
        hits = data.get("query", {}).get("search", [])

        lines = []
        for hit in hits:
            title = hit["title"]
            if "/" in title:  # skip translated subpages
                continue
            lines.append(format_section_link(title, hit.get("sectiontitle", "")))
            if len(lines) >= max_results:
                break

        return "\n".join(lines) if lines else "No articles found."

    @app_commands.command(
        name="wiki",
        description="Search for wiki articles based on a keyword."
    )
    @app_commands.describe(keyword="What to search the wiki for")
    async def wiki(self, interaction: discord.Interaction, keyword: str):
        if len(keyword) < 3:
            await interaction.response.send_message(
                view=NoticeView("Please enter a keyword that is at least 3 characters long."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            text = await self.search(keyword)
        except (aiohttp.ClientError, ValueError) as error:
            log.warning("Wiki search for %r failed: %s", keyword, error)
            text = f"Wiki search failed: {error}"

        with contextlib.suppress(discord.Forbidden):
            await interaction.followup.send(view=NoticeView(text))


class WikiChanges(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None
        self.last_rev_id = self.load_last_rev_id()
        self.check_changes.start()

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        self.check_changes.cancel()
        await self.bot.session_manager.close_session(self.__class__.__name__)

    @staticmethod
    def load_last_rev_id():
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f).get("last_rev_id")
        return None

    @staticmethod
    def save_last_rev_id(rev_id: int):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"last_rev_id": rev_id}, f)

    async def fetch_revision_texts(self, old_rev: int, new_rev: int) -> tuple:
        """The wikitext of both revisions. "old_rev" is 0 for page creations, the old text is then empty"""
        revids = f"{old_rev}|{new_rev}" if old_rev else str(new_rev)
        data = await fetch_json(
            self.session,
            action="query", prop="revisions", revids=revids,
            rvslots="main", rvprop="ids|content",
        )

        texts = {}
        for page in data.get("query", {}).get("pages", []):
            for revision in page.get("revisions", []):
                texts[revision["revid"]] = revision.get("slots", {}).get("main", {}).get("content", "")

        return texts.get(old_rev, ""), texts.get(new_rev, "")

    @tasks.loop(seconds=60)
    async def check_changes(self):
        thread = await resolve_active_thread(self.bot, Channels.WIKI_THREAD)
        if thread is None:
            return

        try:
            data = await fetch_json(
                self.session,
                action="query", list="recentchanges", rctype="edit|new",
                rcprop="title|ids|sizes|user|comment|timestamp", rclimit="50",
            )
        except (aiohttp.ClientError, ValueError) as error:
            log.warning("Wiki recentchanges fetch failed: %s", error)
            return  # transient -- try again next minute

        changes = data.get("query", {}).get("recentchanges", [])

        if self.last_rev_id is None:
            # first run: remember the newest revision instead of
            # spamming the thread with the 50 most recent edits
            if newest := max((c["revid"] for c in changes if c.get("revid")), default=None):
                self.last_rev_id = newest
                self.save_last_rev_id(newest)
            return

        new_changes = [
            change for change in reversed(changes)
            if change.get("revid") and change["revid"] > self.last_rev_id
        ]

        for change in new_changes:
            await self.post_change(thread, change)
            self.last_rev_id = change["revid"]
            self.save_last_rev_id(change["revid"])

    async def post_change(self, thread, change: dict):
        rev_id = change["revid"]
        old_rev = change.get("old_revid") or 0

        old_text, new_text = await self.fetch_revision_texts(old_rev, rev_id)
        added_lines, removed_lines = count_changed_lines(old_text, new_text)

        new_size = change.get("newlen", 0)
        byte_delta = new_size - change.get("oldlen", 0)

        stats = ["```diff"]
        if removed_lines:
            stats.append(f"- {removed_lines} line(s) removed")
        if added_lines:
            stats.append(f"+ {added_lines} line(s) added")
        if byte_delta:
            stats.append(f"{'+' if byte_delta > 0 else '-'} {abs(byte_delta)} byte(s)")
        stats.append(f"= {new_size} bytes total")
        stats.append("```")

        timestamp = datetime.strptime(change["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        if old_rev:
            action = "Page edited"
            url = f"https://wiki.ddnet.org/?diff={rev_id}&oldid={old_rev}"
        else:
            action = "Page created"
            url = page_url(change["title"])

        summary = discord.utils.escape_mentions(change.get("comment") or "(no edit summary)")
        text = (
                f"## {action}: [{change['title']}]({url})\n"
                f"{clip(summary, 200)}\n"
                f"-# By {change['user']} && {to_discord_timestamp(timestamp)}\n"
                + "\n".join(stats)
        )

        await thread.send(view=NoticeView(text), allowed_mentions=discord.AllowedMentions.none())

    @check_changes.before_loop
    async def before_check_changes(self):
        await self.bot.wait_until_ready()


async def setup(bot: "DDNet"):
    await bot.add_cog(Wiki(bot))
    await bot.add_cog(WikiChanges(bot))
