# DDNet Discord bot

The community Discord bot for [DDNet](https://ddnet.org) (DDraceNetwork). It runs
the server's ticket system, moderation/admin/tester hubs, player and map lookups,
a player watchlist, help guides, and assorted chat/utility features.

Built on discord.py 2.7.x, backed by MariaDB, with new UI built as
Components V2 (`LayoutView` / `Container`) rather than embeds.

## This bot is built for DDNet, not as a general-purpose template

It is hard-wired to the DDNet Discord and DDNet's infrastructure, and is not meant
to be run by anyone else. Standalone setup is, frankly, not worth it.

## "Can I run just one module?"

Partly.

- The bot **will not start without a MariaDB pool**. `setup_hook` closes it if
  the pool is `None`.
- `constants.py` (with real DDNet IDs) is imported almost everywhere, and the
  shared managers (`ticket_manager`, `pfm`, `moddb`) are constructed on every
  startup.
- Most cogs assume the single DDNet guild plus DDNet's APIs/DB.

A few are close to standalone in logic (e.g. `misc.meme`, `misc.status`, the
`guides` system, and the DDNet-HTTP-API-only `/profile` `/map` `/points`
`/activity`), but none run without `constants.py` and the shared scaffolding.
Running one truly on its own means editing `bot.py` and supplying a DB + the IDs
it touches.

## Architecture

Quick map:

- `bot.py`: Entry point, the `extensions` list, DB pool, slash sync.
- `extensions/`: The cogs (ticketsystem, management/{admin,moderator,tester},
  guides, misc, chat, wiki, skindb, map_awards, ...).
- `utils/`: shared helpers (DB-agnostic image generation, text, containers,
  master-server parser, ...).
- `data/`: committed content (guides, channel templates, assets) plus gitignored
  runtime state and caches.
- `schema.sql`: the bot's own tables.

## Notes

- Map testing lives in a separate repo (`ddnet-discord-testing-bot`) that shares
  this database; it is not part of this bot.
