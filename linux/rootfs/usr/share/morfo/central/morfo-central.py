#!/usr/bin/env python3
"""Morfo Linux — Central do Morfo.

Abre por cima de qualquer app com Super+Espaço (e fecha com Esc ou com o
mesmo atalho). Reúne Wi-Fi, Bluetooth, Som, Aparência e Sistema.

Prévia sem hardware:  MORFO_CENTRAL_DEMO=1 python3 morfo-central.py [--pagina som]
"""

import importlib.util
import json
import os
import re
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
DEMO = os.environ.get("MORFO_CENTRAL_DEMO") == "1"
if DEMO:
    os.environ["MORFO_REDE_DEMO"] = "1"

TEMAS = {"areia": "Areia", "grafite": "Grafite"}
TECLADOS = [
    ("br abnt2 -", "ABNT2", "Teclado brasileiro, com Ç"),
    ("us pc105 intl", "US Internacional", "Acentos com ' ~ ^ antes da letra"),
    ("us pc105 -", "US", "Teclado americano, sem acentos"),
]


def rodar(*cmd: str, timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or r.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]} não está instalado"
    except subprocess.TimeoutExpired:
        return 124, "demorou demais"


def em_segundo_plano(trabalho, depois) -> None:
    """Roda `trabalho` fora da interface e entrega o resultado a `depois`."""
    def alvo():
        resultado = trabalho()
        GLib.idle_add(lambda: (depois(resultado), False)[1])
    threading.Thread(target=alvo, daemon=True).start()


def carregar_rede():
    spec = importlib.util.spec_from_file_location("morfo_rede", SHARE / "rede" / "morfo-rede.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tema_atual() -> str:
    try:
        t = (ESTADO / "tema").read_text().strip()
        return t if t in TEMAS else "areia"
    except OSError:
        return "areia"


def gravar(arquivo: str, texto: str) -> bool:
    try:
        (ESTADO / arquivo).write_text(texto + "\n")
        return True
    except OSError:
        return False


def titulo_pagina(texto: str, sub: str = "") -> Gtk.Widget:
    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    t = Gtk.Label(label=texto, xalign=0)
    t.add_css_class("titulo")
    caixa.append(t)
    if sub:
        s = Gtk.Label(label=sub, xalign=0, wrap=True)
        s.add_css_class("estado")
        caixa.append(s)
    return caixa


def linha_item(titulo: str, detalhe: str = "", ativo: bool = False) -> tuple[Gtk.Box, Gtk.Box]:
    """Uma linha no estilo das redes Wi-Fi; devolve (linha, área de botões)."""
    caixa = Gtk.Box(spacing=12)
    caixa.add_css_class("rede")
    if ativo:
        caixa.add_css_class("ativa")
    textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    n = Gtk.Label(label=titulo, xalign=0, ellipsize=3)
    n.add_css_class("ssid")
    textos.append(n)
    if detalhe:
        d = Gtk.Label(label=detalhe, xalign=0)
        d.add_css_class("info")
        textos.append(d)
    caixa.append(textos)
    botoes = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
    caixa.append(botoes)
    return caixa, botoes


def botao(rotulo: str, classe: str, acao) -> Gtk.Button:
    b = Gtk.Button(label=rotulo, valign=Gtk.Align.CENTER)
    b.add_css_class(classe)
    b.connect("clicked", lambda *_: acao())
    return b


def limpar(caixa: Gtk.Box) -> None:
    while (f := caixa.get_first_child()) is not None:
        caixa.remove(f)


# --------------------------------------------------------------------------
# Bluetooth (bluetoothctl)
# --------------------------------------------------------------------------

class PaginaBluetooth(Gtk.Box):
    def __init__(self, aviso):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.aviso = aviso
        cab = Gtk.Box(spacing=10)
        cab.append(titulo_pagina("Bluetooth", "Fones, caixas de som, teclados e mouses."))
        cab.append(Gtk.Box(hexpand=True))
        self.chave = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.chave.connect("state-set", self.ligar)
        cab.append(self.chave)
        self.append(cab)
        self.procurar = botao("Procurar dispositivos", "pilula", self.escanear)
        self.procurar.set_halign(Gtk.Align.START)
        self.append(self.procurar)
        self.lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        rol = Gtk.ScrolledWindow(vexpand=True, propagate_natural_height=True)
        rol.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        rol.set_max_content_height(380)
        rol.set_child(self.lista)
        self.append(rol)
        self.atualizar()

    def bt(self, *args, timeout=20):
        if DEMO:
            return 0, ""
        return rodar("bluetoothctl", *args, timeout=timeout)

    def estado(self) -> dict:
        if DEMO:
            return {"adaptador": True, "ligado": True, "dispositivos": [
                {"mac": "1", "nome": "Fone Morfo", "pareado": True, "conectado": True},
                {"mac": "2", "nome": "Teclado K380", "pareado": True, "conectado": False},
                {"mac": "3", "nome": "Caixa JBL Go", "pareado": False, "conectado": False},
            ]}
        cod, show = self.bt("show", timeout=5)
        if cod != 0 or "Controller" not in show:
            return {"adaptador": False}
        ligado = "Powered: yes" in show

        def lista(*filtro):
            _, txt = self.bt("devices", *filtro, timeout=5)
            out = {}
            for l in txt.splitlines():
                m = re.match(r"Device ([0-9A-F:]{17}) (.*)", l.strip())
                if m:
                    out[m.group(1)] = m.group(2)
            return out
        todos, pareados, conectados = lista(), lista("Paired"), lista("Connected")
        disp = [{"mac": mac, "nome": nome, "pareado": mac in pareados, "conectado": mac in conectados}
                for mac, nome in todos.items() if not re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", nome)]
        disp.sort(key=lambda d: (not d["conectado"], not d["pareado"], d["nome"].lower()))
        return {"adaptador": True, "ligado": ligado, "dispositivos": disp}

    def atualizar(self) -> None:
        em_segundo_plano(self.estado, self.mostrar)

    def mostrar(self, e: dict) -> None:
        limpar(self.lista)
        if not e.get("adaptador"):
            self.chave.set_sensitive(False)
            self.procurar.set_sensitive(False)
            msg = Gtk.Label(label="Nenhum adaptador Bluetooth encontrado.", xalign=0)
            msg.add_css_class("estado")
            self.lista.append(msg)
            return
        self.chave.handler_block_by_func(self.ligar)
        self.chave.set_active(e["ligado"])
        self.chave.handler_unblock_by_func(self.ligar)
        self.procurar.set_sensitive(e["ligado"])
        if not e["ligado"]:
            return
        if not e["dispositivos"]:
            msg = Gtk.Label(label="Nenhum dispositivo ainda. Coloque o aparelho em modo de pareamento e toque em Procurar.",
                            xalign=0, wrap=True)
            msg.add_css_class("estado")
            self.lista.append(msg)
        for d in e["dispositivos"]:
            detalhe = "conectado" if d["conectado"] else ("pareado" if d["pareado"] else "disponível")
            linha, botoes = linha_item(d["nome"], detalhe, d["conectado"])
            mac = d["mac"]
            if d["conectado"]:
                botoes.append(botao("Desconectar", "secundario", lambda m=mac: self.acao(("disconnect", m), "Desconectado.")))
            elif d["pareado"]:
                botoes.append(botao("Esquecer", "pilula", lambda m=mac: self.acao(("remove", m), "Dispositivo esquecido.")))
                botoes.append(botao("Conectar", "entrar", lambda m=mac: self.acao(("connect", m), "Conectado.")))
            else:
                botoes.append(botao("Parear", "entrar", lambda m=mac: self.parear(m)))
            self.lista.append(linha)

    def ligar(self, _chave, estado: bool) -> bool:
        self.acao(("power", "on" if estado else "off"), "")
        return False

    def escanear(self) -> None:
        self.procurar.set_sensitive(False)
        self.procurar.set_label("Procurando… (10 s)")
        em_segundo_plano(lambda: self.bt("--timeout", "10", "scan", "on", timeout=15), self._fim_escaneamento)

    def _fim_escaneamento(self, _r) -> None:
        self.procurar.set_label("Procurar dispositivos")
        self.atualizar()

    def parear(self, mac: str) -> None:
        self.aviso("Pareando… confirme no aparelho, se ele pedir.", False)

        def trabalho():
            cod, txt = self.bt("--timeout", "20", "pair", mac, timeout=25)
            if cod == 0 or "AlreadyExists" in txt:
                self.bt("trust", mac)
                cod, txt = self.bt("--timeout", "15", "connect", mac, timeout=20)
            return cod, txt
        em_segundo_plano(trabalho, lambda r: (self.aviso("Pareado e conectado." if r[0] == 0 else
                                                         "Não consegui parear. Confira o modo de pareamento.", r[0] != 0),
                                              self.atualizar()))

    def acao(self, args: tuple, sucesso: str) -> None:
        em_segundo_plano(lambda: self.bt(*args, timeout=20),
                         lambda r: ((self.aviso(sucesso, False) if r[0] == 0 else self.aviso("Não deu certo: " + r[1][-120:]))
                                    if sucesso or r[0] != 0 else None, self.atualizar()))


# --------------------------------------------------------------------------
# Som (pactl, do PipeWire)
# --------------------------------------------------------------------------

class PaginaSom(Gtk.Box):
    def __init__(self, aviso):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.aviso = aviso
        self.append(titulo_pagina("Som", "Volume e por onde o som sai."))

        vol = Gtk.Box(spacing=14)
        vol.add_css_class("rede")
        rot = Gtk.Label(label="Volume", xalign=0)
        rot.add_css_class("ssid")
        self.escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.escala.set_hexpand(True)
        self.escala.set_draw_value(False)
        self.escala.connect("value-changed", self.mudar_volume)
        self.valor = Gtk.Label(label="")
        self.valor.add_css_class("info")
        self.mudo = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Som ligado")
        self.mudo.connect("state-set", self.mudar_mudo)
        vol.append(rot)
        vol.append(self.escala)
        vol.append(self.valor)
        vol.append(self.mudo)
        self.append(vol)

        saida = Gtk.Label(label="Saída de som", xalign=0)
        saida.add_css_class("ssid")
        self.append(saida)
        self.saidas = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self.saidas)
        self._ignorar = False
        self._agendado = None
        self.atualizar()

    def estado(self) -> dict:
        if DEMO:
            return {"volume": 62, "mudo": False, "padrao": "b", "saidas": [
                ("a", "Alto-falante interno"), ("b", "Monitor AOC (HDMI)"), ("c", "Fone de ouvido")]}
        _, vol = rodar("pactl", "get-sink-volume", "@DEFAULT_SINK@", timeout=5)
        m = re.search(r"(\d+)%", vol)
        _, mudo = rodar("pactl", "get-sink-mute", "@DEFAULT_SINK@", timeout=5)
        _, padrao = rodar("pactl", "get-default-sink", timeout=5)
        cod, js = rodar("pactl", "-f", "json", "list", "sinks", timeout=5)
        saidas = []
        if cod == 0:
            try:
                for s in json.loads(js):
                    saidas.append((s.get("name", ""), s.get("description") or s.get("name", "")))
            except ValueError:
                pass
        return {"volume": int(m.group(1)) if m else 0, "mudo": "yes" in mudo,
                "padrao": padrao.strip(), "saidas": saidas}

    def atualizar(self) -> None:
        em_segundo_plano(self.estado, self.mostrar)

    def mostrar(self, e: dict) -> None:
        self._ignorar = True
        self.escala.set_value(min(e["volume"], 100))
        self.valor.set_label(f"{e['volume']}%")
        self.mudo.set_active(not e["mudo"])
        self._ignorar = False
        limpar(self.saidas)
        if not e["saidas"]:
            msg = Gtk.Label(label="Nenhuma saída de som encontrada.", xalign=0)
            msg.add_css_class("estado")
            self.saidas.append(msg)
        for nome, descricao in e["saidas"]:
            ativa = nome == e["padrao"]
            linha, botoes = linha_item(descricao, "em uso" if ativa else "", ativa)
            if not ativa:
                botoes.append(botao("Usar esta", "secundario", lambda n=nome: self.usar(n)))
            self.saidas.append(linha)

    def mudar_volume(self, escala) -> None:
        if self._ignorar:
            return
        v = int(escala.get_value())
        self.valor.set_label(f"{v}%")
        if self._agendado:
            GLib.source_remove(self._agendado)
        # Espera o dedo parar antes de chamar o pactl.
        self._agendado = GLib.timeout_add(120, self._aplicar_volume, v)

    def _aplicar_volume(self, v: int) -> bool:
        self._agendado = None
        if not DEMO:
            rodar("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%", timeout=5)
        return False

    def mudar_mudo(self, _sw, ligado: bool) -> bool:
        if not self._ignorar and not DEMO:
            rodar("pactl", "set-sink-mute", "@DEFAULT_SINK@", "0" if ligado else "1", timeout=5)
        return False

    def usar(self, nome: str) -> None:
        if not DEMO:
            rodar("pactl", "set-default-sink", nome, timeout=5)
        self.aviso("Saída de som trocada.", False)
        self.atualizar()


# --------------------------------------------------------------------------
# Aparência (tema e teclado)
# --------------------------------------------------------------------------

class PaginaAparencia(Gtk.Box):
    def __init__(self, aviso, ao_mudar_tema):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.aviso = aviso
        self.append(titulo_pagina("Aparência", "Tema e teclado."))

        rot = Gtk.Label(label="Tema", xalign=0)
        rot.add_css_class("ssid")
        self.append(rot)
        temas = Gtk.Box(spacing=12, homogeneous=True)
        atual = tema_atual()
        for tid, nome in TEMAS.items():
            b = Gtk.Button()
            caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            img = Gtk.Picture.new_for_filename(str(SHARE / "temas" / tid / "fundo.jpg"))
            img.set_content_fit(Gtk.ContentFit.COVER)
            img.set_size_request(-1, 90)
            img.set_can_shrink(True)
            img.add_css_class("miniatura")
            caixa.append(img)
            caixa.append(Gtk.Label(label=nome + ("  ·  em uso" if tid == atual else "")))
            b.set_child(caixa)
            b.add_css_class("opcao-tema")
            if tid == atual:
                b.add_css_class("escolhida")
            b.connect("clicked", lambda *_, t=tid: ao_mudar_tema(t))
            temas.append(b)
        self.append(temas)
        nota = Gtk.Label(label="O tema vale para a Central, a tela de login e o boot.", xalign=0, wrap=True)
        nota.add_css_class("info")
        self.append(nota)

        rot2 = Gtk.Label(label="Teclado", xalign=0)
        rot2.add_css_class("ssid")
        self.append(rot2)
        atual_tec = self.teclado_atual()
        for cod, nome, desc in TECLADOS:
            linha, botoes = linha_item(nome, desc, cod == atual_tec)
            if cod != atual_tec:
                botoes.append(botao("Usar este", "secundario", lambda c=cod, n=nome: self.usar_teclado(c, n)))
            self.append(linha)

    def teclado_atual(self) -> str:
        try:
            t = (ESTADO / "teclado").read_text().split()
            if len(t) == 3:
                return " ".join(t)
        except OSError:
            pass
        try:
            txt = Path("/etc/default/keyboard").read_text()
            lay = re.search(r'XKBLAYOUT="?([^"\n]*)', txt)
            var = re.search(r'XKBVARIANT="?([^"\n]*)', txt)
            lay, var = (lay.group(1) if lay else "us"), (var.group(1) if var else "")
            for cod, *_ in TECLADOS:
                c = cod.split()
                if c[0] == lay and (c[2] if c[2] != "-" else "") == var:
                    return cod
        except OSError:
            pass
        return "br abnt2 -"

    def usar_teclado(self, cod: str, nome: str) -> None:
        if not gravar("teclado", cod):
            self.aviso("Não consegui salvar o teclado.")
            return
        lay, modelo, var = cod.split()
        if not DEMO and os.environ.get("SWAYSOCK"):
            rodar("swaymsg", f'input type:keyboard xkb_layout "{lay}"', timeout=5)
            rodar("swaymsg", f'input type:keyboard xkb_model "{modelo}"', timeout=5)
            rodar("swaymsg", f'input type:keyboard xkb_variant "{"" if var == "-" else var}"', timeout=5)
        self.aviso(f"Teclado {nome} em uso.", False)


# --------------------------------------------------------------------------
# Sistema
# --------------------------------------------------------------------------

class PaginaSistema(Gtk.Box):
    def __init__(self, aviso, fechar):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.aviso = aviso
        self.append(titulo_pagina("Sistema"))

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info.add_css_class("rede")
        for rotulo, valor in self.versoes():
            l = Gtk.Box(spacing=8)
            a = Gtk.Label(label=rotulo, xalign=0, hexpand=True)
            a.add_css_class("info")
            b = Gtk.Label(label=valor, xalign=1)
            b.add_css_class("ssid")
            l.append(a)
            l.append(b)
            info.append(l)
        self.append(info)

        linha, botoes = linha_item("Atualizar tudo", "Debian, Morfo e o Claude Desktop. Pede a sua senha.")
        botoes.append(botao("Atualizar", "entrar", self.atualizar_sistema))
        self.append(linha)

        acoes = Gtk.Box(spacing=10)
        acoes.append(botao("Sair para o login", "secundario", self.sair))
        acoes.append(Gtk.Box(hexpand=True))
        acoes.append(botao("Reiniciar", "secundario", lambda: self.energia("reboot")))
        acoes.append(botao("Desligar", "secundario", lambda: self.energia("poweroff")))
        self.append(acoes)
        self.fechar = fechar

    def versoes(self) -> list[tuple[str, str]]:
        if DEMO:
            return [("Morfo Linux", "0.3"), ("Base", "Debian 13 (trixie)"), ("Claude Desktop", "5.11492.5")]
        out = []
        try:
            linhas = Path("/etc/morfo-release").read_text().splitlines()
            out.append(("Morfo Linux", linhas[0].replace("Morfo Linux", "").strip() or "instalado"))
            if len(linhas) > 1:
                out.append(("Base", linhas[1].replace("base:", "").strip()))
        except OSError:
            out.append(("Morfo Linux", "—"))
        _, v = rodar("dpkg-query", "-W", "-f=${Version}", "claude-desktop", timeout=5)
        out.append(("Claude Desktop", v or "não instalado"))
        return out

    def atualizar_sistema(self) -> None:
        if DEMO:
            return
        cmd = ("clear; echo; echo '  Atualizando o Morfo Linux (Debian, Morfo e Claude Desktop)'; echo; "
               "sudo apt update && sudo apt full-upgrade; echo; read -p '  Pronto. Enter para fechar.' x")
        subprocess.Popen(["foot", "--app-id", "org.morfolinux.Terminal", "bash", "-c", cmd])

    def sair(self) -> None:
        if not DEMO:
            subprocess.Popen(["swaymsg", "exit"])

    def energia(self, acao: str) -> None:
        if not DEMO:
            subprocess.Popen(["systemctl", acao])


# --------------------------------------------------------------------------
# Janela
# --------------------------------------------------------------------------

class Central(Gtk.ApplicationWindow):
    PAGINAS = ["wifi", "bluetooth", "som", "aparencia", "sistema"]
    NOMES = {"wifi": "Wi-Fi", "bluetooth": "Bluetooth", "som": "Som", "aparencia": "Aparência", "sistema": "Sistema"}

    def __init__(self, app: Gtk.Application, pagina: str):
        super().__init__(application=app, title="Central do Morfo")
        self.app = app
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.tecla)
        self.add_controller(teclas)
        self.pagina_inicial = pagina
        self.montar()

    def montar(self) -> None:
        tema = tema_atual()
        g = SHARE / "greeter"
        self.css.load_from_string((g / "base.css").read_text() + (g / f"{tema}.css").read_text()
                                  + (SHARE / "rede" / "rede.css").read_text()
                                  + (SHARE / "central" / "central.css").read_text())
        overlay = Gtk.Overlay()
        fundo = Gtk.Picture.new_for_filename(str(SHARE / "temas" / tema / "fundo.jpg"))
        fundo.set_content_fit(Gtk.ContentFit.COVER)
        fundo.set_can_shrink(True)
        overlay.set_child(fundo)

        raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        raiz.add_css_class("raiz")
        overlay.add_overlay(raiz)

        topo = Gtk.Box(spacing=12)
        topo.add_css_class("topo")
        marca = Gtk.Image.new_from_file(str(SHARE / "temas" / tema / "logo-128.png"))
        marca.set_pixel_size(30)
        marca.set_valign(Gtk.Align.CENTER)
        nome = Gtk.Label(label="Central do Morfo")
        nome.add_css_class("nome")
        topo.append(marca)
        topo.append(nome)
        topo.append(Gtk.Box(hexpand=True))
        dica = Gtk.Label(label="Super + Espaço abre e fecha")
        dica.add_css_class("info")
        topo.append(dica)
        topo.append(botao("Fechar  ·  Esc", "energia", self.fechar))
        raiz.append(topo)

        cartao = Gtk.Box(spacing=0, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        cartao.add_css_class("cartao")
        cartao.add_css_class("central")
        cartao.set_size_request(880, 560)
        for lado in ("start", "end"):
            getattr(cartao, f"set_margin_{lado}")(48)

        lateral = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        lateral.add_css_class("lateral")
        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True)
        self.pilha.add_css_class("conteudo")

        self.aviso_lbl = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.aviso_lbl.add_css_class("erro")

        rede = carregar_rede()
        paginas = {
            "wifi": self._com_titulo("Wi-Fi", "Escolha uma rede e digite a senha.", rede.PainelRede(titulo_visivel=False)),
            "bluetooth": PaginaBluetooth(self.aviso),
            "som": PaginaSom(self.aviso),
            "aparencia": PaginaAparencia(self.aviso, self.mudar_tema),
            "sistema": PaginaSistema(self.aviso, self.fechar),
        }
        for chave in self.PAGINAS:
            # Cada página rola sozinha: em telas baixas nada fica cortado.
            rol = Gtk.ScrolledWindow(vexpand=True)
            rol.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            rol.set_child(paginas[chave])
            self.pilha.add_named(rol, chave)
            item = Gtk.Label(label=self.NOMES[chave], xalign=0)
            item.add_css_class("item-lateral")
            linha = Gtk.ListBoxRow()
            linha.set_child(item)
            linha.nome_pagina = chave
            lateral.append(linha)
        lateral.connect("row-selected", lambda _l, r: r and self.ir(r.nome_pagina))
        self.lateral = lateral

        direita = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        direita.append(self.pilha)
        direita.append(self.aviso_lbl)
        cartao.append(lateral)
        cartao.append(direita)
        raiz.append(cartao)
        raiz.append(Gtk.Box(height_request=40))
        self.set_child(overlay)

        inicial = self.pagina_inicial if self.pagina_inicial in self.PAGINAS else "wifi"
        lateral.select_row(lateral.get_row_at_index(self.PAGINAS.index(inicial)))

    def _com_titulo(self, titulo: str, sub: str, painel: Gtk.Widget) -> Gtk.Widget:
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        caixa.append(titulo_pagina(titulo, sub))
        caixa.append(painel)
        return caixa

    def ir(self, pagina: str) -> None:
        self.pagina_inicial = pagina
        self.pilha.set_visible_child_name(pagina)
        self.aviso("")

    def aviso(self, texto: str, erro: bool = True) -> None:
        self.aviso_lbl.set_label(texto or "")
        self.aviso_lbl.set_visible(bool(texto))
        (self.aviso_lbl.remove_css_class if erro else self.aviso_lbl.add_css_class)("ok")

    def mudar_tema(self, tema: str) -> None:
        if not gravar("tema", tema):
            self.aviso("Não consegui salvar o tema.")
            return
        self.montar()
        self.aviso(f"Tema {TEMAS[tema]} aplicado. No boot ele vale a partir do próximo reinício.", False)

    def tecla(self, _c, tecla, _cod, _estado) -> bool:
        if tecla == Gdk.KEY_Escape:
            self.fechar()
            return True
        return False

    def fechar(self) -> None:
        self.app.quit()


def main() -> None:
    pagina = sys.argv[sys.argv.index("--pagina") + 1] if "--pagina" in sys.argv else "wifi"
    app = Gtk.Application(application_id="org.morfolinux.Central")

    def ativar(a):
        janelas = a.get_windows()
        if janelas:
            janelas[0].present()
            return
        Central(a, pagina).present()

    app.connect("activate", ativar)
    app.run([])


if __name__ == "__main__":
    main()
