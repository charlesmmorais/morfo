#!/usr/bin/env python3
"""Morfo Linux — boas-vindas do pendrive.

Primeira tela da sessão viva: instalar, conectar o Wi-Fi, experimentar o
Claude direto do pendrive e escolher o tema. Cada app abre em tela cheia
por cima desta tela (cage) e, ao fechar, volta para cá.

Prévia:  MORFO_BOASVINDAS_DEMO=1 python3 morfo-boasvindas.py
"""

import os
import shutil
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

SHARE = Path(os.environ.get("MORFO_SHARE", "/usr/share/morfo"))
ESTADO = Path(os.environ.get("MORFO_ESTADO", "/var/lib/morfo"))
DEMO = os.environ.get("MORFO_BOASVINDAS_DEMO") == "1"
TEMAS = ("grafite", "areia")
NOME = {"grafite": "Grafite", "areia": "Areia"}


def tema_salvo() -> str:
    try:
        t = (ESTADO / "tema").read_text().strip()
        return t if t in TEMAS else "areia"
    except OSError:
        return "areia"


def salvar_tema(t: str) -> None:
    """O tema escolhido aqui vai junto para o sistema instalado."""
    if DEMO:
        return
    subprocess.run(["sudo", "-n", "tee", str(ESTADO / "tema")], input=t + "\n",
                   text=True, capture_output=True)


def estado_rede() -> tuple[bool, str]:
    if DEMO:
        return True, "Conectado: Wi-Fi (Casa Morfo)"
    try:
        r = subprocess.run(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device", "status"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False, "Sem informação da rede"
    nomes = {"wifi": "Wi-Fi", "ethernet": "Cabo", "gsm": "Celular"}
    for linha in r.stdout.splitlines():
        partes = linha.split(":", 2)
        if len(partes) == 3 and partes[1] == "connected" and partes[0] in nomes:
            return True, f"Conectado: {nomes[partes[0]]} ({partes[2]})"
    return False, "Sem internet"


def ambiente_grafico() -> dict:
    env = dict(os.environ)
    env.setdefault("XDG_CURRENT_DESKTOP", "GNOME")
    return env


class BoasVindas(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Morfo Linux")
        self.app = app
        self.tema = tema_salvo()
        self.ocupado = False

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        overlay = Gtk.Overlay()
        self.set_child(overlay)
        self.fundo = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        overlay.set_child(self.fundo)

        raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        raiz.add_css_class("raiz")
        overlay.add_overlay(raiz)

        # Topo
        topo = Gtk.Box(spacing=12)
        topo.add_css_class("topo")
        # Gtk.Image com tamanho fixo: o Gtk.Picture cresce até o tamanho do arquivo.
        self.marca = Gtk.Image(pixel_size=30, valign=Gtk.Align.CENTER)
        nome = Gtk.Label(label="morfo")
        nome.add_css_class("nome")
        topo.append(self.marca)
        topo.append(nome)
        topo.append(Gtk.Box(hexpand=True))
        for rotulo, acao in (("Reiniciar", "reboot"), ("Desligar", "poweroff")):
            b = Gtk.Button(label=rotulo)
            b.add_css_class("energia")
            b.set_valign(Gtk.Align.CENTER)
            b.connect("clicked", self.energia, acao)
            topo.append(b)
        raiz.append(topo)

        # Centro
        centro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        titulo = Gtk.Label(label="Bem-vindo ao Morfo Linux")
        titulo.add_css_class("titulo-grande")
        sub = Gtk.Label(label="Um computador que começa numa conversa com o Claude.")
        sub.add_css_class("data")
        centro.append(titulo)
        centro.append(sub)

        cartoes = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER, homogeneous=True)
        cartoes.add_css_class("cartoes")
        self.btn_instalar = self.cartao(
            cartoes, "Instalar", "Coloca o Morfo neste computador. Leva uns 10 minutos e apaga o disco escolhido.",
            "Instalar o Morfo", True, self.instalar)
        self.btn_rede = self.cartao(
            cartoes, "Internet", "Conecte o Wi-Fi antes de instalar: o Claude é baixado durante a instalação.",
            "Conectar Wi-Fi", False, self.rede)
        self.btn_claude = self.cartao(
            cartoes, "Experimentar", "Use o Claude direto do pendrive, sem instalar nada. Precisa de internet.",
            "Experimentar o Claude", False, self.experimentar)
        centro.append(cartoes)

        self.status = Gtk.Label(label="", wrap=True)
        self.status.add_css_class("estado")
        centro.append(self.status)
        raiz.append(centro)

        # Rodapé
        rodape = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        rodape.add_css_class("rodape")
        self.rede_label = Gtk.Label()
        self.rede_label.add_css_class("pilula-texto")
        self.botao_tema = Gtk.Button()
        self.botao_tema.add_css_class("pilula")
        self.botao_tema.connect("clicked", self.trocar_tema)
        rodape.append(self.rede_label)
        rodape.append(self.botao_tema)
        raiz.append(rodape)

        self.aplicar_tema()
        self.atualizar_rede()
        GLib.timeout_add_seconds(3, self.atualizar_rede)

    # ---- construção ---------------------------------------------------------

    def cartao(self, pai: Gtk.Box, titulo: str, texto: str, rotulo: str, principal: bool, acao) -> Gtk.Button:
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        c.add_css_class("cartao")
        c.add_css_class("cartao-acao")
        c.set_size_request(270, -1)
        t = Gtk.Label(label=titulo, xalign=0)
        t.add_css_class("titulo")
        d = Gtk.Label(label=texto, xalign=0, wrap=True, vexpand=True, valign=Gtk.Align.START)
        d.add_css_class("estado")
        d.set_max_width_chars(30)
        b = Gtk.Button(label=rotulo)
        b.add_css_class("entrar" if principal else "secundario")
        b.connect("clicked", lambda *_: acao())
        c.append(t)
        c.append(d)
        c.append(b)
        pai.append(c)
        return b

    # ---- tema ---------------------------------------------------------------

    def aplicar_tema(self) -> None:
        g = SHARE / "greeter"
        css = ((g / "base.css").read_text() + (g / f"{self.tema}.css").read_text()
               + (SHARE / "rede" / "rede.css").read_text()
               + (SHARE / "boasvindas" / "boasvindas.css").read_text())
        self.css.load_from_string(css)
        pasta = SHARE / "temas" / self.tema
        self.fundo.set_filename(str(pasta / "fundo.jpg"))
        self.marca.set_from_file(str(pasta / "logo-128.png"))
        outro = TEMAS[(TEMAS.index(self.tema) + 1) % 2]
        self.botao_tema.set_label(f"Tema {NOME[self.tema]}  ·  mudar para {NOME[outro]}")

    def trocar_tema(self, *_):
        self.tema = TEMAS[(TEMAS.index(self.tema) + 1) % 2]
        self.aplicar_tema()
        salvar_tema(self.tema)

    # ---- rede ---------------------------------------------------------------

    def atualizar_rede(self) -> bool:
        def trabalho():
            ok, texto = estado_rede()
            GLib.idle_add(self._mostrar_rede, ok, texto)
        threading.Thread(target=trabalho, daemon=True).start()
        return True

    def _mostrar_rede(self, ok: bool, texto: str) -> bool:
        self.rede_label.set_label(("●  " if ok else "○  ") + texto)
        self.btn_rede.set_label("Trocar de rede" if ok else "Conectar Wi-Fi")
        return False

    # ---- ações --------------------------------------------------------------

    def mostrar(self, texto: str) -> bool:
        self.status.set_label(texto)
        return False

    def rodar(self, cmd: list[str], aviso: str = "") -> None:
        """Abre um app por cima desta tela e volta quando ele fechar."""
        if self.ocupado:
            return
        if DEMO:
            self.mostrar(f"Prévia: abriria {' '.join(cmd)}")
            return
        self.ocupado = True
        self.mostrar(aviso)

        def trabalho():
            try:
                subprocess.run(cmd, env=ambiente_grafico())
            finally:
                GLib.idle_add(self._livre)

        threading.Thread(target=trabalho, daemon=True).start()

    def _livre(self) -> bool:
        self.ocupado = False
        self.mostrar("")
        self.atualizar_rede()
        return False

    def instalar(self):
        self.rodar(["sudo", "--preserve-env=WAYLAND_DISPLAY,XDG_RUNTIME_DIR,DISPLAY,XDG_CURRENT_DESKTOP",
                    "env", "QT_QPA_PLATFORM=wayland;xcb", "calamares"], "Abrindo o instalador…")

    def rede(self):
        self.rodar(["python3", str(SHARE / "central" / "morfo-central.py"), "--pagina", "wifi"])

    def experimentar(self):
        if self.ocupado:
            return
        if not estado_rede()[0]:
            self.mostrar("Conecte o Wi-Fi primeiro: o Claude é baixado do site oficial da Anthropic.")
            return
        if DEMO:
            self.mostrar("Prévia: baixaria e abriria o Claude.")
            return
        if shutil.which("claude-desktop"):
            self.rodar(["claude-desktop"], "Abrindo o Claude…")
            return
        self.ocupado = True
        self.mostrar("Baixando o Claude do repositório oficial… (uns minutos, fica só na memória do pendrive)")

        def trabalho():
            r = subprocess.run(["sudo", "-n", "/usr/local/sbin/morfo-instalar-claude"],
                               capture_output=True, text=True)
            GLib.idle_add(self._depois_de_baixar, r.returncode == 0)

        threading.Thread(target=trabalho, daemon=True).start()

    def _depois_de_baixar(self, ok: bool) -> bool:
        self.ocupado = False
        if not ok:
            self.mostrar("Não consegui baixar o Claude. Confira a internet e tente de novo.")
            return False
        self.rodar(["claude-desktop"], "Abrindo o Claude…")
        return False

    def energia(self, _b, acao: str):
        if DEMO:
            self.mostrar(f"Prévia: {acao}")
            return
        subprocess.Popen(["systemctl", acao])


def main() -> None:
    app = Gtk.Application(application_id="org.morfolinux.BoasVindas")

    def ativar(a):
        j = BoasVindas(a)
        j.fullscreen()
        j.present()

    app.connect("activate", ativar)
    app.run([])


if __name__ == "__main__":
    main()
