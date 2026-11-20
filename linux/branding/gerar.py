#!/usr/bin/env python3
"""Gera toda a identidade visual do Morfo Linux a partir de código.

    python3 branding/gerar.py

Saída em branding/out/ (é copiada para o sistema pelo setup).
Requer: numpy, Pillow e rsvg-convert (pacote librsvg2-bin).
"""

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

RAIZ = Path(__file__).resolve().parent
OUT = RAIZ / "out"

TEMAS = {
    # Grafite: escuro, destaque azul (a paleta do kernel Morfo).
    "grafite": {
        "fundo": (16, 18, 24),
        "fundo2": (24, 28, 40),
        "brilhos": [((0.78, 0.18), (64, 96, 190), 0.55), ((0.12, 0.92), (40, 70, 150), 0.45), ((0.55, 0.65), (90, 70, 170), 0.18)],
        "grad": ("#8FB8FF", "#4A6CF7"),
        "ponto": "#101218",
        "texto": "#E6E9F0",
        "suave": "#8C93A5",
    },
    # Areia: claro e quente, destaque ameixa.
    "areia": {
        "fundo": (243, 237, 228),
        "fundo2": (233, 222, 206),
        "brilhos": [((0.82, 0.15), (236, 205, 170), 0.65), ((0.10, 0.90), (214, 186, 205), 0.55), ((0.50, 0.55), (250, 244, 236), 0.35)],
        "grad": ("#B07AA6", "#7A3F6E"),
        "ponto": "#F3EDE4",
        "texto": "#2B2420",
        "suave": "#7D7066",
    },
}


def logo_svg(t: dict, tamanho: int = 256) -> str:
    """Marca: uma "folha" — quadrado com dois cantos totalmente redondos,
    a forma no meio do caminho entre círculo e quadrado (a ideia de morfar).
    O ponto é o cursor de uma conversa."""
    a, b = t["grad"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{tamanho}" height="{tamanho}" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{a}"/>
      <stop offset="1" stop-color="{b}"/>
    </linearGradient>
  </defs>
  <path fill="url(#g)" d="M128 16 H204 A36 36 0 0 1 240 52 V128 A112 112 0 0 1 128 240 H52 A36 36 0 0 1 16 204 V128 A112 112 0 0 1 128 16 Z"/>
  <circle cx="164" cy="164" r="22" fill="{t['ponto']}"/>
</svg>
"""


def wordmark_svg(t: dict) -> str:
    a, b = t["grad"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="256" viewBox="0 0 1080 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>
    </linearGradient>
  </defs>
  <path fill="url(#g)" d="M128 16 H204 A36 36 0 0 1 240 52 V128 A112 112 0 0 1 128 240 H52 A36 36 0 0 1 16 204 V128 A112 112 0 0 1 128 16 Z"/>
  <circle cx="164" cy="164" r="22" fill="{t['ponto']}"/>
  <text x="290" y="168" font-family="Inter" font-weight="600" font-size="132" letter-spacing="-4" fill="{t['texto']}">morfo</text>
  <text x="712" y="168" font-family="Inter" font-weight="300" font-size="132" letter-spacing="-4" fill="{t['suave']}">linux</text>
</svg>
"""


def svg_para_png(svg: str, destino: Path, largura: int) -> None:
    tmp = destino.with_suffix(".tmp.svg")
    tmp.write_text(svg)
    subprocess.run(["rsvg-convert", "-w", str(largura), "-o", str(destino), str(tmp)], check=True)
    tmp.unlink()


def papel_de_parede(t: dict, w: int = 1920, h: int = 1080, semente: int = 7) -> Image.Image:
    """Degradê suave com brilhos difusos e um grão leve (evita faixas)."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = x / w, y / h
    f1, f2 = np.array(t["fundo"], np.float32), np.array(t["fundo2"], np.float32)
    mistura = np.clip(0.6 * ny + 0.4 * nx, 0, 1)[..., None]
    img = f1 * (1 - mistura) + f2 * mistura

    for (cx, cy), cor, forca in t["brilhos"]:
        d2 = ((nx - cx) * (w / h)) ** 2 + (ny - cy) ** 2
        peso = (np.exp(-d2 / 0.18) * forca)[..., None]
        img = img * (1 - peso) + np.array(cor, np.float32) * peso

    rng = np.random.default_rng(semente)
    img += rng.normal(0, 1.6, img.shape[:2])[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ponto(cor: str, d: Path, tamanho: int = 14) -> None:
    """Bolinha do indicador de carregamento do Plymouth (com antisserrilhado)."""
    from PIL import ImageDraw
    k = 4
    img = Image.new("RGBA", (tamanho * k, tamanho * k), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, tamanho * k - 1, tamanho * k - 1), fill=hex_rgb(cor) + (255,))
    img.resize((tamanho, tamanho), Image.LANCZOS).save(d / "ponto.png")


def plymouth_two_step(t: dict, d: Path) -> None:
    """Imagens do tema two-step do Plymouth: a marca (watermark) e os quadros
    da animação (throbber), três pontos que acendem em sequência."""
    import math
    from PIL import ImageDraw
    p = d / "plymouth"
    p.mkdir(exist_ok=True)
    Image.open(d / "logo-256.png").resize((112, 112), Image.LANCZOS).save(p / "watermark.png")
    cor = hex_rgb(t["grad"][1])
    k, raio, passo, quadros = 4, 7, 26, 36
    w, h = passo * 2 + raio * 2 + 4, raio * 2 + 4
    for q in range(quadros):
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        for i in range(3):
            fase = (q / quadros) * 2 * math.pi - i * 0.9
            alfa = int(255 * (0.25 + 0.75 * (math.sin(fase) * 0.5 + 0.5)))
            cx, cy = (2 + raio + i * passo) * k, (2 + raio) * k
            dr.ellipse((cx - raio * k, cy - raio * k, cx + raio * k, cy + raio * k), fill=cor + (alfa,))
        img.resize((w, h), Image.LANCZOS).save(p / f"throbber-{q + 1:04d}.png")
    # Peças do diálogo de senha (só aparecem com disco criptografado).
    Image.new("RGBA", (10, 10), cor + (255,)).save(p / "bullet.png")
    entrada = Image.new("RGBA", (300, 36), (0, 0, 0, 0))
    ImageDraw.Draw(entrada).rounded_rectangle((0, 0, 299, 35), radius=10, fill=(255, 255, 255, 40), outline=cor + (255,))
    entrada.save(p / "entry.png")
    Image.open(d / "logo-128.png").resize((32, 32), Image.LANCZOS).save(p / "lock.png")


def selecao_grub(cor: str, d: Path, raio: int = 12) -> None:
    """Destaque do item selecionado no menu do GRUB, em 9 pedaços (select_*.png)."""
    from PIL import ImageDraw
    k, lado = 4, raio * 3
    rgba = hex_rgb(cor) + (70,)
    img = Image.new("RGBA", (lado * k, lado * k), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, lado * k - 1, lado * k - 1), radius=raio * k, fill=rgba)
    img = img.resize((lado, lado), Image.LANCZOS)
    r = raio
    partes = {
        "nw": (0, 0, r, r), "n": (r, 0, 2 * r, r), "ne": (2 * r, 0, 3 * r, r),
        "w": (0, r, r, 2 * r), "c": (r, r, 2 * r, 2 * r), "e": (2 * r, r, 3 * r, 2 * r),
        "sw": (0, 2 * r, r, 3 * r), "s": (r, 2 * r, 2 * r, 3 * r), "se": (2 * r, 2 * r, 3 * r, 3 * r),
    }
    for nome, caixa in partes.items():
        img.crop(caixa).save(d / f"select_{nome}.png")


def instalador() -> None:
    """Faixa do instalador gráfico do Debian (800x75) e tela do boot BIOS (640x480)."""
    d = OUT / "instalador"
    d.mkdir(exist_ok=True)
    for nome, arquivo in (("grafite", "logo_installer_dark.png"), ("areia", "logo_installer.png")):
        t = TEMAS[nome]
        faixa = papel_de_parede(t, 800, 75)
        marca = Image.open(OUT / nome / "wordmark.png").convert("RGBA")
        marca = marca.resize((int(46 * marca.width / marca.height), 46), Image.LANCZOS)
        faixa.paste(marca, (24, 15), marca)
        faixa.save(d / arquivo)
    t = TEMAS["grafite"]
    tela = papel_de_parede(t, 640, 480)
    marca = Image.open(OUT / "grafite" / "wordmark.png").convert("RGBA")
    marca = marca.resize((300, int(300 * marca.height / marca.width)), Image.LANCZOS)
    tela.paste(marca, ((640 - marca.width) // 2, 70), marca)
    tela.convert("RGB").save(d / "splash.png")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for nome, t in TEMAS.items():
        d = OUT / nome
        d.mkdir(exist_ok=True)
        (d / "logo.svg").write_text(logo_svg(t))
        svg_para_png(logo_svg(t), d / "logo-128.png", 128)
        svg_para_png(logo_svg(t), d / "logo-256.png", 256)
        svg_para_png(wordmark_svg(t), d / "wordmark.png", 1080)

        fundo = papel_de_parede(t)
        fundo.save(d / "fundo.jpg", quality=92, subsampling=0)
        # Fundo do GRUB: mesma imagem com a marca grande e discreta.
        grub = fundo.copy()
        marca = Image.open(d / "wordmark.png").convert("RGBA")
        marca = marca.resize((540, int(540 * marca.height / marca.width)), Image.LANCZOS)
        grub.paste(marca, ((1920 - marca.width) // 2, 230), marca)
        grub.save(d / "grub.jpg", quality=90)
        ponto(t["grad"][1], d)
        plymouth_two_step(t, d)
        selecao_grub(t["grad"][0], d)
        print(f"tema {nome}: ok")

    instalador()

    # Ícone do repositório (README).
    svg_para_png(wordmark_svg(TEMAS["grafite"]), OUT / "wordmark-grafite.png", 1080)
    svg_para_png(wordmark_svg(TEMAS["areia"]), OUT / "wordmark-areia.png", 1080)


if __name__ == "__main__":
    main()
