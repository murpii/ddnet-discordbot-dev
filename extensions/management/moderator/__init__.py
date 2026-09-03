from typing import TYPE_CHECKING

from extensions.management.moderator.automod import AutoMod
from extensions.management.moderator.blacklist import Blacklist
from extensions.management.moderator.commands.app_commands import ModAppCommands
from extensions.management.moderator.commands.context_menu import ModeratorCtxMenu
from extensions.management.moderator.hub import DiscordModHub, ModHub
from extensions.management.moderator.listeners import ModListeners
from extensions.management.moderator.manager import ModeratorDB
from extensions.management.moderator.no_chat import NoChat
from extensions.management.moderator.views.buttons.user_info import UserInfoButton
from extensions.management.moderator.views.containers.hub import (
    DiscordModHubView,
    ModHubView,
)
from extensions.management.moderator.views.containers.mod_log import ModLogView
from extensions.management.moderator.views.info import ModeratorInfoButtons
from extensions.management.moderator.views.spam_actions import (
    SpamDealtButton,
    SpamModButton,
)

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    if bot.moddb is None:
        bot.moddb = ModeratorDB(bot)
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
    bot.add_dynamic_items(SpamModButton, SpamDealtButton, UserInfoButton)
