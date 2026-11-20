#!/usr/bin/env python3
"""Morfo Linux — tela de login.

Um greeter em GTK4 para o greetd: fala o protocolo IPC dele (JSON com
tamanho prefixado num socket UNIX). Roda dentro do `cage`, em tela cheia.

Uso pelo greetd:   cage -s -- python3 /usr/share/morfo/greeter/morfo-greeter.py
Prévia sem login:  python3 morfo-greeter.py --demo [--tema areia]
"""

import json
import os
import pwd
import socket
import struct
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

SHARE = Path(os.environ.get("MORFO_SHARE", "/usr/share/morfo"))
ESTADO = Path(os.environ.get("MORFO_ESTADO", "/var/lib/morfo"))
TEMAS = ("grafite", "areia")
NOME_TEMA = {"grafite": "Grafite", "areia": "Areia"}

SESSOES = [
    ("Claude", ["/usr/local/bin/morfo-session"]),
    ("Configurar Wi-Fi", ["/usr/local/bin/morfo-rede"]),
    ("Terminal", ["/usr/local/bin/morfo-terminal"]),
]

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


# --------------------------------------------------------------------------
# Protocolo do greetd
# --------------------------------------------------------------------------

class Greetd:
    def __init__(self, caminho: str):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(caminho)

    def pedir(self, msg: dict) -> dict:
        dados = json.dumps(msg).encode()
        self.sock.sendall(struct.pack("=I", len(dados)) + dados)
        tam = struct.unpack("=I", self._ler(4))[0]
        return json.loads(self._ler(tam))

    def _ler(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            parte = self.sock.recv(n - len(buf))
            if not parte:
                raise ConnectionError("greetd fechou a conexão")
            buf += parte
        return buf

    def entrar(self, usuario: str, senha: str, comando: list) -> str | None:
        """Devolve None em caso de sucesso ou a mensagem de erro."""
        r = self.pedir({"type": "create_session", "username": usuario})
        while r.get("type") == "auth_message":
            tipo = r.get("auth_message_type")
            resposta = senha if tipo in ("secret", "visible") else None
            r = self.pedir({"type": "post_auth_message_response", "response": resposta})
        if r.get("type") != "success":
            self.pedir({"type": "cancel_session"})
            return "Senha incorreta" if r.get("error_type") == "auth_error" else r.get("description", "Falha no login")
        r = self.pedir({"type": "start_session", "cmd": comando, "env": []})
        if r.get("type") != "success":
            return r.get("description", "Não foi possível iniciar a sessão")
        return None


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def tema_atual() -> str:
    try:
        t = (ESTADO / "tema").read_text().strip()
        return t if t in TEMAS else "areia"
    except OSError:
        return "areia"


def salvar_tema(t: str) -> None:
    try:
        ESTADO.mkdir(parents=True, exist_ok=True)
        (ESTADO / "tema").write_text(t + "\n")
    except OSError as e:
        print(f"morfo-greeter: não salvei o tema: {e}", file=sys.stderr)


def usuarios() -> list[str]:
    """Usuários comuns (UID 1000+ com shell de login)."""
    lista = [u.pw_name for u in pwd.getpwall()
             if 1000 <= u.pw_uid < 60000 and not u.pw_shell.endswith(("nologin", "false"))]
    return sorted(lista) or ["usuario"]


def ultimo_usuario() -> str | None:
    try:
        return (ESTADO / "ultimo-usuario").read_text().strip() or None
    except OSError:
        return None


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

class Greeter(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, demo: bool, tema: str):
        super().__init__(application=app, title="Morfo Linux")
        self.demo = demo
        self.tema = tema
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        overlay = Gtk.Overlay()
        self.set_child(overlay)

        self.fundo = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        overlay.set_child(self.fundo)

        raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        raiz.add_css_class("raiz")
        overlay.add_overlay(raiz)

        # Topo: marca à esquerda, botões de energia à direita.
        topo = Gtk.Box(spacing=12)
        topo.add_css_class("topo")
        # Gtk.Image com tamanho fixo: o Gtk.Picture cresce até o tamanho do arquivo.
        self.marca = Gtk.Image(pixel_size=30, valign=Gtk.Align.CENTER)
        self.marca.add_css_class("marca")
        nome = Gtk.Label(label="morfo")
        nome.add_css_class("nome")
        topo.append(self.marca)
        topo.append(nome)
        espaco = Gtk.Box(hexpand=True)
        topo.append(espaco)
        for rotulo, acao in (("Reiniciar", "reboot"), ("Desligar", "poweroff")):
            b = Gtk.Button(label=rotulo)
            b.add_css_class("energia")
            b.set_valign(Gtk.Align.CENTER)
            b.connect("clicked", self.energia, acao)
            topo.append(b)
        raiz.append(topo)

        # Centro: relógio, data e cartão de login.
        centro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER,
                         halign=Gtk.Align.CENTER, vexpand=True, spacing=6)
        self.hora = Gtk.Label()
        self.hora.add_css_class("hora")
        self.data = Gtk.Label()
        self.data.add_css_class("data")
        centro.append(self.hora)
        centro.append(self.data)

        cartao = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        cartao.add_css_class("cartao")
        cartao.set_size_request(380, -1)

        lista = usuarios()
        self.usuario = Gtk.DropDown.new_from_strings(lista)
        self.usuario.add_css_class("campo")
        ultimo = ultimo_usuario()
        if ultimo in lista:
            self.usuario.set_selected(lista.index(ultimo))
        self.lista_usuarios = lista

        self.senha = Gtk.PasswordEntry(placeholder_text="Senha", show_peek_icon=True)
        self.senha.add_css_class("campo")
        self.senha.connect("activate", self.entrar)

        self.botao = Gtk.Button(label="Entrar")
        self.botao.add_css_class("entrar")
        self.botao.connect("clicked", self.entrar)

        self.erro = Gtk.Label(label="", wrap=True, visible=False)
        self.erro.add_css_class("erro")

        cartao.append(self.usuario)
        cartao.append(self.senha)
        cartao.append(self.botao)
        cartao.append(self.erro)
        centro.append(cartao)
        raiz.append(centro)

        # Rodapé: o que abrir e o tema.
        rodape = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        rodape.add_css_class("rodape")
        self.sessao = Gtk.DropDown.new_from_strings([s[0] for s in SESSOES])
        self.sessao.add_css_class("pilula")
        self.sessao.set_tooltip_text("O que abrir depois de entrar")
        self.botao_tema = Gtk.Button()
        self.botao_tema.add_css_class("pilula")
        self.botao_tema.set_tooltip_text("Trocar o tema (vale para o boot também)")
        self.botao_tema.connect("clicked", self.trocar_tema)
        rodape.append(self.sessao)
        rodape.append(self.botao_tema)
        raiz.append(rodape)

        self.aplicar_tema(tema)
        self.relogio()
        GLib.timeout_add_seconds(1, self.relogio)
        self.senha.grab_focus()

    def mostrar_erro(self, texto: str) -> None:
        self.erro.set_label(texto)
        self.erro.set_visible(bool(texto))

    # ---- tema --------------------------------------------------------------

    def aplicar_tema(self, tema: str) -> None:
        self.tema = tema
        g = SHARE / "greeter"
        css = (g / "base.css").read_text() + (g / f"{tema}.css").read_text()
        self.css.load_from_string(css)
        pasta = SHARE / "temas" / tema
        self.fundo.set_file(Gio.File.new_for_path(str(pasta / "fundo.jpg")))
        self.marca.set_from_file(str(pasta / "logo-128.png"))
        outro = TEMAS[(TEMAS.index(tema) + 1) % len(TEMAS)]
        self.botao_tema.set_label(f"Tema {NOME_TEMA[tema]}  ·  mudar para {NOME_TEMA[outro]}")

    def trocar_tema(self, *_):
        novo = TEMAS[(TEMAS.index(self.tema) + 1) % len(TEMAS)]
        self.aplicar_tema(novo)
        if not self.demo:
            salvar_tema(novo)

    # ---- relógio -----------------------------------------------------------

    def relogio(self) -> bool:
        agora = datetime.now()
        self.hora.set_label(agora.strftime("%H:%M"))
        self.data.set_label(f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}")
        return True

    # ---- login -------------------------------------------------------------

    def entrar(self, *_):
        usuario = self.lista_usuarios[self.usuario.get_selected()]
        senha = self.senha.get_text()
        comando = SESSOES[self.sessao.get_selected()][1]
        if self.demo:
            self.mostrar_erro("Modo de demonstração: nada acontece.")
            return
        self.botao.set_sensitive(False)
        self.botao.set_label("Entrando…")
        self.mostrar_erro("")

        def trabalho():
            try:
                erro = Greetd(os.environ["GREETD_SOCK"]).entrar(usuario, senha, comando)
            except Exception as e:  # noqa: BLE001
                erro = f"Erro de comunicação com o greetd: {e}"
            GLib.idle_add(self.resultado, usuario, erro)

        threading.Thread(target=trabalho, daemon=True).start()

    def resultado(self, usuario: str, erro: str | None) -> bool:
        if erro is None:
            try:
                (ESTADO / "ultimo-usuario").write_text(usuario + "\n")
            except OSError:
                pass
            self.get_application().quit()
            return False
        self.mostrar_erro(erro)
        self.senha.set_text("")
        self.botao.set_sensitive(True)
        self.botao.set_label("Entrar")
        self.senha.grab_focus()
        return False

    def energia(self, _botao, acao: str):
        if self.demo:
            self.mostrar_erro(f"Modo de demonstração: {acao} ignorado.")
            return
        subprocess.Popen(["systemctl", acao])


def main() -> None:
    demo = "--demo" in sys.argv
    tema = tema_atual()
    if "--tema" in sys.argv:
        tema = sys.argv[sys.argv.index("--tema") + 1]
    app = Gtk.Application(application_id="org.morfolinux.Greeter", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def ativar(a):
        janela = Greeter(a, demo, tema)
        janela.fullscreen()
        janela.present()

    app.connect("activate", ativar)
    app.run([])


if __name__ == "__main__":
    main()
