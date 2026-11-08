import QtQuick

// Cuerpo de un módulo que todavía no se ha pasado a la interfaz nativa. Lo dice tal cual:
// nada de controles decorativos que aparenten funcionar.
Column {
    id: root
    property int phase: 1
    property string summary: ""
    width: parent ? parent.width : 300
    spacing: 8
    DashedBox {
        width: root.width
        text: "<b>Todavía no está en la interfaz nativa</b> (llega en la fase " + root.phase + ").<br>" +
              root.summary + "<br>Mientras tanto úsalo en la interfaz actual: abre AllForOne sin <i>--nativo</i>."
        textFormat: Text.StyledText
    }
}
