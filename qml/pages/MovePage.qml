import QtQuick 2.0
import Sailfish.Silica 1.0

// Elige la carpeta de destino para mover uno o varios elementos.
// items: [{type: "file"|"folder", id, name}]
Page {
    id: page

    property var items: []
    property string currentFolder
    property bool busy: false

    signal moved()

    readonly property string description: items.length === 1 ? items[0].name
                                                              : qsTr("%1 items").arg(items.length)

    function move(target) {
        busy = true
        app.api("move_items", [items, target], function(r) {
            busy = false
            if (!r.ok) {
                app.notify(app.resultError(r))
                return
            }
            if (r.failed.length > 0) {
                app.notify(qsTr("Could not move %1: %2").arg(r.failed[0].name)
                           .arg(app.errorText(r.failed[0].error, r.failed[0].params)))
            }
            app.filesChanged()
            page.moved()
            pageStack.pop()
        })
    }

    Component.onCompleted: {
        // Las carpetas que se mueven no pueden ser destino (ni sus subcarpetas).
        var exclude = []
        for (var i = 0; i < items.length; i++) {
            if (items[i].type === "folder") exclude.push(items[i].id)
        }
        app.api("folder_tree", [exclude], function(r) {
            if (!r.ok) return
            folderModel.append({ id: "", name: qsTr("Cofre (home)"), depth: 0 })
            for (var j = 0; j < r.folders.length; j++) {
                var f = r.folders[j]
                folderModel.append({ id: f.id, name: f.name, depth: f.depth + 1 })
            }
        })
    }

    ListModel { id: folderModel }

    SilicaListView {
        anchors.fill: parent
        model: folderModel
        enabled: !page.busy

        header: PageHeader {
            title: qsTr("Move to…")
            description: page.description
        }

        delegate: ListItem {
            id: item
            readonly property bool isCurrent: model.id === page.currentFolder
            enabled: !isCurrent
            onClicked: page.move(model.id)

            Image {
                id: icon
                x: Theme.horizontalPageMargin + model.depth * Theme.paddingLarge * 2
                anchors.verticalCenter: parent.verticalCenter
                source: model.id === "" ? "/usr/share/icons/hicolor/86x86/apps/harbour-cofre.png"
                                        : "image://theme/icon-m-file-folder"
                sourceSize.width: Theme.iconSizeMedium
                sourceSize.height: Theme.iconSizeMedium
                opacity: item.isCurrent ? Theme.opacityLow : 1.0
            }

            Label {
                anchors {
                    left: icon.right
                    leftMargin: Theme.paddingMedium
                    right: parent.right
                    rightMargin: Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }
                text: model.name + (item.isCurrent ? " " + qsTr("(current)") : "")

                truncationMode: TruncationMode.Fade
                color: item.isCurrent ? Theme.secondaryColor
                                      : (item.highlighted ? Theme.highlightColor : Theme.primaryColor)
            }
        }

        VerticalScrollDecorator {}
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: page.busy
    }
}
