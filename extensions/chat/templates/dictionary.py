from constants import Channels, Roles, Emojis

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# HOW-TO:                                                                         #
# 1. Edit the text that needs changing.                                           #
# 2. Reload the cog with /reload static_msgs.                                     #
# 3. Use /update <message-id> <variable> to update a specific message.            #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


#################################
#            WELCOME            #
#################################


welcome_main = """
Welcome to the official DDraceNetwork Discord Server!

This server serves as the central hub for our community. Here, you can chat with friends & engage in discussions about the game's development.

Feel free to ask any questions you may have, whether it's about learning the mechanics of the game or troubleshooting any issues you encounter. Our community members and knowledgeable staff are here to assist you every step of the way.

**For more information about the game, you can visit the game’s Steam Store page:**
<https://store.steampowered.com/app/412220/DDraceNetwork/>
"""

welcome_rules = f"""
`#1` **Be nice** – Don't insult others or engage in lazy negativity towards other people's projects, even as a joke.
`#2` **No NSFW** - No pornography, gore, or anything that could be considered Not Safe For Work.
`#3` **Don't spam** - Includes all types of spamming (messages, emojis, reactions, etc.).
`#4` **Use channels only for their named purpose** - Off-topic goes to <#{Channels.OFF_TOPIC}>, Teeworlds related images and videos go to <#{Channels.SHOWROOM}>.
`#5` **Use English whenever possible** - If you want to talk in another language, do so in #off-topic.
`#6` **Keep drama out of here** - Sort out personal conflicts in DMs.
`#7` **Don't promote or encourage illegal activities** - Includes botting/cheating.
"""

welcome_channel_listing = f"""
**「INFO CATEGORY」**
<#{Channels.WELCOME}> - Welcome! Here you'll find basic information about our server and it's rules!
<#{Channels.ANNOUNCEMENTS}> - Any announcements about the game are posted here, including game update notes.
<#{Channels.MAP_RELEASES}> - Upcoming map releases are announced in this channel!
<#{Channels.RECORDS}> - Every new record done on our official servers are posted in this channel.

**「Development」**
<#{Channels.DEVELOPER}> - Get a glimpse into the exciting realm of game development!
<#{Channels.BUGS}> - Here you can report bugs highlighting unintentional errors in the game.

**「DDraceNetwork」**
<#{Channels.GENERAL}> - This channel is for all Teeworlds, DDNet and related chat!
<#{Channels.SHOWROOM}> - Post videos, screenshots, and other content from the game here!
<#{Channels.QUESTIONS}> - Got Questions? Need Help? Ask Away!
<#{Channels.WIKI}> - A channel for collaborative knowledge building and discussions.
<#{Channels.MAPPING}> - Mapping discussions, questions, and map rating requests.
<#{Channels.OFF_TOPIC}> - Discuss anything unrelated to DDNet. Any languages allowed.
<#{Channels.BOT_CMDS}> - Game and server stats commands. Type /help for more info.

**「Tickets」**
<#{Channels.TICKETS_INFO}>- This channel is dedicated to addressing various issues and requests.

Here's a quick overview of the available categories:
- Report (For in-game issues, like race blockers)
- Rename Requests
- Ban Appeals
- Complaints
- Admin-Mail (for miscellaneous issues)
  * Note: No technical support.

**「Skin Submissions」**
<#{Channels.SKIN_INFO}> - Skin submission information and rules.
<#{Channels.SKIN_SUBMIT}> - Share and evaluate user-submitted player skins for our official database.

**「Map Testing」**
<#{Channels.TESTING_INFO}> - Discover the vital rules map creators must adhere to for their community-created maps to be released on DDNet in this channel.
<#{Channels.TESTING_SUBMIT}> - This is the channel where creators can upload their map creations for evaluation.
"""

welcome_ddnet_links = """
<https://ddnet.org/> - The official DDNet homepage
<https://forum.ddnet.org/> - Our forums for staff applications, Events, Tutorials and more
<https://wiki.ddnet.org/> - The official DDNet wiki, maintained by: <@!97739437772902400> and <@!846386020756226098>

**「For Developers」**
<https://github.com/ddnet/> - All ddnet related repositories that assist in managing our complete infrastructure

**「Our Discord Invite Links」**
<https://ddnet.org/discord/> OR <https://discord.gg/ddracenetwork>
"""

welcome_ddnet_roles = f"""
**「DDNet Staff」**
<@&{Roles.ADMIN}>: The administrators of DDNet.
<@&{Roles.DISCORD_MODERATOR}>: People who keep our Discord server in check.
<@&{Roles.MODERATOR}>: People who moderate our in-game & discord server(s).

<@&{Roles.TESTER}>: Testers assess map suitability for our map pool, ensuring quality and reporting bugs to submitters.
<@&{Roles.TRIAL_TESTER}>: Much like the previous role, all incoming Testers will begin as Trial Testers.

<@&{Roles.SKIN_DB_CREW}>: The Skin Database Crew manages our skin database, ensuring suitability and quality.

**「Achievement Roles」**
<@&{Roles.WIKI_CONTRIBUTOR}>: Can be earned for Wiki contributions that are deemed significant.
<@&{Roles.DEV}>: Assigned to users with accepted pull requests on our main repository.
<@&{Roles.TOURNAMENT_WINNER}>: Assigned to users who have won tournaments.

**「Other」**
<@&{Roles.TESTING}>: All users can obtain this role in <#{Channels.TESTING_INFO}> to access all existing testing channels.
"""

welcome_community_links = """
**「Sites」**
<https://teeworlds.com/> - The official Teeworlds homepage
<https://skins.tw/> - A database containing game assets for both Teeworlds 0.6 and 0.7
<https://ddstats.org/status> || <https://ddstats.org/> - Alternative to https://ddnet.org/status/
<https://db.ddstats.org/> - Datasette instance of the official DDNet record database
<https://trashmap.ddnet.org/> - DDNet Trashmap is a service for mappers who can't host their own servers.

**「Other Community Servers」**
<https://discord.kog.tw/> - KoG (King of Gores)
<https://discord.gg/utB4Rs3> - FNG, hosted by @noby
<https://discord.gg/gbgEs7m6kK> - Unique, a server network that prioritizes maps specifically designed for racing.
<https://discord.gg/mTVQuEDzzc> - Teeworlds Data, a hub for game asset resources.
<https://discord.gg/YnwAXPB3zj> - Tee Directory, another hub for game asset resources.
<https://discord.gg/fYaBTzY> - Blockworlds
<https://discord.gg/NUfhgTe> - iF|City, a city mod server to hang out with friends.
<https://pic.zcat.ch/> - Ƥ.I.Ƈ. Community, a dedicated zCatch events & tournament server.

**「Non English Speaking Servers」**
<https://discord.gg/CauG396Waa> - Tee Olympics 🇫🇷
<https://discord.gg/SyZER9HR83> - DDNET France 🇫🇷
<https://discord.gg/2hdeGVtKdt> - New Generation Clan [NwG] + Community 🇪🇸
<https://discord.gg/mpvWdvH> <> [QQ](<https://qun.qq.com/qqweb/qunpro/share?_wv=3&_wwv=128&inviteCode=AI8a2&from=246610&biz=ka#/out>) - Teeworlds中文社区 🇨🇳
<https://discord.gg/gSHZZkqBxJ> - MadTeaParty 🇷🇺
<https://discord.gg/GZW2b87xwe> - DDRusNetwork 🇷🇺
<https://discord.gg/DTaPZa699B> - TeeFusion 🇷🇺
<https://discord.gg/P8CpKWgUGZ> - DDBalkan / Victory Community
<https://discord.gg/Uz4Th6sFW5> - DDNet Polska 🇵🇱
"""

#################################
#            TESTING            #
#################################


testing_info_header = f"""
# <:ddnet:{Emojis.DDNET}> Map Release Requirements
If you want to have your map released on DDNet, it has to follow the [mapping rules](https://ddnet.org/rules/).
If you're looking for tips on how to improve your submission, be sure to check out our [guidelines](https://ddnet.org/guidelines/).
"""

testing_info = f"""
# 📬 Map Submissions
When you are ready to release it, send it in <#{Channels.TESTING_SUBMIT}>.
The message has to contain the map's details as follows: "<map_name>" by <mapper> [<server_type>]
```markdown
# Server Types
👶 Novice
🌸 Moderate
💪 Brutal
💀 Insane
♿ Dummy
👴 Oldschool
⚡ Solo
🏁 Race
🎉 Fun
```
`[Credits: Cøke, Jao, Ravie, Lady Saavik, Pipou, Patiga, Learath, RayB, Soreu, hi_leute_gll, Knight, Oblique. & Index]`
"""

testing_channel_access = f"""
# Accessing TEST Servers
To join, search for "Test" in the server browser and enter "nimrocks" as password when asked.
To obtain testing powers, open the rcon console (F2), leave "enter username" blank and press enter, then type the following password: test4321

__Useful testing rcon commands:__
```ansi
[32mSuper[38m, [31mUnsuper [38m(makes you invulnerable, grants you infinite jumps)
[34mUp[38m, [34mDown[38m, [34mLeft[38m, [34mRight [38m(helps you move around the map)
[34mWeapons[38m [38m(gives you all the weapons)
[34mTele [38m(helps you move around the map)
[32mDeep[38m, [31mUndeep [38m(puts you into deep/undeep freeze)
[32mSolo[38m, [31mUnsolo [38m(puts you into solo/unsolo part)
```
Find more at <https://ddnet.org/settingscommands/>
If you wish to test maps locally, visit the following wiki article: <https://wiki.ddnet.org/wiki/LAN_Server>
# Accessing Testing Channels
- To see all channels, add a ✅ reaction to this message
- To see individual testing channels, add a ✅ reaction to the submission message in <#{Channels.TESTING_SUBMIT}> of the map's channel you want to see,
  removing the reaction reverts it
- Find archived channels at https://ddnet.tw/testlogs/ 
"""
