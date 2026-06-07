import asyncio
import discord
from discord.ext import commands
from discord import app_commands


class HelpFormatter:
    PREFIX = "$"

    @classmethod
    def format_command(cls, command: commands.Command) -> str:
        params = " ".join(f"<{p}>" for p in command.clean_params)
        base = f"{cls.PREFIX}{command.qualified_name} {params}".strip()

        if command.aliases:
            aliases = ", ".join(f"{cls.PREFIX}{a}" for a in command.aliases)
            return f"`{base}` (aliases: {aliases})"

        return f"`{base}`"

    @classmethod
    async def collect_commands(cls, bot: commands.Bot, interaction: discord.Interaction):
        result = {}

        for cog_name, cog in bot.cogs.items():
            if visible_commands := [
                cmd for cmd in cog.get_commands() if not cmd.hidden and cmd.enabled
            ]:
                visible_commands.sort(key=lambda c: c.name)
                result[cog] = visible_commands  # store cog object

        return result

    @classmethod
    async def build_embed(cls, bot: commands.Bot, interaction: discord.Interaction) -> discord.Embed:
        embed = discord.Embed(
            title="Commands",
            description="Available prefix commands",
            colour=discord.Colour.blurple(),
        )

        grouped = await cls.collect_commands(bot, interaction)

        for cog, commands_list in grouped.items():
            cog_name = getattr(cog, "qualified_name", "No Category")
            formatted = [cls.format_command(cmd) for cmd in commands_list]
            value = "\n".join(formatted)

            if (
                    cog_description := getattr(cog, "description", None)
                                       or cog.__doc__
                                       or ""
            ):
                value = f"> {cog_description}\n\n{value}"

            embed.add_field(
                name=cog_name,
                value=value,
                inline=False,
            )

        return embed


class HelpAppCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show available commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = await HelpFormatter.build_embed(self.bot, interaction)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="help")
    async def help_redirect(self, ctx: commands.Context):
        resp = await ctx.message.reply(
            "Use `/help` to view available commands.",
            mention_author=False,

        )
        await asyncio.sleep(30)
        await ctx.channel.delete_messages([resp, ctx.message])


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpAppCommand(bot))
