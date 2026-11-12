import QtQuick 2.0
import Sailfish.Silica 1.0

// Una foto dentro de la galería: zoom con dos dedos, doble toque para volver.
Item {
    id: root

    property string fileId
    property string name
    property int orientation: 1
    property bool active        // es el elemento visible de la galería
    property bool chromeVisible // no se usa aquí; lo tienen todos los elementos

    // Mientras hay zoom, la galería no debe pasar de foto al arrastrar.
    readonly property bool zoomed: flick.contentWidth > flick.width + 1
    readonly property bool blockSwipe: zoomed

    signal toggleChrome()

    // La imagen llega ya decodificada desde Python (proveedor image://python),
    // así que la orientación EXIF hay que aplicarla aquí.
    readonly property int angle: app.orientationAngle(orientation)
    readonly property bool swapped: angle === 90 || angle === 270

    onActiveChanged: if (!active) flick.resetZoom()

    SilicaFlickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: height
        interactive: root.zoomed
        clip: true

        function resetZoom() {
            contentWidth = width
            contentHeight = height
            contentX = 0
            contentY = 0
        }

        onWidthChanged: resetZoom()
        onHeightChanged: resetZoom()

        PinchArea {
            width: Math.max(flick.contentWidth, flick.width)
            height: Math.max(flick.contentHeight, flick.height)

            property real startWidth

            onPinchStarted: startWidth = flick.contentWidth
            onPinchUpdated: {
                flick.contentX += pinch.previousCenter.x - pinch.center.x
                flick.contentY += pinch.previousCenter.y - pinch.center.y
                var scale = Math.max(1, Math.min(6, startWidth * pinch.scale / flick.width))
                flick.resizeContent(flick.width * scale, flick.height * scale, pinch.center)
            }
            onPinchFinished: flick.returnToBounds()

            Item {
                width: flick.contentWidth
                height: flick.contentHeight

                Image {
                    id: image
                    anchors.centerIn: parent
                    width: root.swapped ? parent.height : parent.width
                    height: root.swapped ? parent.width : parent.height
                    rotation: root.angle
                    source: root.fileId !== "" ? "image://python/full/" + root.fileId : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    smooth: !flick.moving
                }

                MouseArea {
                    anchors.fill: parent
                    property real startX
                    property real startY
                    // Un toque muestra/oculta la cabecera; doble toque quita el zoom.
                    // El toque simple espera por si llega un segundo toque.
                    // Un deslizamiento (p. ej. en la primera o última foto, donde la
                    // galería no se mueve) no cuenta como toque.
                    onPressed: { startX = mouse.x; startY = mouse.y }
                    onClicked: {
                        if (Math.abs(mouse.x - startX) < Theme.startDragDistance
                                && Math.abs(mouse.y - startY) < Theme.startDragDistance) {
                            singleTap.restart()
                        }
                    }
                    onDoubleClicked: {
                        singleTap.stop()
                        flick.resetZoom()
                    }
                }

                Timer {
                    id: singleTap
                    interval: 300
                    onTriggered: root.toggleChrome()
                }
            }
        }
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: image.status === Image.Loading
    }

    Label {
        anchors.centerIn: parent
        width: parent.width - 2 * Theme.horizontalPageMargin
        visible: image.status === Image.Error
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        color: Theme.secondaryColor
        text: qsTr("The image could not be displayed")

    }
}
