import contextlib
import difflib
import json
import logging
import os
import re
from datetime import datetime

import aiohttp
import discord
import requests
from discord.ext import commands, tasks

from constants import Channels

WIKI_API = "https://wiki.ddnet.org/w/api.php"
STATE_FILE = "data/wiki/wiki_state.json"


class Wiki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def find_sections_with_keywords(content, keywords):
        sections = []
        current_section = ""
        in_relevant_section = False
        lines = content.split("\n")
        for line in lines:
            if match := re.match(r"==+\s*([^=]+?)\s*==+", line):
                if any(keyword.lower() in match[1].lower() for keyword in keywords):
                    if in_relevant_section:
                        sections.append(current_section)
                    current_section = match[1].strip()
                    in_relevant_section = True

            if all(keyword.lower() in line.lower() for keyword in keywords):
                in_relevant_section = True

        if in_relevant_section:
            sections.append(current_section)

        return sections

    @staticmethod
    def format_section_link(title, section):
        title_formatted = title.replace(" ", "_")
        section_formatted = section.replace(" ", "_")
        link = f"https://wiki.ddnet.org/wiki/{title_formatted}#{section_formatted}"
        print(link)
        if section:
            return f"[`{title} - {section}`]({link})"
        else:
            return f"[`{title}`]({link})"

    def fetch_article_content(self, pageid):
        params = {
            "action": "parse",
            "format": "json",
            "pageid": pageid,
            "prop": "wikitext",
        }
        headers = {"User-Agent": "DDNetDiscordBot/1.0 (+https://ddnet.org/)"}

        try:
            response = self.bot.request_cache.get(WIKI_API, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            # print(data.get('parse', {}).get('wikitext', {}).get('*'))
            return data.get("parse", {}).get("wikitext").get("*")
        except requests.RequestException as e:
            logging.error("Error fetching article content:", e)
            return ""

    def wiki_search(self, keyword, max_articles=5, max_sections_per_article=2):
        keywords = keyword.split()
        articles = self.search_articles(keyword)
        if not articles:
            return "No articles found."

        response_lines = []

        for article in articles[:max_articles]:
            content = self.fetch_article_content(article["pageid"])
            sections = self.find_sections_with_keywords(content, keywords)

            for section in sections[:max_sections_per_article]:
                link = self.format_section_link(article["title"], section)
                response_lines.append(link)

        return "\n".join(response_lines) if response_lines else "No matching sections found."

    def search_articles(self, keyword):
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": keyword,
            "srlimit": 5,
        }
        headers = {"User-Agent": "DDNetDiscordBot/1.0 (+https://ddnet.org/)"}

        try:
            response = self.bot.request_cache.get(WIKI_API, params=params, headers=headers)
            response.raise_for_status()

            if response.status_code == 200:
                data = response.json()
                if "error" in data:
                    raise ValueError(f"Wiki API Error: {data['error'].get('info', 'Unknown error')}")

                articles = data.get("query", {}).get("search", [])
                return [article for article in articles if "/" not in article["title"]]

            raise ValueError(f"Unexpected status code from Wiki API: {response.status_code}")

        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch articles: {e}") from e

    @commands.command(
        name="wiki",
        description="Search for wiki articles based on a keyword.",
        usage="<keyword>"
    )
    async def wiki(self, ctx, *keywords):
        """Usage: $wiki <keyword>"""
        search_query = " ".join(keywords)

        if not search_query or len(search_query) < 3:
            await ctx.send("Please enter a keyword that is at least 3 characters long.")
            return

        try:
            resp = self.wiki_search(search_query, max_articles=5, max_sections_per_article=3)
            embed = discord.Embed(description=resp, colour=discord.Colour.blurple())
        except ValueError as e:
            embed = discord.Embed(
                title="Wiki Search Error",
                description=str(e),
                colour=discord.Colour.red()
            )

        with contextlib.suppress(discord.Forbidden):
            if ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await self.bot.reply(message=ctx.message, embed=embed)


class WikiChanges(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_rev_id = self.load_last_rev_id()
        self.check_changes.start()

    def cog_unload(self):
        self.check_changes.cancel()

    def load_last_rev_id(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_rev_id")
        return None

    def save_last_rev_id(self, rev_id):
        with open(STATE_FILE, "w") as f:
            json.dump({"last_rev_id": rev_id}, f)

    async def fetch_json(self, session, params):
        async with session.get(WIKI_API, params=params) as resp:
            return await resp.json()

    async def fetch_revision_text(self, session, rev_id):
        """Fetch the raw wikitext of a specific revision."""
        params = {
            "action": "query",
            "prop": "revisions",
            "revids": rev_id,
            "rvslots": "main",
            "rvprop": "content",
            "format": "json",
        }
        data = await self.fetch_json(session, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            revisions = page.get("revisions", [])
            if revisions:
                return revisions[0].get("slots", {}).get("main", {}).get("*", "")
        return ""

    @tasks.loop(seconds=60)
    async def check_changes(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(Channels.WIKI)
        if not channel:
            return

        async with aiohttp.ClientSession() as session:
            params = {
                "action": "query",
                "list": "recentchanges",
                "rcprop": "title|ids|sizes|flags|user|comment|timestamp",
                "rclimit": 50,
                "format": "json"
            }
            data = await self.fetch_json(session, params)
            changes = data.get("query", {}).get("recentchanges", [])

            new_changes = [
                c for c in reversed(changes)
                if c.get("revid") and (not self.last_rev_id or c["revid"] > self.last_rev_id)
            ]

            for change in new_changes:
                rev_id = change["revid"]
                old_rev = change.get("old_revid")

                ts = change["timestamp"]
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                discord_ts = f"<t:{int(dt.timestamp())}:f>"

                old_size = change.get("oldlen", 0)
                new_size = change.get("newlen", 0)
                added_bytes = max(new_size - old_size, 0)
                removed_bytes = max(old_size - new_size, 0)

                old_text = await self.fetch_revision_text(session, old_rev) if old_rev else ""
                new_text = await self.fetch_revision_text(session, rev_id)

                diff = list(difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    lineterm=""
                ))

                added_lines = sum(bool(line.startswith("+") and not line.startswith("+++"))
                                  for line in diff)
                removed_lines = sum(bool(line.startswith("-") and not line.startswith("---"))
                                    for line in diff)

                diff = "```diff\n"
                if removed_lines > 0:
                    diff += f"- {removed_lines} line(s) removed\n"
                if added_lines > 0:
                    diff += f"+ {added_lines} line(s) added\n"
                diff += "```"
                bytes = "```diff\n"
                if removed_bytes > 0:
                    bytes += f"- {removed_bytes} byte(s)\n"
                if added_bytes > 0:
                    bytes += f"+ {added_bytes} byte(s)\n"
                bytes += f"= {new_size} bytes total\n```"
                diff += bytes
                embed = discord.Embed(
                    title=f"Page edited: {change['title']}",
                    url=f"https://wiki.ddnet.org/?diff={rev_id}&oldid={old_rev}",
                    description=change.get("comment") or "(no edit summary)",
                    color=discord.Color.blue()
                )
                embed.set_author(name=change["user"])
                embed.add_field(name="Revision ID", value=str(rev_id), inline=True)
                embed.add_field(name="Timestamp", value=discord_ts, inline=True)
                embed.add_field(name="Changes", value=diff, inline=False)

                await channel.send(embed=embed)
                self.last_rev_id = rev_id
                self.save_last_rev_id(rev_id)

    @check_changes.before_loop
    async def before_check_changes(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Wiki(bot))
    await bot.add_cog(WikiChanges(bot))
