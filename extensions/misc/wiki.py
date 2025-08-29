import contextlib
import logging
import re
import requests

import discord
from discord.ext import commands


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
        if section:
            return f"[`{title} - {section}`]({link})"
        else:
            return f"[`{title}`]({link})"

    def fetch_article_content(self, pageid):
        api = "https://wiki.ddnet.org/api.php"

        params = {
            "action": "parse",
            "format": "json",
            "pageid": pageid,
            "prop": "wikitext",
        }

        try:
            response = self.bot.request_cache.get(api, params=params)
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
        api = "https://wiki.ddnet.org/api.php"
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": keyword,
            "srlimit": 5,
        }

        try:
            response = self.bot.request_cache.get(api, params=params)
            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                # print(data)

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
        usage="<keyword>")
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


async def setup(bot):
    await bot.add_cog(Wiki(bot))
