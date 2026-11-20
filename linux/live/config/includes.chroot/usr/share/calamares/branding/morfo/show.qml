/* Morfo Linux — apresentação durante a instalação (Calamares, API 2). */
import QtQuick 2.15
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 8000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    function onActivate() { presentation.currentSlide = 0; }
    function onLeave() { }

    component MorfoSlide: Slide {
        id: slide
        property string titulo: ""
        property string texto: ""

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#101218" }
                GradientStop { position: 1.0; color: "#1C2338" }
            }
        }
        Column {
            anchors.centerIn: parent
            width: parent.width * 0.7
            spacing: 18
            Image {
                source: "logo.png"
                width: 72; height: 72
                fillMode: Image.PreserveAspectFit
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: slide.titulo
                color: "#E6E9F0"
                font.family: "Inter"
                font.pixelSize: 30
                font.weight: Font.Light
                horizontalAlignment: Text.AlignHCenter
                width: parent.width
                wrapMode: Text.WordWrap
            }
            Text {
                text: slide.texto
                color: "#8C93A5"
                font.family: "Inter"
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
                width: parent.width
                wrapMode: Text.WordWrap
                lineHeight: 1.3
            }
        }
    }

    MorfoSlide {
        titulo: "Um computador que começa numa conversa"
        texto: "Ao ligar, o Morfo vai direto para o Claude, em tela cheia. Sem área de trabalho, sem distrações."
    }
    MorfoSlide {
        titulo: "Grafite ou Areia"
        texto: "Troque o tema na tela de login, com um toque. Ele vale para o boot, o login e o terminal."
    }
    MorfoSlide {
        titulo: "Wi-Fi, som e Cowork prontos"
        texto: "Use \"Configurar Wi-Fi\" na tela de login. O Cowork já vem com a virtualização configurada."
    }
    MorfoSlide {
        titulo: "O Claude vem do site oficial"
        texto: "O instalador baixa o Claude Desktop direto da Anthropic. Sem internet agora? Ele termina sozinho quando você conectar."
    }
    MorfoSlide {
        titulo: "Vida nova para computadores antigos"
        texto: "O Morfo foi feito para máquinas como o Mac mini 2011: leve, bonito e focado no que importa."
    }
}
