import io
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import discord
from discord.ext import commands


class StatsCog(commands.Cog):
    """DDNet trend-based statistics without exposing players."""

    def __init__(self, bot):
        self.bot = bot

    async def plot_and_send(self, ctx, df, x_col, y_cols, title, ylabel, filename, legend=True, integer_y=False):
        """Helper to plot DataFrame and send as Discord image."""
        plt.figure(figsize=(12, 6))
        if isinstance(y_cols, list):
            for col in y_cols:
                plt.plot(df[x_col], df[col], marker='o', label=col)
            if legend:
                plt.legend(title="Category")
        else:
            plt.plot(df[x_col], df[y_cols], marker='o')

        plt.title(title)
        plt.xlabel(x_col)
        plt.ylabel(ylabel)
        plt.xticks(rotation=45)
        plt.tight_layout()

        if integer_y:
            plt.gca().yaxis.set_major_locator(mtick.MaxNLocator(integer=True))

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        await ctx.send(file=discord.File(fp=buf, filename=filename))

    @commands.command(name="monthly_trend")
    async def monthly_trend(self, ctx):
        """Monthly total finishes for the year 2025 (correct counts)."""
        query = """
                SELECT DATE_FORMAT(Timestamp, '%%Y-%%m') AS Month,
                       COUNT(*)                          AS TotalFinishes
                FROM record_race
                WHERE Timestamp >= '2025-01-01'
                  AND Timestamp < '2026-01-01'
                GROUP BY Month
                ORDER BY Month; \
                """
        results = await self.bot.fetch(query, fetchall=True)
        if not results:
            return await ctx.send("No data found for 2025.")

        df = pd.DataFrame(results, columns=["Month", "TotalFinishes"])
        df["Month"] = pd.to_datetime(df["Month"])
        df["TotalFinishes"] = df["TotalFinishes"].astype(int)

        await self.plot_and_send(
            ctx, df,
            x_col="Month",
            y_cols="TotalFinishes",
            title="📊 Monthly Finishes Trend (2025)",
            ylabel="Total Finishes",
            filename="monthly_trend.png",
            integer_y=True
        )

    @commands.command(name="category_trend")
    async def category_trend(self, ctx):
        """Monthly finishes per category (Server), correct counts without overcounting."""
        query = """
                SELECT rm.Server,
                       DATE_FORMAT(rr.Timestamp, '%%Y-%%m')     AS Month,
                       COUNT(DISTINCT rr.Map, rr.Name, rr.Time) AS Finishes
                FROM record_race rr
                         JOIN record_maps rm ON rr.Map = rm.Map
                WHERE rr.Timestamp >= '2025-01-01'
                  AND rr.Timestamp < '2026-01-01'
                GROUP BY rm.Server, Month
                ORDER BY rm.Server, Month; \
                """
        results = await self.bot.fetch(query, fetchall=True)
        if not results:
            return await ctx.send("No data found for 2025.")

        df = pd.DataFrame(results, columns=["Server", "Month", "Finishes"])
        df["Month"] = pd.to_datetime(df["Month"])
        df["Finishes"] = df["Finishes"].astype(int)

        pivot = df.pivot(index="Month", columns="Server", values="Finishes").fillna(0)

        await self.plot_and_send(
            ctx, pivot.reset_index(),
            x_col="Month",
            y_cols=list(pivot.columns),
            title="📊 Category Finishes per Month (2025)",
            ylabel="Finishes",
            filename="category_trend.png",
            integer_y=True
        )
