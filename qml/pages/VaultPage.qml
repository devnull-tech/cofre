import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0

Page {
    id: page

    property string folderId: ""
    property string folderName: qsTr("Cofre")
    property bool loading: true
    property bool missing: false
    property int fileCount: 0
    property int folderCount: 0

    // --- selección múltiple ---------------------------------------------------
    property bool selecting: false
    property var selection: ({})   // id -> {type, id, name}
    property int selectedCount: 0
    property int selectionRevision: 0  // fuerza a reevaluar "selected" en la lista

    function isSelected(id) {
        return selectionRevision >= 0 && selection.hasOwnProperty(id)
    }

    function setSelected(item, on) {
        if (on) selection[item.id] = { type: item.type, id: item.id, name: item.name }
        else delete selection[item.id]
        selectedCount = Object.keys(selection).length
        selectionRevision++
    }

    function startSelection(item) {
        selection = {}
        selecting = true
        if (item) setSelected(item, true)
        else { selectedCount = 0; selectionRevision++ }
    }

    function endSelection() {
        selecting = false
        selection = {}
        selectedCount = 0
        selectionRevision++
    }

    function selectAll(on) {
        for (var i = 0; i < fileModel.count; i++) setSelected(fileModel.get(i), on)
    }

    function selectedItems() {
        var out = []
        for (var id in selection) out.push(selection[id])
        return out
    }

    function batchResult(r, verb) {
        if (!r.ok) {
            app.notify(app.resultError(r))
        } else if (r.failed.length > 0) {
            app.notify(qsTr("%1 failed. %2: %3").arg(r.failed.length).arg(r.failed[0].name)
                       .arg(app.errorText(r.failed[0].error, r.failed[0].params)))
        } else {
            app.notify(verb)
        }
    }

    function moveSelected() {
        var obj = pageStack.push(Qt.resolvedUrl("MovePage.qml"),
                                 { items: selectedItems(), currentFolder: folderId })
        obj.moved.connect(page.endSelection)
    }

    function exportSelected() {
        var items = selectedItems()
        endSelection()
        app.api("export_items", [items], function(r) {
            batchResult(r, r.done === 1 ? qsTr("1 file exported to Downloads")
                                        : qsTr("%1 files exported to Downloads").arg(r.done))
        })
    }

    function deleteSelected() {
        var items = selectedItems()
        endSelection()
        remorse.execute(items.length === 1 ? qsTr("Deleting 1 item") : qsTr("Deleting %1 items").arg(items.length),
                        function() {
            app.api("delete_items", [items], function(r) {
                batchResult(r, r.done === 1 ? qsTr("1 item deleted") : qsTr("%1 items deleted").arg(r.done))
                app.filesChanged()
            })
        })
    }

    // --- listado --------------------------------------------------------------

    function reload() {
        app.api("list_files", [folderId], function(r) {
            loading = false
            if (!r.ok) {
                missing = app.unlocked
                fileModel.clear()
                return
            }
            missing = false
            if (r.path.length > 0) folderName = r.path[r.path.length - 1].name
            fileModel.clear()
            var i
            for (i = 0; i < r.folders.length; i++) {
                var f = r.folders[i]
                fileModel.append({ type: "folder", id: f.id, name: f.name, kind: "folder",
                                   size: 0, added: f.created, thumb: "", orientation: 1,
                                   count: f.count })
            }
            for (i = 0; i < r.files.length; i++) {
                var e = r.files[i]
                fileModel.append({ type: "file", id: e.id, name: e.name, kind: e.kind,
                                   size: e.size, added: e.added, thumb: e.thumb,
                                   orientation: e.orientation, count: 0 })
            }
            folderCount = r.folders.length
            fileCount = r.files.length
            // Quita de la selección lo que ya no está en la carpeta
            if (selecting) {
                var present = {}
                for (i = 0; i < fileModel.count; i++) present[fileModel.get(i).id] = true
                for (var id in selection) if (!present[id]) delete selection[id]
                selectedCount = Object.keys(selection).length
                selectionRevision++
            }
        })
    }

    function describe() {
        var parts = []
        if (folderCount > 0) parts.push(folderCount === 1 ? qsTr("1 folder") : qsTr("%1 folders").arg(folderCount))
        if (fileCount > 0 || folderCount === 0) parts.push(fileCount === 1 ? qsTr("1 file") : qsTr("%1 files").arg(fileCount))
        return parts.join(" · ")
    }

    function iconFor(kind) {
        var variant = Theme.colorScheme === Theme.LightOnDark ? "-light" : "-dark"
        switch (kind) {
        case "folder": return "image://theme/icon-m-file-folder"
        case "image": return "image://theme/icon-m-file-image"
        case "video": return "image://theme/icon-m-file-video"
        case "audio": return "image://theme/icon-m-file-audio"
        case "text": return "image://theme/icon-m-file-note" + variant
        default: return "image://theme/icon-m-file-other" + variant
        }
    }

    function openItem(item) {
        if (item.type === "folder") {
            pageStack.push(Qt.resolvedUrl("VaultPage.qml"), { folderId: item.id, folderName: item.name })
            return
        }
        switch (item.kind) {
        case "image":
        case "video":
            // Galería con todas las fotos y vídeos de la carpeta, en el orden de la lista
            var items = [], start = 0
            for (var i = 0; i < fileModel.count; i++) {
                var e = fileModel.get(i)
                if (e.kind !== "image" && e.kind !== "video") continue
                if (e.id === item.id) start = items.length
                items.push({ id: e.id, name: e.name, kind: e.kind, orientation: e.orientation })
            }
            pageStack.push(Qt.resolvedUrl("GalleryPage.qml"), { items: items, startIndex: start })
            break
        case "audio":
            pageStack.push(Qt.resolvedUrl("GalleryPage.qml"),
                           { items: [{ id: item.id, name: item.name, kind: "audio", orientation: 1 }] })
            break
        case "text":
            pageStack.push(Qt.resolvedUrl("TextPage.qml"), { fileId: item.id, name: item.name })
            break
        default:
            app.notify(qsTr("No preview for this type. You can export it."))
        }
    }

    function runImport(fn, args) {
        app.importing = true
        app.importProgress = 0
        app.importLabel = ""
        app.api(fn, args, function(r) {
            app.importing = false
            app.filesChanged()
            if (!r.ok) {
                app.notify(qsTr("Import failed: %1").arg(app.resultError(r)))
                return
            }
            if (r.failed.length > 0) {
                app.notify(qsTr("%1 files could not be imported: %2").arg(r.failed.length)
                           .arg(app.errorText(r.failed[0].error, r.failed[0].params)))
            } else if (r.imported === 0) {
                app.notify(qsTr("There were no files to import"))
            }
            if (r.imported > 0 && app.unlocked) {
                pageStack.completeAnimation()
                pageStack.push(Qt.resolvedUrl("DeleteOriginalsDialog.qml"),
                               { count: r.imported, folderImport: r.folder_import })
            }
        })
    }

    function exportOne(type, id, name) {
        app.api("export_items", [[{ type: type, id: id, name: name }]], function(r) {
            page.batchResult(r, type === "folder" ? qsTr("Folder exported to Downloads") : qsTr("Exported to Downloads"))
        })
    }

    function renameOne(type, id, name) {
        askName(qsTr("Rename"), qsTr("Rename"), name, function(newName) {
            app.api(type === "folder" ? "rename_folder" : "rename_file", [id, newName], page.done)
        })
    }

    function askName(title, acceptText, name, callback) {
        pageStack.push(Qt.resolvedUrl("NameDialog.qml"),
                       { title: title, acceptText: acceptText, name: name, callback: callback })
    }

    function done(r) {
        if (!r.ok) app.notify(app.resultError(r))
        app.filesChanged()
    }

    Component.onCompleted: reload()

    Connections {
        target: app
        onFilesChanged: page.reload()
    }

    ListModel { id: fileModel }

    RemorsePopup { id: remorse }

    Component {
        id: filePickerComponent
        MultiContentPickerDialog {
            title: qsTr("Add to %1").arg(page.folderName)
            onAccepted: {
                var paths = []
                for (var i = 0; i < selectedContent.count; i++) {
                    var p = selectedContent.get(i).filePath
                    if (p) paths.push(p)
                }
                if (paths.length > 0) page.runImport("import_files", [paths, page.folderId])
            }
        }
    }

    Component {
        id: folderPickerComponent
        FolderPickerPage {
            dialogTitle: qsTr("Import folder")
            onSelectedPathChanged: {
                if (selectedPath) page.runImport("import_folder", [selectedPath, page.folderId])
            }
        }
    }

    SilicaListView {
        id: view
        anchors.fill: parent
        anchors.bottomMargin: actions.visibleSize
        clip: actions.expanded
        model: fileModel

        header: Column {
            width: view.width

            PageHeader {
                title: page.selecting
                       ? (page.selectedCount === 1 ? qsTr("1 selected") : qsTr("%1 selected").arg(page.selectedCount))
                       : page.folderName
                description: page.selecting ? page.folderName : (page.loading ? "" : page.describe())
            }

            ProgressBar {
                width: parent.width
                visible: app.importing
                minimumValue: 0
                maximumValue: 1
                value: app.importProgress
                label: "Cifrando " + app.importLabel
            }
        }

        PullDownMenu {
            busy: app.importing

            // Modo selección
            MenuItem {
                text: qsTr("End selection")
                visible: page.selecting
                onClicked: page.endSelection()
            }
            MenuItem {
                text: page.selectedCount === fileModel.count ? qsTr("Clear selection") : qsTr("Select all")
                visible: page.selecting && fileModel.count > 0
                onClicked: page.selectAll(page.selectedCount !== fileModel.count)
            }

            // Modo normal
            MenuItem {
                text: qsTr("Lock")
                visible: !page.selecting
                onClicked: app.lockVault()
            }
            MenuItem {
                text: qsTr("Change password")
                visible: !page.selecting && page.folderId === ""
                onClicked: pageStack.push(Qt.resolvedUrl("ChangePasswordPage.qml"))
            }
            MenuItem {
                text: qsTr("Select")
                visible: !page.selecting && fileModel.count > 0
                onClicked: page.startSelection(null)
            }
            MenuItem {
                text: qsTr("New folder")
                visible: !page.selecting
                enabled: !page.missing
                onClicked: page.askName(qsTr("New folder"), qsTr("Create"), "", function(name) {
                    app.api("create_folder", [name, page.folderId], page.done)
                })
            }
            MenuItem {
                text: qsTr("Import folder")
                visible: !page.selecting
                enabled: !app.importing && !page.missing
                onClicked: pageStack.push(folderPickerComponent)
            }
            MenuItem {
                text: qsTr("Add files")
                visible: !page.selecting
                enabled: !app.importing && !page.missing
                onClicked: pageStack.push(filePickerComponent)
            }
        }

        ViewPlaceholder {
            enabled: !page.loading && fileModel.count === 0 && !app.importing
            text: page.missing ? qsTr("This folder no longer exists")
                               : (page.folderId === "" ? qsTr("The vault is empty") : qsTr("Empty folder"))
            hintText: page.missing ? "" : qsTr("Pull down to add files or folders")
        }

        delegate: ListItem {
            id: item
            contentHeight: Theme.itemSizeLarge

            readonly property bool isFolder: model.type === "folder"
            readonly property bool selected: page.isSelected(model.id)

            highlighted: down || menuOpen || selected
            menu: page.selecting ? null : contextMenu

            onClicked: {
                if (page.selecting) page.setSelected(model, !selected)
                else page.openItem(model)
            }

            function remove() {
                var id = model.id
                if (isFolder) {
                    remorseAction(qsTr("Deleting folder and its contents"), function() {
                        app.api("delete_folder", [id], page.done)
                    })
                } else {
                    remorseDelete(function() {
                        app.api("delete_file", [id], page.done)
                    })
                }
            }

            Component {
                id: contextMenu
                ContextMenu {
                    MenuItem {
                        text: qsTr("Select")
                        onClicked: page.startSelection(model)
                    }
                    // El menú se destruye al cerrarse: las acciones con respuesta
                    // asíncrona viven en la página, no aquí.
                    MenuItem {
                        text: qsTr("Export to Downloads")
                        onClicked: page.exportOne(model.type, model.id, model.name)
                    }
                    MenuItem {
                        text: qsTr("Rename")
                        onClicked: page.renameOne(model.type, model.id, model.name)
                    }
                    MenuItem {
                        text: qsTr("Move to…")
                        onClicked: pageStack.push(Qt.resolvedUrl("MovePage.qml"),
                                                  { items: [{ type: model.type, id: model.id, name: model.name }],
                                                    currentFolder: page.folderId })
                    }
                    MenuItem {
                        text: qsTr("Delete")
                        onClicked: item.remove()
                    }
                }
            }

            Item {
                id: thumb
                x: Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.itemSizeMedium
                height: width

                Image {
                    id: preview
                    anchors.fill: parent
                    visible: status === Image.Ready
                    // Miniatura EXIF (o la imagen entera si es pequeña), descifrada
                    // en memoria por el proveedor de Python. Sin miniatura: icono.
                    source: model.kind === "image" && model.thumb !== ""
                            ? "image://python/thumb/" + model.id : ""
                    rotation: app.orientationAngle(model.orientation)
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    cache: false
                    clip: true
                }

                Image {
                    anchors.centerIn: parent
                    visible: !preview.visible
                    source: page.iconFor(model.kind)
                }
            }

            Column {
                anchors {
                    left: thumb.right
                    leftMargin: Theme.paddingLarge
                    right: check.visible ? check.left : parent.right
                    rightMargin: check.visible ? Theme.paddingMedium : Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }

                Label {
                    width: parent.width
                    text: model.name
                    truncationMode: TruncationMode.Fade
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                }

                Label {
                    width: parent.width
                    text: item.isFolder
                          ? (model.count === 1 ? qsTr("1 item") : qsTr("%1 items").arg(model.count))
                          : app.formatSize(model.size) + " · " +
                            Format.formatDate(new Date(model.added * 1000), Format.DateMedium) + ", " +
                            Format.formatDate(new Date(model.added * 1000), Format.TimeValue)

                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                    truncationMode: TruncationMode.Fade
                }
            }

            // Indicador del modo selección: un círculo, vacío o relleno
            Rectangle {
                id: check
                visible: page.selecting
                anchors {
                    right: parent.right
                    rightMargin: Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }
                width: Theme.iconSizeSmall
                height: width
                radius: width / 2
                color: item.selected ? Theme.highlightColor : "transparent"
                border.width: Math.max(2, Math.round(Theme.pixelRatio * 2))
                border.color: item.selected ? Theme.highlightColor : Theme.secondaryColor
            }
        }

        VerticalScrollDecorator {}
    }

    // Acciones sobre la selección
    DockedPanel {
        id: actions
        width: parent.width
        height: Theme.itemSizeLarge
        dock: Dock.Bottom
        open: page.selecting

        Row {
            anchors.centerIn: parent
            spacing: Theme.paddingMedium

            Repeater {
                model: [
                    { text: qsTr("Move"), action: "move" },
                    { text: qsTr("Export"), action: "export" },
                    { text: qsTr("Delete"), action: "delete" }

                ]

                Button {
                    width: (actions.width - 2 * Theme.horizontalPageMargin - 2 * Theme.paddingMedium) / 3
                    preferredWidth: width
                    text: modelData.text
                    enabled: page.selectedCount > 0
                    onClicked: {
                        if (modelData.action === "move") page.moveSelected()
                        else if (modelData.action === "export") page.exportSelected()
                        else page.deleteSelected()
                    }
                }
            }
        }
    }
}
