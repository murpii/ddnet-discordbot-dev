"""Template for constants.py (which is gitignored).

Copy this file to constants.py and replace every 0 with the real Discord
snowflake (channel / role / emoji / ... ID). Mirrors constants.py exactly --
same Enum classes and members -- so a filled-in copy is a drop-in.

A 0 left in place means "unset". For the channels explicitly noted below the
bot treats 0 as "disabled" or "auto-detect by name"; everywhere else fill in
the real ID before running the bot. The public URLs are kept real.
"""
from enum import IntEnum, StrEnum


class Guilds(IntEnum):
    DDNET = 0


class Channels(IntEnum):
    # Information Category
    CAT_INFORMATION = 0
    WELCOME = 0
    JOIN_LEAVE = 0
    ANNOUNCEMENTS = 0
    MAP_RELEASES = 0
    RECORDS = 0

    # Development Category
    CAT_DEVELOPMENT = 0
    DEVELOPER = 0
    BUGS = 0

    # DDraceNetwork Category
    CAT_DDRACENETWORK = 0
    GENERAL = 0
    SHOWROOM = 0
    MEDIA_ONLY = 0
    QUESTIONS = 0
    WIKI = 0
    WIKI_THREAD = 0
    OFF_TOPIC = 0
    MAPPING = 0
    BOT_CMDS = 0

    # Ticket Category
    CAT_TICKETS = 0
    # 0 = unset: the bot then finds/creates a category named "Community Applications" by name
    CAT_COMMUNITY_APPS = 0
    TICKETS_INFO = 0
    TICKETS_TRANSCRIPTS = 0
    TH_REPORTS = 0
    TH_BAN_APPEALS = 0
    TH_RENAMES = 0
    TH_COMPLAINTS = 0
    TH_ADMIN_MAIL = 0
    TH_COMMUNITY_APPS = 0

    # SkinDB Category
    CAT_SKIN_SUBM = 0
    SKIN_INFO = 0
    SKIN_SUBMIT = 0
    SKIN_LOGS = 0

    # Moderator Category
    CAT_MODERATOR = 0
    MODERATOR = 0
    MODERATOR_LOUNGE = 0
    BANS = 0
    PLAYERFINDER = 0
    MATRIX_MOD = 0
    LOGS = 0
    # Log sub-threads inside LOGS; 0 = fall back to posting in the LOGS channel
    LOG_MESSAGES = 0      # message deletions + edits
    LOG_MOD_ACTIONS = 0   # bans/kicks/timeouts, nickname changes, testing bans, guild pauses
    LOG_MOD_ALERTS = 0    # blacklist hits, automod spam alerts

    # Internal Category
    CAT_INTERNAL = 0
    MOD_C = 0
    TESTER_C = 0
    ADMIN = 0
    DBG = 0

    # Testing Category
    CAT_TESTING = 0
    TESTER_HUB = 0        # tester button hub; 0 disables the hub
    TESTER_META = 0
    TESTER_VOTES = 0
    TESTING_INFO = 0
    TESTING_SUBMIT = 0
    CAT_WAITING = 0
    CAT_EVALUATED = 0

    # Hub control channels
    MOD_HUB = 0           # moderation button hub; 0 disables the hub
    ADMIN_HUB = 0         # admin button hub; 0 disables the hub
    TESTER_CHAT = 0


class Forums(IntEnum):
    MODERATOR_APPS = 0
    MODERATOR_ONBOARDING = 0
    TESTER_ONBOARDING = 0
    QUESTIONS = 0


class ForumTags(IntEnum):
    SOLVED = 0


class Roles(IntEnum):
    BANNER_CURATOR = 0

    ADMIN = 0
    DISCORD_MODERATOR = 0
    MODERATOR = 0
    TESTER = 0
    TESTER_EXCL_TOURNAMENTS = 0
    TRIAL_TESTER = 0
    TRIAL_TESTER_EXCL_TOURNAMENTS = 0
    TESTING = 0
    SKIN_DB_CREW = 0
    WIKI_CONTRIBUTOR = 0
    DEV = 0
    TOURNAMENT_WINNER = 0
    MAPPER = 0


ALL_TESTER_ROLES: list = [
    Roles.TESTER,
    Roles.TESTER_EXCL_TOURNAMENTS,
    Roles.TRIAL_TESTER,
    Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
]

# Raw user IDs (not roles) of the wiki curators.
WIKI_CURATOR_ROLES: list = [
    0,
    0,
]


class Emojis(IntEnum):
    DDNET = 0
    F3 = 0
    F4 = 0
    HAPPY = 0
    MMM = 0
    FLAG_UNK = 0
    CAMMOSTRIPES = 0
    BROWNBEAR = 0
    TEAR = 0
    SORRY = 0

    # Alphabet
    A = 0
    B = 0
    C = 0
    D = 0
    E = 0
    F = 0
    G = 0
    H = 0
    I = 0
    J = 0
    K = 0
    L = 0
    M = 0
    N = 0
    O = 0
    P = 0
    Q = 0
    R = 0
    S = 0
    T = 0
    U = 0
    V = 0
    W = 0
    X = 0
    Y = 0
    Z = 0

    # Symbols
    UNDERSCORE = 0


class Webhooks(IntEnum):
    DDNET_RECORDS = 0
    DDNET_MAP_RELEASES = 0


class Messages(IntEnum):
    TESTING_BANS_EMBED = 0
    TESTING_BANS_CHANGELOG = 0


class URLs(StrEnum):
    GITHUB_URL = "https://github.com/ddnet/ddnet-discordbot"
    DDNET_MAPPING_RULES = "https://ddnet.org/mapping/rules/"
    DDNET_MAPPING_GUIDELINES = "https://ddnet.org/mapping/guidelines/"
    DDNET_MASTER_RULES = "https://ddnet.org/rules/master/"
    DDNET_COMMUNITY_RULES = "https://ddnet.org/rules/community/"
    WIKI_API = "https://wiki.ddnet.org/w/api.php"
    WIKI_PAGE_URL = "https://wiki.ddnet.org/wiki/"
