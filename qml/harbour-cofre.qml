import QtQuick 2.0
import Sailfish.Silica 1.0
import io.thp.pyotherside 1.5

ApplicationWindow {
    id: app

    property bool ready: false
    property bool vaultExists: false
    property bool unlocked: false
    property bool importing: false
    property real importProgress: 0
    property string importLabel: ""

    signal filesChanged()
    // Copia temporal de vídeo/audio lista (o fallida). Ver open_media en Python.
    signal mediaReady(string fileId, string url)
    signal mediaError(string fileId, string message)

    // Traduce los códigos de error que devuelve Python (ver error_info en cofre_bridge.py).
    function errorText(code, params) {
        params = params || {}
        switch (code) {
        case "wrong_password": return qsTr("Wrong password")
        case "password_too_short": return qsTr("The password must be at least %1 characters long").arg(params.min)
        case "locked": return qsTr("The vault is locked")
        case "locked_during_import": return qsTr("The vault was locked during the import")
        case "already_exists": return qsTr("A vault already exists")
        case "bad_vault_params": return qsTr("The vault settings are invalid")
        case "index_damaged": return qsTr("The vault index is damaged")
        case "index_save_failed": return qsTr("Could not save the vault index: %1").arg(params.detail)
        case "invalid_id": return qsTr("Invalid identifier")
        case "invalid_name": return qsTr("Invalid name")
        case "folder_not_found": return qsTr("The folder does not exist")
        case "file_not_found": return qsTr("The file does not exist")
        case "not_a_folder": return qsTr("It is not a folder")
        case "move_into_itself": return qsTr("A folder cannot be moved into itself")
        case "no_secure_memory": return qsTr("There is no secure temporary memory to play it. Export the file instead.")
        case "too_big": return qsTr("It is too big to play from memory (%1 MB). Export it to view it.").arg(params.mb)
        case "corrupt": return qsTr("The encrypted file is damaged or has been tampered with")
        case "permission_denied": return qsTr("Permission denied")
        case "no_space": return qsTr("There is not enough storage space")
        case "os_error": return qsTr("System error: %1").arg(params.detail)
        default: return qsTr("Unexpected error: %1").arg(params.detail || code)
        }
    }

    // Texto de error de un resultado {"ok": false, "error": código, "params": {...}}
    function resultError(r) {
        return errorText(r.error, r.params)
    }

    initialPage: Qt.resolvedUrl("pages/StartPage.qml")
    cover: Qt.resolvedUrl("cover/CoverPage.qml")
    allowedOrientations: defaultAllowedOrientations

    function api(fn, args, callback) {
        py.call("cofre_bridge." + fn, args || [], function(result) {
            if (callback) callback(result)
        })
    }

    function notify(text) {
        Notices.show(text, Notice.Short, Notice.Bottom)
    }

    // Orientación EXIF (1..8) a grados de giro.
    function orientationAngle(orientation) {
        switch (orientation) {
        case 3: case 4: return 180
        case 5: case 6: return 90
        case 7: case 8: return 270
        default: return 0
        }
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB"
        return (bytes / 1073741824).toFixed(2) + " GB"
    }

    function lockVault() {
        if (!unlocked) return
        unlocked = false
        // Primero se cierran las pantallas (paran el reproductor) y después Python
        // borra las copias temporales y olvida la clave.
        pageStack.clear()
        pageStack.push(Qt.resolvedUrl("pages/UnlockPage.qml"), {}, PageStackAction.Immediate)
        api("lock")

    }

    // Bloqueo automático cuando la app pasa a segundo plano.
    Timer {
        id: autoLock
        interval: 60 * 1000
        onTriggered: {
            if (app.importing) restart()
            else app.lockVault()
        }
    }

    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state === Qt.ApplicationActive) autoLock.stop()
            else if (app.unlocked) autoLock.restart()
        }
    }

    Python {
        id: py

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../python"))
            setHandler("import-progress", function(fraction, name, current, total) {
                app.importProgress = fraction
                app.importLabel = total > 1 ? ("(" + current + "/" + total + ") " + name) : name
            })
            setHandler("media-ready", function(fid, url) { app.mediaReady(fid, url) })
            setHandler("media-error", function(fid, code, params) {
                app.mediaError(fid, app.errorText(code, params))
            })
            importModule("cofre_bridge", function() {
                app.api("init", [], function(r) {
                    if (!r.ok) {
                        app.notify(qsTr("Could not start: %1").arg(app.resultError(r)))
                        return
                    }
                    app.vaultExists = r.exists
                    app.ready = true
                })
            })
        }

        onError: console.log("Python error: " + traceback)
    }
}
