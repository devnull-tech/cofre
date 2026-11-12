import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property bool busy: false
    property string error: ""
    readonly property bool canCreate: password.text.length >= 8 && password.text === repeat.text && !busy

    function create() {
        if (!canCreate) return
        busy = true
        error = ""
        app.api("create", [password.text], function(r) {
            busy = false
            if (r.ok) {
                app.vaultExists = true
                app.unlocked = true
                pageStack.replace(Qt.resolvedUrl("VaultPage.qml"))
            } else {
                error = app.resultError(r)
            }
        })
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge

        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingLarge

            PageHeader { title: qsTr("New vault") }

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "/usr/share/icons/hicolor/172x172/apps/harbour-cofre.png"
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeSmall
                text: qsTr("Choose a master password. Everything you store in the vault is encrypted with it.") +
                      "\n\n" + qsTr("If you forget it, there is no way to recover your files.")
            }

            PasswordField {
                id: password
                label: qsTr("Password (at least 8 characters)")
                enabled: !page.busy
                focus: true
                EnterKey.iconSource: "image://theme/icon-m-enter-next"
                EnterKey.onClicked: repeat.focus = true
            }

            PasswordField {
                id: repeat
                label: text.length > 0 && text !== password.text ? qsTr("Passwords do not match") : qsTr("Repeat the password")
                errorHighlight: text.length > 0 && text !== password.text
                enabled: !page.busy
                EnterKey.enabled: page.canCreate
                EnterKey.iconSource: "image://theme/icon-m-enter-accept"
                EnterKey.onClicked: page.create()
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: page.error !== ""
                wrapMode: Text.Wrap
                color: Theme.errorColor
                text: page.error
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Create vault")

                enabled: page.canCreate
                onClicked: page.create()
            }

            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                running: page.busy
                visible: running
            }
        }
    }
}
