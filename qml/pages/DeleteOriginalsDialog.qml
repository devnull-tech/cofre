import QtQuick 2.0
import Sailfish.Silica 1.0

Dialog {
    id: dialog

    // Las rutas se quedan en Python (bytes): aquí solo se muestra el resumen.
    property int count: 0
    property bool folderImport: false

    onRejected: app.api("keep_originals")
    onAccepted: {
        app.api("delete_originals", [], function(r) {
            if (!r.ok) {
                app.notify(app.resultError(r))
            } else if (r.failed.length > 0) {
                app.notify(qsTr("Deleted %1. Could not delete %2: %3").arg(r.deleted).arg(r.failed[0].name)
                           .arg(app.errorText(r.failed[0].error, r.failed[0].params)))
            } else {
                app.notify(r.deleted === 1 ? qsTr("Original deleted") : qsTr("%1 originals deleted").arg(r.deleted))
            }
        })
    }

    Column {
        width: parent.width
        spacing: Theme.paddingLarge

        DialogHeader {
            acceptText: qsTr("Delete")
            cancelText: qsTr("Keep")
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * x
            wrapMode: Text.Wrap
            color: Theme.highlightColor
            text: (dialog.count === 1 ? qsTr("The file is now encrypted in the vault.")
                                      : qsTr("The %1 files are now encrypted in the vault.").arg(dialog.count)) +
                  "\n\n" + qsTr("Do you want to delete the unencrypted originals from the phone?") +
                  (dialog.folderImport ? "\n\n" + qsTr("Folders left empty will also be removed.") : "")
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * x
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.secondaryHighlightColor
            text: qsTr("Note that the gallery may keep cached thumbnails, and copies in the cloud or on other devices are not deleted.")


        }
    }
}
