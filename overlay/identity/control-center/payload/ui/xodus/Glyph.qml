import QtQuick

// Original line glyphs for the Xodus control surface.
Canvas {
    id: glyph
    property string symbol: "controls"
    property color ink: "#f5f3fa"
    implicitWidth: 24
    implicitHeight: 24
    onSymbolChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        const p = getContext("2d")
        p.reset()
        p.scale(width / 24, height / 24)
        p.strokeStyle = ink
        p.fillStyle = ink
        p.lineWidth = 1.8
        p.lineCap = "round"
        p.lineJoin = "round"
        function line(a, b, c, d) { p.beginPath(); p.moveTo(a,b); p.lineTo(c,d); p.stroke() }
        function ring(x,y,r) { p.beginPath(); p.arc(x,y,r,0,2*Math.PI); p.stroke() }
        if (symbol === "wifi") {
            for (let r of [4, 8, 12]) { p.beginPath(); p.arc(12,20,r,Math.PI*1.23,Math.PI*1.77); p.stroke() }
            p.beginPath(); p.arc(12,20,1.2,0,Math.PI*2); p.fill()
        } else if (symbol === "bluetooth") {
            line(11,2,11,22); line(11,2,18,8); line(18,8,5,18); line(5,6,18,16); line(18,16,11,22)
        } else if (symbol === "brightness") {
            ring(12,12,4)
            for (let i=0; i<8; ++i) { let a=i*Math.PI/4; line(12+7*Math.cos(a),12+7*Math.sin(a),12+10*Math.cos(a),12+10*Math.sin(a)) }
        } else if (symbol === "volume") {
            p.beginPath(); p.moveTo(3,9); p.lineTo(7,9); p.lineTo(12,5); p.lineTo(12,19); p.lineTo(7,15); p.lineTo(3,15); p.closePath(); p.stroke()
            for (let r of [5,8]) { p.beginPath(); p.arc(12,12,r,-0.75,0.75); p.stroke() }
        } else if (symbol === "pause") {
            p.fillRect(7,5,3,14); p.fillRect(14,5,3,14)
        } else if (symbol === "play" || symbol === "next" || symbol === "previous") {
            const previous = symbol === "previous"
            p.beginPath(); p.moveTo(previous ? 17 : 7,5); p.lineTo(previous ? 6 : 18,12); p.lineTo(previous ? 17 : 7,19); p.closePath(); p.fill()
            if (symbol !== "play") line(previous ? 5 : 19,5,previous ? 5 : 19,19)
        } else if (symbol === "power") {
            line(12,2,12,11); p.beginPath(); p.arc(12,13,8,-0.95,Math.PI*2-2.2); p.stroke()
        } else if (symbol === "close") {
            line(6,6,18,18); line(18,6,6,18)
        } else if (symbol === "arrow") {
            line(9,6,15,12); line(15,12,9,18)
        } else if (symbol === "focus") {
            ring(12,12,8); line(7,12,17,12)
        } else if (symbol === "night") {
            p.beginPath(); p.arc(12,12,8,0.3,5); p.quadraticCurveTo(6,12,20,14); p.stroke()
        } else if (symbol === "theme") {
            ring(12,12,9); p.beginPath(); p.arc(12,12,7,Math.PI/2,Math.PI*1.5); p.fill()
        } else if (symbol === "devices") {
            p.strokeRect(7,2,10,20); line(10,18,14,18)
        } else if (symbol === "screenshot") {
            line(3,8,3,3); line(3,3,8,3); line(16,3,21,3); line(21,3,21,8)
            line(21,16,21,21); line(21,21,16,21); line(8,21,3,21); line(3,21,3,16)
            p.strokeRect(7,7,10,10)
        } else if (symbol === "music") {
            line(10,17,10,5); line(10,5,20,3); line(20,3,20,15); ring(6.5,18,3.5); ring(16.5,16,3.5)
        } else {
            line(3,7,21,7); line(3,17,21,17); ring(8,7,3); ring(16,17,3)
        }
    }
}
