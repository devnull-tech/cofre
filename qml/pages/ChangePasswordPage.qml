import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property bool busy: false
    property string error: ""
    readonly property bool canChange: current.text.length > 0 && password.text.length >= 8
                                      && password.text === repeat.text && !busy

    function change() {
        if (!canChange) return
        busy = true
        error = ""
        app.api("change_password", [current.text, password.text], function(r) {
            busy = false
            if (r.ok) {
                app.notify(qsTr("Password changed"))
                pageStack.pop()
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

            PageHeader { title: qsTr("Change password") }

            PasswordField {
                id: current
                label: qsTr("Current password")
                enabled: !page.busy
                focus: true
                EnterKey.iconSource: "image://theme/icon-m-enter-next"
                EnterKey.onClicked: password.focus = true
            }

            PasswordField {
                id: password
                label: qsTr("New password (at least 8 characters)")
                enabled: !page.busy
                EnterKey.iconSource: "image://theme/icon-m-enter-next"
                EnterKey.onClicked: repeat.focus = true
            }

            PasswordField {
                id: repeat
                label: text.length > 0 && text !== password.text ? qsTr("Passwords do not match") : qsTr("Repeat the new password")
                errorHighlight: text.length > 0 && text !== password.text
                enabled: !page.busy
                EnterKey.enabled: page.canChange
                EnterKey.iconSource: "image://theme/icon-m-enter-accept"
                EnterKey.onClicked: page.change()
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
                text: qsTr("Change")

                enabled: page.canChange
                onClicked: page.change()
            }

            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                running: page.busy
                visible: running
            }
        }
    }
}
