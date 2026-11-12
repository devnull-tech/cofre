import QtQuick 2.0
import Sailfish.Silica 1.0
import QtMultimedia 5.6

// Un vídeo (o audio) dentro de la galería. Al hacerse visible se descifra a la
// RAM privada de la app y empieza a reproducirse; al dejar de verse se para,
// se cancela el descifrado si no había terminado y se borra la copia.
Item {
    id: root

    property string fileId
    property string name
    property int orientation: 1
    property bool active
    property bool chromeVisible: true
    property bool audioOnly: false

    // Mientras se toca la barra de avance, la galería no debe pasar de vídeo.
    readonly property bool blockSwipe: seek.pressed
    readonly property bool playing: video.playbackState === MediaPlayer.PlayingState
    property bool preparing: false
    property bool requested: false  // se pidió una copia descifrada a Python
    property string error: ""
    // GStreamer puede estimar mal la duración de algunos formatos: nunca
    // mostramos una duración menor que la posición.
    readonly property int total: Math.max(video.duration, video.position)

    signal toggleChrome()

    // Al terminar el vídeo GStreamer queda "detenido" y en ese estado ignora los
    // saltos de la barra. Se guarda el punto elegido y se aplica en cuanto
    // vuelve a reproducirse.
    property int pendingSeek: -1

    function seekTo(ms) {
        if (video.playbackState === MediaPlayer.StoppedState) pendingSeek = ms
        else video.seek(ms)
    }

    function togglePlay() {
        if (playing) {
            video.pause()
        } else {
            if (video.playbackState === MediaPlayer.StoppedState && pendingSeek < 0
                    && video.status === MediaPlayer.EndOfMedia) {
                pendingSeek = 0  // al final, play vuelve a empezar
            }
            video.play()
        }
    }

    Timer {
        id: applySeek
        interval: 100
        repeat: true
        running: root.pendingSeek >= 0 && root.playing
        onTriggered: {
            if (!video.seekable) return
            video.seek(root.pendingSeek)
            root.pendingSeek = -1
        }
    }

    function formatTime(ms) {
        var s = Math.floor(ms / 1000)
        var h = Math.floor(s / 3600)
        var m = Math.floor((s % 3600) / 60)
        s = s % 60
        var mm = (m < 10 && h > 0 ? "0" : "") + m
        return (h > 0 ? h + ":" : "") + mm + ":" + (s < 10 ? "0" : "") + s
    }

    function start() {
        if (video.source != "" || preparing) return
        error = ""
        preparing = true
        requested = true
        app.api("open_media", [fileId])
    }

    function stop() {
        startTimer.stop()
        video.stop()
        video.source = ""
        if (requested) app.api("close_media", [fileId])
        requested = false
        pendingSeek = -1
        preparing = false
    }

    // Se espera un momento antes de descifrar: si solo se pasa de largo por
    // este vídeo en la galería, no se llega a empezar.
    Timer {
        id: startTimer
        interval: 350
        onTriggered: root.start()
    }

    onActiveChanged: active ? startTimer.restart() : stop()
    Component.onCompleted: if (active) startTimer.restart()
    Component.onDestruction: stop()

    // Al pasar la app a segundo plano, el vídeo se pausa.
    Connections {
        target: Qt.application
        onStateChanged: if (Qt.application.state !== Qt.ApplicationActive && root.playing) video.pause()
    }

    Connections {
        target: app

        onMediaReady: {
            if (fileId !== root.fileId || !root.active) return
            root.preparing = false
            video.source = url
            video.play()
        }
        onMediaError: {
            if (fileId !== root.fileId) return
            root.preparing = false
            root.error = message
        }
    }

    Video {
        id: video
        anchors.fill: parent
        fillMode: VideoOutput.PreserveAspectFit
    }

    Image {
        anchors.centerIn: parent
        visible: root.audioOnly || (video.source == "" && !root.preparing && root.error === "")
        source: root.audioOnly ? "image://theme/icon-l-music" : "image://theme/icon-l-play"
    }

    MouseArea {
        anchors.fill: parent
        property real startX
        property real startY
        // Un deslizamiento no cuenta como toque (ver GalleryImage.qml)
        onPressed: { startX = mouse.x; startY = mouse.y }
        onClicked: {
            if (Math.abs(mouse.x - startX) < Theme.startDragDistance
                    && Math.abs(mouse.y - startY) < Theme.startDragDistance) {
                root.toggleChrome()
            }
        }
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: root.preparing || (!root.playing && video.status === MediaPlayer.Loading)
    }

    Label {
        anchors.centerIn: parent
        width: parent.width - 2 * Theme.horizontalPageMargin
        visible: root.error !== "" || video.error !== MediaPlayer.NoError
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        color: Theme.errorColor
        text: root.error !== "" ? root.error : qsTr("Cannot play: %1").arg(video.errorString)

    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: controls.height + Theme.paddingLarge
        visible: root.chromeVisible && video.source != ""
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.8) }
        }

        Column {
            id: controls
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.paddingLarge
            width: parent.width

            Slider {
                id: seek
                width: parent.width
                minimumValue: 0
                maximumValue: Math.max(1, root.total)
                enabled: video.seekable
                valueText: root.formatTime(value) + " / " + root.formatTime(root.total)
                onDownChanged: if (!down) root.seekTo(value)
            }

            Binding {
                target: seek
                property: "value"
                value: root.pendingSeek >= 0 ? root.pendingSeek : video.position
                when: !seek.down
            }

            IconButton {
                anchors.horizontalCenter: parent.horizontalCenter
                icon.source: root.playing ? "image://theme/icon-l-pause" : "image://theme/icon-l-play"
                onClicked: root.togglePlay()
            }
        }
    }
}
