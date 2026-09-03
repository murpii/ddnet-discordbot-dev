from extensions.ticketsystem.views.containers.change_category import (
    ChangeCategoryContainer,
)
from extensions.ticketsystem.views.modals import rename_m


class RenameChangeContainer(ChangeCategoryContainer):
    title = "# [Player Rename Request](https://ddnet.org/renames/)"
    intro = (
        "Your current request doesn't seem to fit the current category!\n"
        "In order for us to process your rename request, we need some additional information from you.\n"
        "Click the Submit button below to start."
    )
    submit_custom_id = "RenameSubmitBtn"

    def make_modal(self, interaction):
        return rename_m.RenameModal(interaction.client, ticket=self.ticket)
