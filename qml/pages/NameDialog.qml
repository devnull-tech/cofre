import QtQuick 2.0
import Sailfish.Silica 1.0

// Diálogo genérico para pedir un nombre (nueva carpeta, renombrar…).
Dialog {
    id: dialog

    property string title
    property string acceptText: qsTr("Accept")
    property string name
    property var callback

    canAccept: field.text.trim().length > 0 && field.text.trim() !== name

    onAccepted: if (callback) callback(field.text.trim())

    Column {
        width: parent.width

        DialogHeader {
            title: dialog.title
            acceptText: dialog.acceptText
        }

        TextField {
            id: field
            width: parent.width
            label: qsTr("Name")

            text: dialog.name
            focus: true
            EnterKey.enabled: dialog.canAccept
            EnterKey.iconSource: "image://theme/icon-m-enter-accept"
            EnterKey.onClicked: dialog.accept()
        }
    }
}
