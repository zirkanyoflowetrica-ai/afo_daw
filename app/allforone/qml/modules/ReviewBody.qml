import QtQuick
import "../theme"
import "../controls"
import "../state/fxgraph.js" as FG

// Módulo Antes / Después (A/B Comp): dos pantallas en vivo, la señal que ENTRA a una cadena de efectos
// y la que SALE, tomadas del audio que suena (sin archivos). Se conecta a cualquier rack: el canal
// elegido en Mezcla o el master. Escucha A/B: puentea toda la cadena y la restablece como estaba.
Column {
    id: root
    property var mixer
    property var studio
    property bool shown: true
    property string src: "rack"                 // "rack" (canal de Efectos) o "master"
    readonly property int tid: src === "master" ? 0 : studio.rackTrack
    property var scope: null                    // {pre, post, pre_db, post_db, active}
    property var saved: null                    // estados de la cadena antes de escuchar A
    width: parent ? parent.width : 380
    spacing: 0

    readonly property string srcName: {
        if (src === "master") return "Master"
        for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === studio.rackTrack) return studio.tracks[i].name
        return "sin canal"
    }
    onTidChanged: { restore(); scope = null }

    function f(v) { return v !== undefined && v > -99 ? v.toFixed(1) : "—" }
    function listenA() {                        // A: toda la cadena puenteada
        if (tid < 0 || saved) return
        var r = studio.call("fxList", tid)
        if (!r.ok || !r.chain.length) { studio.toast("Esa cadena no tiene efectos"); return }
        saved = { tid: tid, chain: r.chain.map(function (e) { return [e.id, e.enabled] }) }
        r.chain.forEach(function (e) { studio.call("fxEnable", e.id, false) })
        studio.refreshRacks()
    }
    function restore() {                        // B: cada efecto vuelve a como estaba
        if (!saved) return
        saved.chain.forEach(function (p) { studio.call("fxEnable", p[0], p[1]) })
        saved = null
        studio.refreshRacks()
    }

    Timer {                                     // ~10 tomas por segundo mientras suena
        interval: 100; repeat: true
        running: root.shown && root.studio.engineOk && root.studio.playing && root.tid >= 0
        onTriggered: { var r = root.studio.call("chainScope", root.tid, 64); if (r.ok) root.scope = r }
    }

    Row {
        width: root.width; spacing: 6; bottomPadding: 8
        Text { text: "Conectado a"; height: 26; verticalAlignment: Text.AlignVCenter; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
        Repeater {
            model: [["rack", "Rack del canal"], ["master", "Master"]]
            NeoButton {
                required property var modelData
                readonly property bool on: root.src === modelData[0]
                text: modelData[1]; fontSize: 11; padX: 8; padY: 2; shadow: 2
                color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                onClicked: root.src = modelData[0]
            }
        }
    }
    Text {
        width: root.width; bottomPadding: 8; elide: Text.ElideRight
        text: root.srcName.toUpperCase() + " · " + (root.scope ? root.scope.active + " efectos activos" : "reproduce para ver la señal")
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
    }
    Row {                                       // las dos pantallas juntas
        width: root.width; spacing: 6
        Repeater {
            model: [["ANTES", "pre", "pre_db", "#ffcf9e", "rgba(255,207,158,0.30)"], ["DESPUÉS", "post", "post_db", "#5ee0b0", "rgba(94,224,176,0.30)"]]
            Rectangle {
                id: scr
                required property var modelData
                width: (root.width - 6) / 2; height: 150
                color: "#16130e"; border.width: 3; border.color: "#000"
                Canvas {
                    x: 3; y: 22; width: parent.width - 6; height: parent.height - 25
                    property var bands: root.scope ? root.scope[scr.modelData[1]] : []
                    onBandsChanged: requestPaint()
                    onPaint: FG.spectrum(getContext("2d"), width, height, bands, scr.modelData[3], scr.modelData[4])
                }
                Text { x: 8; y: 4; text: scr.modelData[0]; color: scr.modelData[3]
                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                Text { anchors.right: parent.right; anchors.rightMargin: 8; y: 4
                       text: root.f(root.scope ? root.scope[scr.modelData[2]] : undefined) + " dB RMS"
                       color: "#ffb000"; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
            }
        }
    }
    Text {
        width: root.width; topPadding: 6; wrapMode: Text.Wrap
        readonly property real d: root.scope && root.scope.pre_db > -99 && root.scope.post_db > -99 ? root.scope.post_db - root.scope.pre_db : NaN
        text: isNaN(d) ? "Espectro de 20 Hz a 20 kHz (dBFS) a la entrada del primer efecto activo y a la salida del último."
                       : "La cadena cambia el nivel " + (d >= 0 ? "+" : "") + d.toFixed(1) + " dB. Espectro de 20 Hz a 20 kHz a la entrada del primer efecto activo y a la salida del último."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
    }
    Row {                                       // .afo-ab
        width: root.width; spacing: 6; topPadding: 8; bottomPadding: 8 + 3
        NeoButton { width: (root.width - 6) / 2 - 1; text: "A · sin la cadena"; fontWeight: 700
                    readonly property bool on: !!root.saved
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    tip: "Escucha sin efectos (todos puenteados)"; onClicked: root.listenA() }
        NeoButton { width: (root.width - 6) / 2 - 1; text: "B · con la cadena"; fontWeight: 700
                    readonly property bool on: !root.saved
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    tip: "Cada efecto vuelve a como estaba"; onClicked: root.restore() }
    }
}
