#!/usr/bin/env python3
"""Morfo Linux — Rede.

Tela de Wi-Fi no estilo da tela de login: lista as redes, conecta com senha,
mostra a conexão atual (Wi-Fi, cabo ou celular) e volta para o login.
Usa o NetworkManager pelo `nmcli`.

Prévia sem NetworkManager:  MORFO_REDE_DEMO=1 python3 morfo-rede.py
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

SHARE = Path(os.environ.get("MORFO_SHARE", "/usr/share/morfo"))
ESTADO = Path(os.environ.get("MORFO_ESTADO", "/var/lib/morfo"))
DEMO = os.environ.get("MORFO_REDE_DEMO") == "1"

TIPOS = {"wifi": "Wi-Fi", "ethernet": "Cabo de rede", "gsm": "Celular", "bluetooth": "Bluetooth"}


# --------------------------------------------------------------------------
# NetworkManager
# --------------------------------------------------------------------------

def nmcli(*args: str, timeout: int = 40) -> tuple[int, str]:
    if DEMO:
        return demo(args)
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout if r.returncode == 0 else (r.stderr or r.stdout)).strip()
    except FileNotFoundError:
        return 1, "O NetworkManager não está instalado."
    except subprocess.TimeoutExpired:
        return 1, "A rede demorou demais para responder."


def campos(linha: str) -> list[str]:
    """Separa uma linha do modo -t do nmcli (':' separa, '\\:' é literal)."""
    out, atual, i = [], "", 0
    while i < len(linha):
        ch = linha[i]
        if ch == "\\" and i + 1 < len(linha):
            atual += linha[i + 1]
            i += 2
            continue
        if ch == ":":
            out.append(atual)
            atual = ""
        else:
            atual += ch
        i += 1
    out.append(atual)
    return out


def redes_wifi(reescanear: bool) -> list[dict]:
    cod, txt = nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                     "--rescan", "yes" if reescanear else "no")
    if cod != 0:
        return []
    vistas: dict[str, dict] = {}
    for linha in txt.splitlines():
        f = campos(linha)
        if len(f) < 4 or not f[1]:
            continue
        r = {"ativa": f[0] == "*", "ssid": f[1], "sinal": int(f[2] or 0), "segura": f[3] not in ("", "--")}
        # A mesma rede aparece uma vez por antena: fica a de sinal mais forte.
        if r["ssid"] not in vistas or r["sinal"] > vistas[r["ssid"]]["sinal"] or r["ativa"]:
            vistas[r["ssid"]] = r
    return sorted(vistas.values(), key=lambda r: (not r["ativa"], -r["sinal"]))


def conexoes_ativas() -> list[tuple[str, str]]:
    cod, txt = nmcli("-t", "-f", "TYPE,STATE,CONNECTION", "device", "status")
    if cod != 0:
        return []
    out = []
    for linha in txt.splitlines():
        f = campos(linha)
        if len(f) >= 3 and f[1] == "connected" and f[0] in TIPOS:
            out.append((TIPOS[f[0]], f[2]))
    return out


def redes_salvas() -> set[str]:
    cod, txt = nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
    if cod != 0:
        return set()
    return {campos(l)[0] for l in txt.splitlines() if l.endswith(":802-11-wireless")}


def demo(args: tuple) -> tuple[int, str]:
    if "wifi" in args and "list" in args:
        return 0, "*:Casa Morfo:82:WPA2\n:Vizinho 5G:64:WPA2 WPA3\n:Café da esquina:41:\n:NET_2G7A1B:28:WPA2\n:Escritório\\: sala 2:19:WPA2"
    if "status" in args:
        return 0, "wifi:connected:Casa Morfo\nethernet:unavailable:\nloopback:connected (externally):lo"
    if "show" in args:
        return 0, "Casa Morfo:802-11-wireless\nWired connection 1:802-3-ethernet"
    return 0, ""


def barras(sinal: int) -> str:
    n = 1 if sinal < 30 else 2 if sinal < 55 else 3 if sinal < 75 else 4
    return "▂▄▆█"[:n] + "·" * (4 - n)


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

def tema_atual() -> str:
    try:
        t = (ESTADO / "tema").read_text().strip()
        return t if t in ("grafite", "areia") else "grafite"
    except OSError:
        return "grafite"


class Rede(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Rede")
        tema = tema_atual()
        css = Gtk.CssProvider()
        g = SHARE / "greeter"
        css.load_from_string((g / "base.css").read_text() + (g / f"{tema}.css").read_text()
                             + (SHARE / "rede" / "rede.css").read_text())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        overlay = Gtk.Overlay()
        self.set_child(overlay)
        fundo = Gtk.Picture.new_for_filename(str(SHARE / "temas" / tema / "fundo.jpg"))
        fundo.set_content_fit(Gtk.ContentFit.COVER)
        fundo.set_can_shrink(True)
        overlay.set_child(fundo)

        raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        raiz.add_css_class("raiz")
        overlay.add_overlay(raiz)

        topo = Gtk.Box(spacing=12)
        topo.add_css_class("topo")
        marca = Gtk.Picture.new_for_filename(str(SHARE / "temas" / tema / "logo-128.png"))
        marca.set_size_request(30, 30)
        marca.set_can_shrink(True)
        nome = Gtk.Label(label="morfo")
        nome.add_css_class("nome")
        topo.append(marca)
        topo.append(nome)
        topo.append(Gtk.Box(hexpand=True))
        sair = Gtk.Button(label="Voltar ao login")
        sair.add_css_class("energia")
        sair.connect("clicked", lambda *_: app.quit())
        topo.append(sair)
        raiz.append(topo)

        cartao = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        cartao.add_css_class("cartao")
        cartao.set_size_request(520, -1)

        cab = Gtk.Box(spacing=10)
        titulo = Gtk.Label(label="Rede", xalign=0, hexpand=True)
        titulo.add_css_class("titulo")
        self.atualizar = Gtk.Button(label="Procurar redes")
        self.atualizar.add_css_class("pilula")
        self.atualizar.connect("clicked", lambda *_: self.carregar(True))
        cab.append(titulo)
        cab.append(self.atualizar)
        cartao.append(cab)

        self.estado = Gtk.Label(xalign=0, wrap=True)
        self.estado.add_css_class("estado")
        cartao.append(self.estado)

        rolagem = Gtk.ScrolledWindow(vexpand=True)
        rolagem.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        rolagem.set_min_content_height(320)
        rolagem.set_max_content_height(420)
        rolagem.set_propagate_natural_height(True)
        self.lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lista.add_css_class("redes")
        rolagem.set_child(self.lista)
        cartao.append(rolagem)

        self.aviso = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.aviso.add_css_class("erro")
        cartao.append(self.aviso)

        raiz.append(cartao)
        raiz.append(Gtk.Box(height_request=40))

        self.salvas: set[str] = set()
        self.carregar(False)

    # ---- dados ---------------------------------------------------------------

    def carregar(self, reescanear: bool) -> None:
        self.atualizar.set_sensitive(False)
        self.atualizar.set_label("Procurando…")

        def trabalho():
            if reescanear or not DEMO:
                nmcli("radio", "wifi", "on")
            dados = (redes_wifi(reescanear), conexoes_ativas(), redes_salvas())
            GLib.idle_add(self.mostrar, *dados)

        threading.Thread(target=trabalho, daemon=True).start()

    def mostrar(self, redes: list[dict], ativas: list[tuple[str, str]], salvas: set[str]) -> bool:
        self.salvas = salvas
        self.atualizar.set_sensitive(True)
        self.atualizar.set_label("Procurar redes")
        if ativas:
            self.estado.set_label("Conectado: " + "  ·  ".join(f"{t} ({n})" for t, n in ativas))
        else:
            self.estado.set_label("Sem conexão. Escolha uma rede Wi-Fi abaixo.")

        while (filho := self.lista.get_first_child()) is not None:
            self.lista.remove(filho)
        if not redes:
            vazio = Gtk.Label(label="Nenhuma rede Wi-Fi encontrada.\nSe a placa de Wi-Fi for Broadcom, o driver "
                                    "pode estar faltando: conecte um cabo e rode o setup de novo.",
                              wrap=True, xalign=0)
            vazio.add_css_class("estado")
            self.lista.append(vazio)
        for r in redes:
            self.lista.append(self.linha(r))
        return False

    def linha(self, r: dict) -> Gtk.Widget:
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        caixa.add_css_class("rede")
        if r["ativa"]:
            caixa.add_css_class("ativa")

        topo = Gtk.Box(spacing=12)
        sinal = Gtk.Label(label=barras(r["sinal"]))
        sinal.add_css_class("sinal")
        nome = Gtk.Label(label=r["ssid"], xalign=0, hexpand=True, ellipsize=3)
        nome.add_css_class("ssid")
        detalhe = "conectada" if r["ativa"] else ("salva" if r["ssid"] in self.salvas else
                                                  ("protegida" if r["segura"] else "aberta"))
        info = Gtk.Label(label=("🔒 " if r["segura"] else "") + detalhe)
        info.add_css_class("info")
        topo.append(sinal)
        topo.append(nome)
        topo.append(info)
        caixa.append(topo)

        # Área que abre ao tocar: senha e botões.
        # Na prévia, uma rede já aparece aberta para mostrar o campo de senha.
        acoes = Gtk.Box(spacing=10, visible=DEMO and r["ssid"] == "Vizinho 5G")
        senha = Gtk.PasswordEntry(placeholder_text="Senha da rede", show_peek_icon=True, hexpand=True)
        senha.add_css_class("campo")
        conectar = Gtk.Button(label="Desconectar" if r["ativa"] else "Conectar")
        conectar.add_css_class("entrar")
        if r["segura"] and not r["ativa"] and r["ssid"] not in self.salvas:
            acoes.append(senha)
        else:
            acoes.append(Gtk.Box(hexpand=True))
        if r["ssid"] in self.salvas and not r["ativa"]:
            esquecer = Gtk.Button(label="Esquecer")
            esquecer.add_css_class("pilula")
            esquecer.connect("clicked", lambda *_: self.executar(
                ("connection", "delete", "id", r["ssid"]), f"{r['ssid']} esquecida."))
            acoes.append(esquecer)
        acoes.append(conectar)
        caixa.append(acoes)

        def agir(*_):
            if r["ativa"]:
                self.executar(("connection", "down", "id", r["ssid"]), "Desconectado.")
            elif r["ssid"] in self.salvas:
                self.executar(("connection", "up", "id", r["ssid"]), f"Conectado a {r['ssid']}.")
            else:
                cmd = ["device", "wifi", "connect", r["ssid"]]
                if r["segura"]:
                    if not senha.get_text():
                        self.mostrar_aviso("Digite a senha da rede.")
                        senha.grab_focus()
                        return
                    cmd += ["password", senha.get_text()]
                self.executar(tuple(cmd), f"Conectado a {r['ssid']}.")

        conectar.connect("clicked", agir)
        senha.connect("activate", agir)

        clique = Gtk.GestureClick()
        clique.connect("released", lambda *_: (acoes.set_visible(not acoes.get_visible()),
                                               senha.grab_focus() if acoes.get_visible() else None))
        topo.add_controller(clique)
        return caixa

    def executar(self, args: tuple, sucesso: str) -> None:
        self.mostrar_aviso("Aguarde…", erro=False)

        def trabalho():
            cod, txt = nmcli(*args, timeout=60)
            msg = sucesso if cod == 0 else traduzir(txt)
            GLib.idle_add(self.mostrar_aviso, msg, cod != 0)
            GLib.idle_add(self.carregar, False)

        threading.Thread(target=trabalho, daemon=True).start()

    def mostrar_aviso(self, texto: str, erro: bool = True) -> bool:
        self.aviso.set_label(texto)
        self.aviso.set_visible(bool(texto))
        if erro:
            self.aviso.remove_css_class("ok")
        else:
            self.aviso.add_css_class("ok")
        return False


def traduzir(txt: str) -> str:
    t = txt.lower()
    if "secrets were required" in t or "password" in t or "802-1x" in t:
        return "Senha incorreta. Confira e tente de novo."
    if "no network with ssid" in t:
        return "A rede saiu do alcance. Toque em Procurar redes."
    if "not authorized" in t:
        return "Sem permissão para mudar a rede (o usuário precisa estar no grupo netdev)."
    return txt.splitlines()[-1] if txt else "Não foi possível conectar."


def main() -> None:
    app = Gtk.Application(application_id="org.morfolinux.Rede")

    def ativar(a):
        j = Rede(a)
        j.fullscreen()
        j.present()

    app.connect("activate", ativar)
    app.run([])


if __name__ == "__main__":
    sys.exit(main())
