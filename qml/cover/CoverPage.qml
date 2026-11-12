import QtQuick 2.0
import Sailfish.Silica 1.0

CoverBackground {
    Column {
        anchors.centerIn: parent
        width: parent.width
        spacing: Theme.paddingMedium

        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            source: "/usr/share/icons/hicolor/108x108/apps/harbour-cofre.png"
            opacity: app.unlocked ? 1.0 : 0.6
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Cofre")
            font.pixelSize: Theme.fontSizeLarge
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: app.importing ? qsTr("Encrypting %1%").arg(Math.round(app.importProgress * 100))
                                : (app.unlocked ? qsTr("Open") : qsTr("Locked"))
            color: Theme.secondaryColor
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    CoverActionList {
        enabled: app.unlocked && !app.importing
        CoverAction {
            iconSource: "image://theme/icon-cover-cancel"
            onTriggered: app.lockVault()
        }
    }
}
