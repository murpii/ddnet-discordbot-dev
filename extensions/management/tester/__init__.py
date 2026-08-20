"""
Tester hub: staff tools for the map-testing crew.

Map testing itself lives in the separate testing bot.
This extension covers the community-server side:

  - bans.py     testing-category ban system (cog TesterBans)
  - hub.py      keeps the hub message alive in Channels.TESTER_HUB
  - listeners.py  passive testing-category listeners (cog TesterListeners)
  - votes.py    JSON store for the promotion votes
  - views/      hub container, ban/unban flows, channel tools and the
                Trial Tester vote panel
"""

from extensions.management.tester.bans import TesterBans
from extensions.management.tester.hub import TesterHub
from extensions.management.tester.listeners import TesterListeners
from extensions.management.tester.views.hub_view import TesterHubView
from extensions.management.tester.views.promote import PromotionVotes, PromotionVoteView, RoleChoiceView


async def setup(bot):
    await bot.add_cog(TesterBans(bot))
    await bot.add_cog(TesterHub(bot))
    await bot.add_cog(PromotionVotes(bot))
    await bot.add_cog(TesterListeners(bot))
    bot.add_view(TesterHubView(bot))
    bot.add_view(PromotionVoteView())
    bot.add_view(RoleChoiceView())
