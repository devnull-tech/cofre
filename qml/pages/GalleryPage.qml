import QtQuick 2.0
import Sailfish.Silica 1.0

// Visor de fotos y vídeos de una carpeta: se pasa de uno a otro deslizando.
// items: [{id, name, kind ("image"|"video"|"audio"), orientation}]
Page {
    id: page

    property var items: []
    property int startIndex: 0
    property bool chrome: true

    readonly property var current: view.currentIndex >= 0 && view.currentIndex < items.length
                                   ? items[view.currentIndex] : null

    allowedOrientations: Orientation.All

    Rectangle {
        anchors.fill: parent
        color: "black"
    }

    ListView {
        id: view
        anchors.fill: parent
        model: page.items
        orientation: ListView.Horizontal
        snapMode: ListView.SnapOneItem
        highlightRangeMode: ListView.StrictlyEnforceRange
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 0  // solo se carga lo visible: nada descifrado de más
        interactive: !(currentItem && currentItem.blockSwipe)

        Component.onCompleted: {
            currentIndex = page.startIndex
            positionViewAtIndex(page.startIndex, ListView.Beginning)
        }

        delegate: Item {
            id: slot
            width: view.width
            height: view.height

            readonly property bool isCurrent: ListView.isCurrentItem
            readonly property bool blockSwipe: loader.item ? loader.item.blockSwipe : false

            Loader {
                id: loader
                anchors.fill: parent
                Component.onCompleted: {
                    var props = { fileId: modelData.id, name: modelData.name,
                                  orientation: modelData.orientation || 1 }
                    if (modelData.kind === "image") {
                        setSource("GalleryImage.qml", props)
                    } else {
                        props.audioOnly = modelData.kind === "audio"
                        setSource("GalleryVideo.qml", props)
                    }
                }
            }

            Binding {
                target: loader.item
                property: "active"
                value: slot.isCurrent && page.status === PageStatus.Active
                when: loader.status === Loader.Ready
            }

            Binding {
                target: loader.item
                property: "chromeVisible"
                value: page.chrome
                when: loader.status === Loader.Ready
            }

            Connections {
                target: loader.item
                ignoreUnknownSignals: true
                onToggleChrome: page.chrome = !page.chrome
            }
        }
    }

    // Cabecera con el nombre y la posición (se oculta tocando la pantalla)
    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: header.height + Theme.paddingLarge
        visible: page.chrome
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.8) }
            GradientStop { position: 1.0; color: "transparent" }
        }

        Column {
            id: header
            x: Theme.horizontalPageMargin
            y: Theme.paddingLarge
            width: parent.width - 2 * x

            Label {
                width: parent.width
                horizontalAlignment: Text.AlignRight
                text: page.current ? page.current.name : ""
                truncationMode: TruncationMode.Fade
                color: Theme.lightPrimaryColor
            }

            Label {
                width: parent.width
                horizontalAlignment: Text.AlignRight
                visible: page.items.length > 1
                text: (view.currentIndex + 1) + " / " + page.items.length
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.lightSecondaryColor
            }
        }
    }
}
