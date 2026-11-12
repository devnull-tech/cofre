import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property string fileId
    property string name
    property string url
    property string kind
    property bool loading: true
    property bool truncated: false
    property string error: ""

    allowedOrientations: Orientation.All

    Component.onCompleted: {
        app.api("read_text", [fileId], function(r) {
            loading = false
            if (r.ok) {
                content.text = r.text
                truncated = r.truncated
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
            spacing: Theme.paddingMedium

            PageHeader {
                title: page.name
                description: page.truncated ? qsTr("Showing only the first MB") : ""

            }

            Label {
                id: content
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.primaryColor
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: page.error !== ""
                wrapMode: Text.Wrap
                color: Theme.errorColor
                text: page.error
            }
        }

        VerticalScrollDecorator {}
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: page.loading
    }
}
