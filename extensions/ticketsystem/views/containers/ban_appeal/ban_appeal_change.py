from extensions.ticketsystem.views.containers.change_category import (
    ChangeCategoryContainer,
)
from extensions.ticketsystem.views.modals import ban_appeal_m


class BanAppealChangeContainer(ChangeCategoryContainer):
    title = "# [Ban Appeal Request](https://-/)"
    intro = (
        "Your current request doesn't seem to fit the current category!\n"
        "In order for us to process your ban appeal, we need some additional information from you.\n"
        "Click the Submit button below to start."
    )
    submit_custom_id = "BanAppealSubmitBtn"

    def make_modal(self, interaction):
        return ban_appeal_m.BanAppealModal(interaction.client, ticket=self.ticket)
