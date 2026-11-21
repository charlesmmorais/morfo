#!/usr/bin/env python3
"""Morfo Linux — barra do topo.

Logo, data e hora, Wi-Fi, Bluetooth, volume e energia, por cima do Claude.
Dois modos, escolhidos na Central (Aparência) e gravados em /var/lib/morfo/barra:
  auto  — escondida; aparece quando o mouse encosta no topo (padrão)
  fixa  — sempre visível; o Claude ocupa o espaço abaixo dela

Usa o gtk4-layer-shell (painel do sway). Sem ele, abre como janela comum,
o que serve para prévia:  MORFO_BARRA_DEMO=1 python3 morfo-barra.py
"""

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as Camada  # noqa: E402
except (ValueError, ImportError):
    Camada = None
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

SHARE = Path(os.environ.get("MORFO_SHARE", "/usr/share/morfo"))
ESTADO = Path(os.environ.get("MORFO_ESTADO", "/var/lib/morfo"))
DEMO = os.environ.get("MORFO_BARRA_DEMO") == "1"
ALTURA = 34
VISIVEL_ESCONDIDA = 2  # faixa que fica na tela para o mouse "encostar"

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rodar(*cmd: str, timeout: int = 5) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""


def ler(arquivo: str, padrao: str) -> str:
    try:
        return (ESTADO / arquivo).read_text().strip() or padrao
    except OSError:
        return padrao


def abrir(*cmd: str) -> None:
    if DEMO:
        print("abriria:", " ".join(cmd))
        return
    subprocess.Popen(cmd, start_new_session=True)


def estado_sistema() -> dict:
    """Wi-Fi, Bluetooth e volume. Roda fora da interface."""
    if DEMO:
        return {"wifi": "Casa Morfo", "sinal": 80, "cabo": False, "bt": True, "bt_conectado": "Fone Morfo",
                "volume": 62, "mudo": False}
    e = {"wifi": "", "sinal": 0, "cabo": False, "bt": False, "bt_conectado": "", "volume": 0, "mudo": False}
    cod, txt = rodar("nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device", "status")
    for linha in txt.splitlines() if cod == 0 else []:
        partes = linha.split(":")
        if len(partes) >= 3 and partes[1] == "connected":
            if partes[0] == "wifi":
                e["wifi"] = ":".join(partes[2:]).replace("\\:", ":")
            elif partes[0] == "ethernet":
                e["cabo"] = True
    if e["wifi"]:
        _, txt = rodar("nmcli", "-t", "-f", "IN-USE,SIGNAL", "device", "wifi", "list", "--rescan", "no")
        for linha in txt.splitlines():
            if linha.startswith("*:"):
                try:
                    e["sinal"] = int(linha.split(":")[1])
                except ValueError:
                    pass
    cod, show = rodar("bluetoothctl", "show")
    e["bt"] = cod == 0 and "Powered: yes" in show
    if e["bt"]:
        _, txt = rodar("bluetoothctl", "devices", "Connected")
        m = re.search(r"Device \S+ (.+)", txt)
        e["bt_conectado"] = m.group(1) if m else ""
    _, vol = rodar("pactl", "get-sink-volume", "@DEFAULT_SINK@")
    m = re.search(r"(\d+)%", vol)
    e["volume"] = int(m.group(1)) if m else 0
    _, mudo = rodar("pactl", "get-sink-mute", "@DEFAULT_SINK@")
    e["mudo"] = "yes" in mudo
    return e


_tema_icones = "areia"


def arquivo_icone(nome: str) -> str:
    """Ícones desenhados do Morfo, já pintados para cada tema (PNG 2x)."""
    return str(SHARE / "barra" / "icones" / _tema_icones / f"{nome}.png")


def icone(nome: str) -> Gtk.Image:
    img = Gtk.Image.new_from_file(arquivo_icone(nome))
    img.set_pixel_size(16)
    return img


def trocar_icone(img: Gtk.Image, nome: str) -> None:
    img.set_from_file(arquivo_icone(nome))


class Barra(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Barra do Morfo")
        self.add_css_class("barra-janela")
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.tema = ""
        self.modo = ""
        self.visivel = True
        self._esconder_id = 0
        self.popovers: list[Gtk.Popover] = []
        self.carregar_tema()

        if Camada is not None and Camada.is_supported():
            Camada.init_for_window(self)
            Camada.set_namespace(self, "morfo-barra")
            Camada.set_layer(self, Camada.Layer.TOP)
            for borda in (Camada.Edge.TOP, Camada.Edge.LEFT, Camada.Edge.RIGHT):
                Camada.set_anchor(self, borda, True)
            Camada.set_keyboard_mode(self, Camada.KeyboardMode.ON_DEMAND)
        elif DEMO:
            self.set_default_size(1280, ALTURA)
        else:
            # Sem painel de verdade a barra viraria uma janela solta no quiosque.
            raise SystemExit("morfo-barra: gtk4-layer-shell indisponível")
        self.set_size_request(-1, ALTURA)

        self.caixa = Gtk.CenterBox()
        self.caixa.add_css_class("barra")
        self.set_child(self.caixa)
        self.montar()

        movimento = Gtk.EventControllerMotion()
        movimento.connect("enter", lambda *_: self.mostrar())
        movimento.connect("leave", lambda *_: self.agendar_esconder())
        self.add_controller(movimento)

        self.aplicar_modo(ler("barra", "auto"))
        self.atualizar_hora()
        GLib.timeout_add_seconds(15, self.atualizar_hora)
        self.atualizar_estado()
        GLib.timeout_add_seconds(5, self.atualizar_estado)
        GLib.timeout_add_seconds(2, self.vigiar_preferencias)

    # ---- aparência --------------------------------------------------------

    def carregar_tema(self) -> None:
        tema = ler("tema", "areia")
        tema = tema if tema in ("areia", "grafite") else "areia"
        if tema == self.tema:
            return
        self.tema = tema
        global _tema_icones
        _tema_icones = tema
        g = SHARE / "greeter"
        self.css.load_from_string((g / f"{tema}.css").read_text()
                                  + (SHARE / "barra" / "barra.css").read_text())

    def montar(self) -> None:
        self.popovers = []
        esq = Gtk.Box(spacing=8)
        logo = Gtk.Image.new_from_file(str(SHARE / "temas" / self.tema / "logo-128.png"))
        logo.set_pixel_size(18)
        nome = Gtk.Label(label="Morfo")
        nome.add_css_class("marca")
        botao_logo = Gtk.Button()
        caixa_logo = Gtk.Box(spacing=8)
        caixa_logo.append(logo)
        caixa_logo.append(nome)
        botao_logo.set_child(caixa_logo)
        botao_logo.add_css_class("item")
        botao_logo.set_tooltip_text("Central do Morfo (Super + Espaço)")
        botao_logo.connect("clicked", lambda *_: abrir("/usr/local/bin/morfo-central"))
        esq.append(botao_logo)
        self.caixa.set_start_widget(esq)

        self.hora = Gtk.Label()
        self.hora.add_css_class("hora")
        self.caixa.set_center_widget(self.hora)

        dir_ = Gtk.Box(spacing=2)
        self.btn_wifi = self.item("wifi-3", "",
                                  lambda: abrir("/usr/local/bin/morfo-central", "--pagina", "wifi"))
        self.btn_bt = self.item("bt", "",
                                lambda: abrir("/usr/local/bin/morfo-central", "--pagina", "bluetooth"))
        self.btn_som = self.item_popover("som-3", self.painel_som())
        self.btn_energia = self.item_popover("energia", self.painel_energia())
        for b in (self.btn_wifi, self.btn_bt, self.btn_som, self.btn_energia):
            dir_.append(b)
        self.caixa.set_end_widget(dir_)

    def item(self, icone_nome: str, texto: str, acao) -> Gtk.Button:
        b = Gtk.Button()
        b.add_css_class("item")
        conteudo = Gtk.Box(spacing=6)
        conteudo.append(icone(icone_nome))
        rot = Gtk.Label(label=texto, visible=bool(texto))
        rot.add_css_class("rotulo")
        conteudo.append(rot)
        b.set_child(conteudo)
        b.icone = conteudo.get_first_child()
        b.rotulo = rot
        b.connect("clicked", lambda *_: acao())
        return b

    def item_popover(self, icone_nome: str, painel: Gtk.Widget) -> Gtk.MenuButton:
        b = Gtk.MenuButton()
        b.add_css_class("item")
        conteudo = Gtk.Box(spacing=6)
        conteudo.append(icone(icone_nome))
        rot = Gtk.Label(visible=False)
        rot.add_css_class("rotulo")
        conteudo.append(rot)
        b.set_child(conteudo)
        b.icone = conteudo.get_first_child()
        b.rotulo = rot
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("painel")
        pop.set_child(painel)
        pop.connect("closed", lambda *_: self.agendar_esconder())
        b.set_popover(pop)
        self.popovers.append(pop)
        return b

    def painel_som(self) -> Gtk.Widget:
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        titulo = Gtk.Label(label="Som", xalign=0)
        titulo.add_css_class("titulo-painel")
        caixa.append(titulo)
        linha = Gtk.Box(spacing=10)
        self.mudo = Gtk.ToggleButton()
        self.mudo.set_child(icone("som-3"))
        self.mudo.add_css_class("redondo")
        self.mudo.set_tooltip_text("Mudo")
        self.mudo.connect("toggled", self.mudar_mudo)
        self.escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.escala.set_draw_value(False)
        self.escala.set_size_request(220, -1)
        self.escala.set_hexpand(True)
        self.escala.connect("value-changed", self.mudar_volume)
        linha.append(self.mudo)
        linha.append(self.escala)
        caixa.append(linha)
        mais = Gtk.Button(label="Saídas e mais opções…")
        mais.add_css_class("link")
        mais.connect("clicked", lambda *_: (self.fechar_popovers(),
                                            abrir("/usr/local/bin/morfo-central", "--pagina", "som")))
        caixa.append(mais)
        self._ignorar = False
        self._volume_id = 0
        return caixa

    def painel_energia(self) -> Gtk.Widget:
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        opcoes = [
            ("Central do Morfo…", lambda: abrir("/usr/local/bin/morfo-central")),
            ("Sair para o login", lambda: abrir("swaymsg", "exit")),
            (None, None),
            ("Reiniciar", lambda: abrir("systemctl", "reboot")),
            ("Desligar", lambda: abrir("systemctl", "poweroff")),
        ]
        for rotulo, acao in opcoes:
            if rotulo is None:
                caixa.append(Gtk.Separator())
                continue
            b = Gtk.Button(label=rotulo)
            b.add_css_class("opcao")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda *_, a=acao: (self.fechar_popovers(), a()))
            caixa.append(b)
        return caixa

    # ---- estado -----------------------------------------------------------

    def atualizar_hora(self) -> bool:
        agora = datetime.now()
        self.hora.set_label(f"{DIAS[agora.weekday()]} {agora.day} de {MESES[agora.month - 1]}   {agora:%H:%M}")
        return True

    def atualizar_estado(self) -> bool:
        def trabalho():
            e = estado_sistema()
            GLib.idle_add(self.mostrar_estado, e)
        threading.Thread(target=trabalho, daemon=True).start()
        return True

    def mostrar_estado(self, e: dict) -> bool:
        if e["cabo"]:
            nome, texto, dica = "cabo", "", "Conectado por cabo"
        elif e["wifi"]:
            nivel = 3 if e["sinal"] >= 67 else 2 if e["sinal"] >= 34 else 1
            nome, texto, dica = f"wifi-{nivel}", e["wifi"], f"Wi-Fi: {e['wifi']}"
        else:
            nome, texto, dica = "wifi-off", "Sem internet", "Sem conexão. Clique para escolher uma rede."
        trocar_icone(self.btn_wifi.icone, nome)
        self.btn_wifi.rotulo.set_label(texto)
        self.btn_wifi.rotulo.set_visible(bool(texto))
        self.btn_wifi.set_tooltip_text(dica)

        trocar_icone(self.btn_bt.icone, "bt" if e["bt"] else "bt-off")
        self.btn_bt.set_tooltip_text(f"Bluetooth: {e['bt_conectado']}" if e["bt_conectado"]
                                     else "Bluetooth ligado" if e["bt"] else "Bluetooth desligado")

        v = e["volume"]
        som = "som-0" if e["mudo"] or v == 0 else "som-1" if v < 34 else "som-2" if v < 67 else "som-3"
        trocar_icone(self.btn_som.icone, som)
        self.btn_som.set_tooltip_text("Mudo" if e["mudo"] else f"Volume {v}%")
        if not self.btn_som.get_active():  # não briga com o dedo no controle
            self._ignorar = True
            self.escala.set_value(min(v, 100))
            self.mudo.set_active(e["mudo"])
            self.mudo.set_child(icone(som))
            self._ignorar = False
        return False

    def mudar_volume(self, escala) -> None:
        if self._ignorar:
            return
        if self._volume_id:
            GLib.source_remove(self._volume_id)
        self._volume_id = GLib.timeout_add(80, self._aplicar_volume, int(escala.get_value()))

    def _aplicar_volume(self, v: int) -> bool:
        self._volume_id = 0
        if not DEMO:
            rodar("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%")
        return False

    def mudar_mudo(self, botao) -> None:
        if not self._ignorar and not DEMO:
            rodar("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if botao.get_active() else "0")

    def fechar_popovers(self) -> None:
        for p in self.popovers:
            p.popdown()

    # ---- modo fixo / automático --------------------------------------------

    def vigiar_preferencias(self) -> bool:
        modo = ler("barra", "auto")
        if modo != self.modo:
            self.aplicar_modo(modo)
        tema_antes = self.tema
        self.carregar_tema()
        if self.tema != tema_antes:
            self.montar()
            self.atualizar_estado()
            self.atualizar_hora()
        return True

    def aplicar_modo(self, modo: str) -> None:
        self.modo = "fixa" if modo == "fixa" else "auto"
        if self.modo == "fixa":
            if Camada is not None and Camada.is_layer_window(self):
                Camada.set_exclusive_zone(self, ALTURA)
            self.mostrar()
        else:
            if Camada is not None and Camada.is_layer_window(self):
                Camada.set_exclusive_zone(self, 0)
            self.agendar_esconder(1500)

    def mostrar(self) -> None:
        if self._esconder_id:
            GLib.source_remove(self._esconder_id)
            self._esconder_id = 0
        if self.visivel:
            return
        self.visivel = True
        self.caixa.remove_css_class("escondida")
        if Camada is not None and Camada.is_layer_window(self):
            Camada.set_margin(self, Camada.Edge.TOP, 0)

    def agendar_esconder(self, atraso: int = 700) -> None:
        if self.modo != "auto":
            return
        if self._esconder_id:
            GLib.source_remove(self._esconder_id)
        self._esconder_id = GLib.timeout_add(atraso, self._esconder)

    def _esconder(self) -> bool:
        self._esconder_id = 0
        if self.modo != "auto" or any(p.get_visible() for p in self.popovers):
            return False
        self.visivel = False
        self.caixa.add_css_class("escondida")
        if Camada is not None and Camada.is_layer_window(self):
            # Sobe a barra para fora da tela e deixa só uma faixa fininha,
            # onde o mouse "encosta" para trazê-la de volta.
            Camada.set_margin(self, Camada.Edge.TOP, -(ALTURA - VISIVEL_ESCONDIDA))
        return False


def main() -> None:
    app = Gtk.Application(application_id="org.morfolinux.Barra")
    app.connect("activate", lambda a: a.get_windows() or Barra(a).present())
    app.run([])


if __name__ == "__main__":
    main()
