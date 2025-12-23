from .report import ReportEmbed, ReportInfoEmbed
from .rename import RenameEmbed, RenameInfoEmbed
from .complaint import ComplaintEmbed, ComplaintInfoEmbed
from .ban_appeal import BanAppealEmbed, BanAppealInfoEmbed
from .admin_mail import AdminMailEmbed, AdminMailInfoEmbed
from .main_menu import MainMenuEmbed, MainMenuFollowUp
from .extras import FollowUpEmbed

__all__ = [
    ReportEmbed, ReportInfoEmbed,
    RenameEmbed, RenameInfoEmbed,
    ComplaintEmbed, ComplaintInfoEmbed,
    BanAppealEmbed, BanAppealInfoEmbed,
    AdminMailEmbed, AdminMailInfoEmbed,
    FollowUpEmbed,
    MainMenuEmbed, MainMenuFollowUp,
]
