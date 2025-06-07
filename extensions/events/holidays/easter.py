import discord
from datetime import datetime
from constants import Emojis


class Easter(discord.Embed):
    def __new__(cls, bot, sub_end: int, vote_end: int):
        try:
            v = bot.get_emoji(Emojis.V)
            b = bot.get_emoji(Emojis.B)
            d = bot.get_emoji(Emojis.D)
            o = bot.get_emoji(Emojis.O)
            t = bot.get_emoji(Emojis.T)
            r = bot.get_emoji(Emojis.R)
            i = bot.get_emoji(Emojis.I)
            c = bot.get_emoji(Emojis.C)
            k = bot.get_emoji(Emojis.K)
            g = bot.get_emoji(Emojis.G)
            e = bot.get_emoji(Emojis.E)
            a = bot.get_emoji(Emojis.A)
            l = bot.get_emoji(Emojis.L)
            n = bot.get_emoji(Emojis.N)

            title = f"👹{t}{r}{i}{c}{k} or {t}{r}{e}{a}{t}🪦"

            embed = discord.Embed(
                title=title,
                description="We’re thrilled to announce our new **Halloween Contest**! It's time to get spooky and unleash your "
                            "creativity to give our Discord server a fresh, hauntingly beautiful "
                            "look with a new **Banner** and **Icon**. 🦇 Here are the details and criteria you need to know.",
                colour=15105570,
            )
            embed.add_field(
                name=f"{c}{r}{i}{t}{e}{r}{i}{a}",
                value=""" 
                1\\. **Design**: Must be Teeworlds related.
                2\\. **Content Restrictions:** No offensive content, and **no AI-generated images**.
                3\\. **Theme:** Keep it eerie, creepy, or fun—whatever says Halloween to you!
                """,
                inline=False
            )
            embed.add_field(
                name=f"{b}{a}{n}{n}{e}{r}",
                value=""" 
                1\\. **Minimum Dimensions:** 960x540 pixels
                """,
                inline=True
            )
            embed.add_field(
                name=f"{i}{c}{o}{n}",
                value=""" 
                1\\. **Minimum Dimensions:** 128x128 pixels
                2\\. **Design:** Must feature a Halloween version of a DDNet mascot.
                """,
                inline=True
            )
            embed.add_field(
                name=f"{d}{e}{a} {d}{l}{i}{n}{e}",
                value=f"""
                You have until **<t:{sub_end}:f>** to submit your banner and icon artwork.

                {v}{o}{t}{i}{n}{g}:
                After the submission period ends, voting will start and remains open until **<t:{vote_end}:f>**.  

                The entries with the most votes will become this year's **official Halloween banner and icon**!



                {n}{o}{t}{e}:
                Please only submit your artwork when it's completely finished and ready for review.
                """,
                inline=False
            )
            embed.set_image(url="attachment://thumbnail.png")
            file = discord.File("data/events/ddnet_halloween_thumbnail_by_insanity.png", filename="thumbnail.png")
            return embed, file
        except ValueError as e:
            now = datetime.now().strftime("%Y/%m/%d %H:%M")
            raise ValueError(
                f"Invalid date/time format. Please use the format `YYYY/MM/DD HH:MM` (Example: {now})."
            ) from e