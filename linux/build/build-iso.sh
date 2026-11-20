#!/bin/bash
# =============================================================================
# Morfo Linux — gera a ISO instaladora a partir do netinst oficial do Debian.
#
#   bash linux/build/build-iso.sh            → linux/dist/morfo-linux-<versão>-amd64.iso
#
# Requisitos (Ubuntu/Debian): xorriso cpio gzip curl python3-numpy python3-pil
#                             librsvg2-bin grub-common fonts-inter
#
# Nada da Anthropic vai dentro da ISO: o Claude Desktop é baixado do
# repositório oficial durante a instalação, na máquina de quem instala.
# =============================================================================
set -euo pipefail

LINUX="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-$LINUX/build/work}"
DIST="$LINUX/dist"
VERSAO="${MORFO_VERSAO:-$(git -C "$LINUX" describe --tags --always 2>/dev/null || echo dev)}"
DEBIAN_CD="${DEBIAN_CD:-https://cdimage.debian.org/debian-cd/current/amd64/iso-cd}"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

for c in xorriso cpio gzip curl python3 rsvg-convert grub-mkfont; do
    command -v "$c" >/dev/null || { echo "falta o comando: $c" >&2; exit 1; }
done

mkdir -p "$WORK" "$DIST"

# -----------------------------------------------------------------------------
say "1/6 Identidade visual"
# -----------------------------------------------------------------------------
python3 "$LINUX/branding/gerar.py"
OUT="$LINUX/branding/out"

# -----------------------------------------------------------------------------
say "2/6 Netinst oficial do Debian (com verificação SHA-512)"
# -----------------------------------------------------------------------------
curl -fsSL "$DEBIAN_CD/SHA512SUMS" -o "$WORK/SHA512SUMS"
BASE=$(awk '$2 ~ /^debian-[0-9.]+-amd64-netinst\.iso$/ {print $2; exit}' "$WORK/SHA512SUMS")
[ -n "$BASE" ] || { echo "não achei o netinst em $DEBIAN_CD" >&2; exit 1; }
if [ ! -f "$WORK/$BASE" ]; then
    curl -fL --progress-bar "$DEBIAN_CD/$BASE" -o "$WORK/$BASE.part"
    mv "$WORK/$BASE.part" "$WORK/$BASE"
fi
(cd "$WORK" && grep " $BASE\$" SHA512SUMS | sha512sum -c -)
echo "base: $BASE"

# -----------------------------------------------------------------------------
say "3/6 Extraindo a ISO"
# -----------------------------------------------------------------------------
ISO="$WORK/iso"
rm -rf "$ISO" && mkdir -p "$ISO"
xorriso -osirrox on -indev "$WORK/$BASE" -extract / "$ISO" 2>/dev/null
chmod -R u+w "$ISO"

# -----------------------------------------------------------------------------
say "4/6 Respostas automáticas e marca no instalador"
# -----------------------------------------------------------------------------
# O d-i lê /preseed.cfg de dentro do initrd. Um segundo cpio concatenado ao
# initrd.gz é aceito pelo kernel e sobrepõe arquivos do primeiro.
EXTRA="$WORK/initrd-extra"
rm -rf "$EXTRA" && mkdir -p "$EXTRA/usr/share/graphics"
cp "$LINUX/installer/preseed.cfg" "$EXTRA/preseed.cfg"
cp "$OUT/instalador/logo_installer.png" "$OUT/instalador/logo_installer_dark.png" "$EXTRA/usr/share/graphics/"
for initrd in "$ISO/install.amd/initrd.gz" "$ISO/install.amd/gtk/initrd.gz"; do
    [ -f "$initrd" ] || continue
    (cd "$EXTRA" && find . | cpio -H newc -o --quiet | gzip -9) >> "$initrd"
done

# Conteúdo do Morfo que o late.sh copia para o sistema instalado.
M="$ISO/morfo"
rm -rf "$M" && mkdir -p "$M"
cp -r "$LINUX/rootfs" "$LINUX/setup.sh" "$M/"
cp "$LINUX/installer/late.sh" "$M/"

# Kit offline: driver do Wi-Fi Broadcom (para o kernel exato desta ISO),
# compilador e NetworkManager, como um repositório local. Assim, quem instala
# sem internet consegue conectar o Wi-Fi no primeiro boot.
mkdir -p "$M/offline"
cp "$LINUX/offline/morfo-continuar" "$LINUX/offline/morfo-continuar.service" "$LINUX/offline/90-morfo-continuar" "$M/offline/"
IMG=$(find "$ISO/pool" -name 'linux-image-[0-9]*-amd64_*_amd64.deb' ! -name '*dbg*' | head -1)
ABI=$(basename "${IMG:-x}" | sed -nE 's/^linux-image-(.+)_[^_]+_amd64\.deb$/\1/p')
CODINOME=$(find "$ISO/dists" -mindepth 1 -maxdepth 1 -type d ! -name stable -printf '%f\n' | head -1)
if [ "${MORFO_SEM_KIT:-0}" != 1 ] && command -v docker >/dev/null && [ -n "$ABI" ] && [ -n "$CODINOME" ]; then
    echo "kernel da ISO: $ABI ($CODINOME)"
    KIT="$M/offline/kit"
    mkdir -p "$KIT"
    echo "$ABI" > "$KIT/ABI"
    docker run --rm -v "$KIT:/kit" -e ABI="$ABI" "debian:$CODINOME" bash -euc '
        sed -i -E "s/^Components:.*/Components: main contrib non-free non-free-firmware/" /etc/apt/sources.list.d/debian.sources
        apt-get update -qq
        apt-get install -y -qq dpkg-dev >/dev/null
        PACOTES="network-manager wpasupplicant pciutils dkms broadcom-sta-dkms linux-headers-$ABI"
        apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks \
            --no-replaces --no-enhances $PACOTES | grep -E "^[a-z0-9]" | sort -u > /tmp/lista
        cd /kit
        xargs -a /tmp/lista -n 20 -P 4 apt-get download -qq 2>/dev/null || true
        for p in $PACOTES; do ls ${p}_*.deb >/dev/null 2>&1 || apt-get download -qq "$p"; done
        dpkg-scanpackages --multiversion . /dev/null 2>/dev/null | gzip -9 > Packages.gz
        chown -R "$(stat -c %u:%g /kit)" /kit
    '
    echo "kit offline: $(find "$KIT" -name '*.deb' | wc -l) pacotes, $(du -sh "$KIT" | cut -f1)"
else
    echo "Aviso: kit offline do Wi-Fi não incluído (precisa de docker; MORFO_SEM_KIT=1 desliga)."
fi
mkdir -p "$M/temas"
cp -r "$OUT/grafite" "$OUT/areia" "$M/temas/"

# Menu UEFI com o tema do Morfo (Grafite).
T="$ISO/boot/grub/themes/morfo"
mkdir -p "$T"
cp "$OUT/grafite/grub.jpg" "$OUT/grafite"/select_*.png "$T/"
sed -e 's/@TEXTO@/#E6E9F0/g' -e 's/@SUAVE@/#8C93A5/g' \
    -e 's/Iniciando em %d s/Instalação automática em %d s/' \
    "$LINUX/rootfs/usr/share/morfo/boot/grub-theme.txt" > "$T/theme.txt"
FONTE=$(fc-match -f '%{file}' 'Inter:style=Regular')
for s in 14 18; do grub-mkfont -n "Morfo" -s "$s" -o "$T/morfo-$s.pf2" "$FONTE" 2>/dev/null; done
cp "$LINUX/installer/grub.cfg" "$ISO/boot/grub/grub.cfg"

# Boot BIOS: só a tela de fundo (o menu continua o do Debian, já com o preseed).
[ -f "$ISO/isolinux/splash.png" ] && cp "$OUT/instalador/splash.png" "$ISO/isolinux/splash.png"

# Identificação.
sed -i "1s/^/Morfo Linux $VERSAO, sobre /" "$ISO/.disk/info" 2>/dev/null || true

# -----------------------------------------------------------------------------
say "5/6 Somas de verificação internas"
# -----------------------------------------------------------------------------
(cd "$ISO" && find . -type f ! -name md5sum.txt ! -path './isolinux/*' -print0 | \
    xargs -0 md5sum > md5sum.txt)

# -----------------------------------------------------------------------------
say "6/6 Montando a ISO (híbrida: BIOS, UEFI e pendrive)"
# -----------------------------------------------------------------------------
SAIDA="$DIST/morfo-linux-$VERSAO-amd64.iso"
# Reaproveita exatamente os parâmetros de boot da ISO original do Debian.
mapfile -t OPCOES < <(xorriso -indev "$WORK/$BASE" -report_el_torito as_mkisofs 2>/dev/null)
eval "xorriso -as mkisofs ${OPCOES[*]} -o \"\$SAIDA\" \"\$ISO\"" 2>&1 | grep -vE '^(xorriso|Drive current|Media current|Media status|Media summary|Added to ISO|Writing|Mapped|Copying|libisofs)' || true
[ -s "$SAIDA" ] || { echo "falha ao gerar a ISO" >&2; exit 1; }

(cd "$DIST" && sha256sum "$(basename "$SAIDA")" > "$(basename "$SAIDA").sha256")
say "Pronto: $SAIDA ($(du -h "$SAIDA" | cut -f1))"
