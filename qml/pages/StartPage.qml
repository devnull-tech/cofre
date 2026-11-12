import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    function proceed() {
        if (app.ready && status === PageStatus.Active) {
            pageStack.replace(Qt.resolvedUrl(app.vaultExists ? "UnlockPage.qml" : "SetupPage.qml"),
                              {}, PageStackAction.Immediate)
        }
    }

    onStatusChanged: proceed()

    Connections {
        target: app
        onReadyChanged: page.proceed()
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: true
    }
}
