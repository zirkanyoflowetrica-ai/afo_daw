import QtQuick
import "../theme"
import "../controls"

// Panel de inicio (X11), como el de un DAW: la Biblioteca en tres columnas, Artistas · Lanzamientos
// del artista · Canciones del lanzamiento. «+ Nuevo» pide el nombre en el sitio (sin ventanas) y
// «Quitar» se confirma con un segundo clic (va a la papelera de la biblioteca, no se borra).
// Doble clic en una canción la abre; abajo, Recientes, «Proyecto suelto» y «Abrir .afo…».
Rectangle {
    id: root
    property var studio
    readonly property var pj: studio ? studio.project : null
    color: Theme.canvas

    property var tree: []
    property var recent: []
    property string artistPath: ""
    property string releasePath: ""
    property string songPath: ""
    readonly property var artist: find(tree, artistPath)
    readonly property var release: artist ? find(artist.releases, releasePath) : null
    readonly property var song: release ? find(release.songs, songPath) : null

    function find(list, p) { for (var i = 0; i < (list || []).length; i++) if (list[i].path === p) return list[i]; return null }
    function reload() {
        if (!studio) return
        var r = studio.call("libraryTree"); tree = r.ok ? r.tree : []
        var q = studio.call("libraryRecent"); recent = q.ok ? q.recent : []
        if (!artist && tree.length) artistPath = tree[0].path
        if (artist && !release) releasePath = artist.releases.length ? artist.releases[0].path : ""
    }
    // Crear: artista, lanzamiento o canción (en el sitio; extra = {type, year} para un lanzamiento)
    function create(kind, name, extra) {
        var parent = kind === "release" ? artistPath : kind === "song" ? releasePath : ""
        var r = studio.call("libraryCreate", kind, parent, name, JSON.stringify(extra || {}))
        if (!r.ok) { studio.toast(r.error); return null }
        reload()
        if (kind === "artist") { artistPath = r.item.path; releasePath = "" }
        else if (kind === "release") releasePath = r.item.path
        else songPath = r.item.path
        reload()
        return r.item
    }
    function removeItem(path) {
        var r = studio.call("libraryRemove", path)
        if (!r.ok) { studio.toast(r.error); return }
        if (path === artistPath) { artistPath = ""; releasePath = "" }
        if (path === releasePath) releasePath = ""
        studio.toast("Movido a la papelera de la biblioteca")
        reload()
    }
    function openSong(s) { if (s && pj.openSong(s)) studio.view = "arrange" }
    onVisibleChanged: if (visible) reload()
    Component.onCompleted: reload()

    // ---------- una columna ----------
    component Col: Rectangle {
        id: col
        property string title
        property string kind
        property var items: []
        property string current: ""
        property string empty: ""
        property bool canAdd: true
        property string addTip: ""
        property bool single: false               // lanzamiento: elegir Álbum / Single al crearlo
        signal picked(var it)
        signal opened(var it)
        color: Theme.panelBody; radius: Theme.radius
        border.width: 1; border.color: Theme.line
        property bool adding: false
        property string relType: "album"
        Column {
            x: 12; y: 10; width: parent.width - 24; spacing: 8
            Row {
                width: parent.width; height: 30
                Text { width: parent.width - addBtn.width; anchors.verticalCenter: parent.verticalCenter
                       text: col.title; color: Theme.ink; elide: Text.ElideRight
                       font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                NeoButton { id: addBtn; text: "+ Nuevo"; fontSize: 12; padY: 3; padX: 8; enabled: col.canAdd; opacity: enabled ? 1 : 0.5
                            tip: col.addTip; onClicked: { col.adding = !col.adding; if (col.adding) nameIn.forceActiveFocus() } }
            }
            Column {                                // nombre en el sitio
                visible: col.adding; width: parent.width; spacing: 6
                Rectangle {
                    width: parent.width; height: 32; color: Theme.input; border.width: 1; border.color: nameIn.activeFocus ? Theme.focus : Theme.line
                    TextInput {
                        id: nameIn
                        x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter
                        color: Theme.ink; font.family: Theme.font; font.pixelSize: 14; selectByMouse: true; clip: true
                        Keys.onEscapePressed: { text = ""; col.adding = false }
                        onAccepted: okBtn.go()
                        Text { visible: !parent.text && !parent.activeFocus; text: "Nombre…"; color: Theme.ink; opacity: 0.7
                               font: parent.font; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                Row {
                    spacing: 6
                    NeoButton { visible: col.single; text: "Álbum"; fontSize: 12; padY: 3; pressedState: col.relType === "album"
                                color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                                tip: "Varias canciones"; onClicked: col.relType = "album" }
                    NeoButton { visible: col.single; text: "Single"; fontSize: 12; padY: 3; pressedState: col.relType === "single"
                                color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                                tip: "Una sola canción"; onClicked: col.relType = "single" }
                    NeoButton {
                        id: okBtn; text: "Crear"; fontSize: 12; padY: 3; color: Theme.accent; textColor: Theme.inkOnAccent
                        tip: "Crear (Intro); Esc cancela"
                        function go() {
                            if (!nameIn.text.trim()) return
                            if (root.create(col.kind, nameIn.text, col.single ? { type: col.relType } : {})) { nameIn.text = ""; col.adding = false }
                        }
                        onClicked: go()
                    }
                    NeoButton { text: "Cancelar"; fontSize: 12; padY: 3; onClicked: { nameIn.text = ""; col.adding = false } }
                }
            }
            Text { visible: !col.items.length; width: parent.width; wrapMode: Text.Wrap; text: col.empty
                   color: Theme.ink; opacity: 0.8; font.family: Theme.font; font.pixelSize: 13 }
        }
        ListView {
            id: list
            x: 6; y: 52 + (col.adding ? 76 : 0) + (!col.items.length ? 40 : 0)
            width: parent.width - 12; height: parent.height - y - 8
            clip: true; spacing: 2
            model: col.items
            delegate: Rectangle {
                id: row
                required property var modelData
                readonly property bool on: modelData.path === col.current
                width: list.width; height: 40; radius: Theme.radius
                color: on ? Theme.pressedBg : rh.hovered ? Theme.pn2 : "transparent"
                HoverHandler { id: rh }
                Column {
                    x: 10; width: parent.width - 20 - rmBtn.width; anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; elide: Text.ElideRight; text: row.modelData.name
                           color: row.on ? Theme.pressedInk : Theme.ink; font.family: Theme.font; font.pixelSize: 14; font.weight: 600 }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        text: row.modelData.kind === "release" ? (row.modelData.type === "single" ? "Single" : "Álbum") + " · " + row.modelData.year + " · " + row.modelData.songs.length + (row.modelData.songs.length === 1 ? " canción" : " canciones")
                            : row.modelData.kind === "song" ? (row.modelData.hasAfo ? "Proyecto guardado · " + row.modelData.modified : "Sin proyecto todavía: ábrela para empezar")
                            : row.modelData.releases.length + (row.modelData.releases.length === 1 ? " lanzamiento" : " lanzamientos")
                        color: row.on ? Theme.pressedInk : Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 11 }
                }
                MouseArea { anchors.fill: parent; onClicked: col.picked(row.modelData); onDoubleClicked: col.opened(row.modelData) }
                NeoButton {
                    id: rmBtn
                    anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                    visible: rh.hovered || row.on || arming
                    text: arming ? "¿Quitar?" : "Quitar"; confirm: "¿Quitar?"; fontSize: 11; padY: 2; padX: 6
                    tip: "Va a la papelera de la biblioteca (no se borra). Pulsa otra vez para confirmar"
                    onClicked: root.removeItem(row.modelData.path)
                }
            }
        }
    }

    // ---------- distribución ----------
    Column {
        x: 16; y: 14; width: parent.width - 32; spacing: 12
        Row {
            width: parent.width; spacing: 12
            Text { id: homeTitle; text: "Inicio"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 22; font.weight: 700 }
            Text { anchors.baseline: homeTitle.baseline; text: "Biblioteca: artista → álbum o single → canción. Doble clic en una canción para abrirla."
                   color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 13 }
        }
        Row {
            id: cols
            width: parent.width; spacing: 12
            height: root.height - 14 - 34 - 12 - bottom.height - 12 - 14
            Col {
                width: (cols.width - 24) / 3; height: cols.height
                title: "Artistas"; kind: "artist"; items: root.tree; current: root.artistPath
                empty: "Aún no hay artistas. Pulsa «+ Nuevo» para crear el primero."
                addTip: "Crear un artista"
                onPicked: function (it) { root.artistPath = it.path; root.releasePath = it.releases.length ? it.releases[0].path : ""; root.songPath = "" }
            }
            Col {
                width: (cols.width - 24) / 3; height: cols.height
                title: root.artist ? "Álbumes y singles de " + root.artist.name : "Álbumes y singles"
                kind: "release"; single: true; items: root.artist ? root.artist.releases : []; current: root.releasePath
                canAdd: !!root.artist
                empty: root.artist ? "Sin lanzamientos. Crea un álbum o un single." : "Elige un artista."
                addTip: "Crear un álbum o un single de este artista"
                onPicked: function (it) { root.releasePath = it.path; root.songPath = "" }
            }
            Col {
                width: (cols.width - 24) / 3; height: cols.height
                title: root.release ? "Canciones de " + root.release.name : "Canciones"
                kind: "song"; items: root.release ? root.release.songs : []; current: root.songPath
                canAdd: !!root.release && !(root.release.type === "single" && root.release.songs.length >= 1)
                empty: root.release ? "Sin canciones. Crea una y ábrela con doble clic." : "Elige un álbum o un single."
                addTip: root.release && root.release.type === "single" && root.release.songs.length ? "Un single tiene una sola canción" : "Crear una canción"
                onPicked: function (it) { root.songPath = it.path }
                onOpened: function (it) { root.openSong(it) }
            }
        }
        Rectangle {
            id: bottom
            width: parent.width; height: 118
            color: Theme.panelBody; radius: Theme.radius; border.width: 1; border.color: Theme.line
            Column {
                x: 12; y: 10; width: parent.width - 24; spacing: 8
                Row {
                    spacing: 8
                    Text { text: "Recientes"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
                           font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                    NeoButton { text: "Abrir canción"; fontSize: 12; padY: 3; enabled: !!root.song; opacity: enabled ? 1 : 0.5
                                color: Theme.accent; textColor: Theme.inkOnAccent; tip: "Abrir la canción elegida (o doble clic en ella)"
                                onClicked: root.openSong(root.song) }
                    NeoButton { text: "Proyecto suelto"; fontSize: 12; padY: 3
                                tip: "Empezar sin artista ni canción (se guarda donde elijas)"
                                onClicked: { root.pj.newLoose(); root.studio.view = "arrange" } }
                    NeoButton { text: "Abrir .afo…"; fontSize: 12; padY: 3; tip: "Abrir un proyecto de cualquier carpeta (Ctrl+O)"
                                onClicked: { if (root.pj.open("")) root.studio.view = "arrange" } }
                    NeoButton { visible: root.studio && root.studio.tracks.length > 0; text: "Volver al proyecto"; fontSize: 12; padY: 3
                                tip: "Seguir con el proyecto abierto (F5)"; onClicked: root.studio.view = "arrange" }
                }
                Flow {
                    width: parent.width; spacing: 6
                    Text { visible: !root.recent.length; text: "Todavía no has abierto ni guardado proyectos."
                           color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 13 }
                    Repeater {
                        model: root.recent
                        NeoButton {
                            required property var modelData
                            text: (modelData.artist ? modelData.artist + " · " + modelData.release + " · " : "") + modelData.name
                            fontSize: 12; padY: 3; padX: 8
                            tip: modelData.path + " · " + modelData.modified
                            onClicked: { if (root.pj.open(modelData.path)) root.studio.view = "arrange" }
                        }
                    }
                }
            }
        }
    }
}
