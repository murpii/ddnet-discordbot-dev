"""
Server management: everything staff uses to run the DDNet guild.

This package bundles the staff modules and the hub
infrastructure they share:

  - hub.py        staff button helpers (HubButton, staff_guard); generic HubCog is utils/hub.py
  - admin/        admin hub, /purge, extension picker, player rename
  - moderator/    moderation hub, automod, blacklist, mod commands/views
  - tester/       tester hub, testing bans, Trial Tester votes

The submodules stay separately loadable extensions.

bot.py loads:
extensions.management.admin, extensions.management.admin.rename,
extensions.management.moderator and extensions.management.tester
individually.
"""
