import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property bool busy: false
    property string error: ""

    function unlock() {
        if (busy || password.text.length === 0) return
        busy = true
        error = ""
        app.api("unlock", [password.text], function(r) {
            busy = false
            if (r.ok) {
                password.text = ""
                app.unlocked = true
                pageStack.replace(Qt.resolvedUrl("VaultPage.qml"))
            } else {
                error = app.resultError(r)
                password.selectAll()
                password.forceActiveFocus()
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

            PageHeader { title: qsTr("Cofre") }

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "/usr/share/icons/hicolor/172x172/apps/harbour-cofre.png"
            }

            PasswordField {
                id: password
                label: qsTr("Password")
                enabled: !page.busy
                focus: true
                errorHighlight: page.error !== ""
                EnterKey.enabled: text.length > 0
                EnterKey.iconSource: "image://theme/icon-m-enter-accept"
                EnterKey.onClicked: page.unlock()
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
                text: qsTr("Open")

                enabled: !page.busy && password.text.length > 0
                onClicked: page.unlock()
            }

            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                running: page.busy
                visible: running
            }
        }
    }
}
