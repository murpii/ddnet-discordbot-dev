from extensions.management.moderator.automod import AutoMod
from extensions.management.moderator.blacklist import Blacklist
from extensions.management.moderator.hub import ModHub, DiscordModHub
from extensions.management.moderator.no_chat import NoChat
from extensions.management.moderator.commands.app_commands import ModAppCommands
from extensions.management.moderator.commands.context_menu import ModeratorCtxMenu
from extensions.management.moderator.views.containers.hub import ModHubView, DiscordModHubView
from extensions.management.moderator.views.containers.mod_log import ModLogView
from extensions.management.moderator.views.info import ModeratorInfoButtons
from extensions.management.moderator.listeners import ModListeners


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
    await bot.add_cog(Blacklist(bot))
    await bot.add_cog(ModAppCommands(bot))
    await bot.add_cog(ModeratorCtxMenu(bot))
    await bot.add_cog(ModHub(bot))
    await bot.add_cog(DiscordModHub(bot))
    await bot.add_cog(ModListeners(bot))
    await bot.add_cog(NoChat(bot))
    bot.add_view(view=ModHubView(bot))
    bot.add_view(view=DiscordModHubView(bot))
    bot.add_view(view=ModLogView(bot))
    bot.add_view(view=ModeratorInfoButtons(bot))
