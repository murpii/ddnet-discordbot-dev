from extensions.moderator.automod import AutoMod
from extensions.moderator.no_chat import NoChat
from extensions.moderator.commands.app_commands import ModAppCommands
from extensions.moderator.commands.context_menu import ModeratorCtxMenu
from extensions.moderator.views.info import ModeratorInfoButtons
from extensions.moderator.listeners import ModListeners


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
    await bot.add_cog(ModAppCommands(bot))
    await bot.add_cog(ModeratorCtxMenu(bot))
    await bot.add_cog(ModListeners(bot))
    await bot.add_cog(NoChat(bot))
    bot.add_view(view=ModeratorInfoButtons(bot))
