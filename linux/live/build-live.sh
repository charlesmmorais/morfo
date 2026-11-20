#!/bin/bash
# =============================================================================
# Morfo Linux — gera a ISO viva com o instalador Calamares (v0.2+).
#
# Roda dentro de um container Debian com privilégios (o live-build monta
# sistemas de arquivos):
#
#   docker run --rm --privileged -v "$PWD:/repo" -e MORFO_VERSAO=dev \
#       debian:trixie bash /repo/linux/live/build-live.sh
#
# Saída: linux/dist/morfo-linux-live-<versão>-amd64.iso
# O Claude Desktop NÃO vai na ISO: é baixado na máquina de quem usa.
# =============================================================================
set -euo pipefail

REPO="${REPO:-/repo}"
LINUX="$REPO/linux"
VERSAO="${MORFO_VERSAO:-dev}"
W="${WORK:-/build}"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

say "1/4 Ferramentas"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq live-build debootstrap squashfs-tools xorriso >/dev/null

say "2/4 Configuração do live-build"
rm -rf "$W" && mkdir -p "$W" && cd "$W"
lb config \
    --distribution trixie \
    --archive-areas "main contrib non-free non-free-firmware" \
    --debian-installer none \
    --binary-images iso-hybrid \
    --linux-packages "linux-image linux-headers" \
    --bootappend-live "boot=live components quiet splash username=morfo hostname=morfo locales=pt_BR.UTF-8 keyboard-layouts=br keyboard-model=abnt2 timezone=America/Sao_Paulo" \
    --iso-volume "MORFO_LINUX" \
    --iso-application "Morfo Linux" \
    --iso-publisher "Morfo Linux" \
    --memtest none \
    --firmware-chroot true \
    --firmware-binary false \
    --security true \
    --updates true \
    --cache false

# Pacotes, gancho e arquivos da sessão viva.
cp -r "$LINUX/live/config/." config/
# O Morfo inteiro em /opt/morfo: o gancho roda o setup a partir daqui, e o
# sistema instalado reaproveita (pós-instalação e retomada sem internet).
M=config/includes.chroot/opt/morfo
mkdir -p "$M/branding"
cp -r "$LINUX/setup.sh" "$LINUX/VERSAO" "$LINUX/rootfs" "$LINUX/offline" "$M/"
cp -r "$LINUX/branding/out" "$M/branding/"
chmod +x config/hooks/normal/*.hook.chroot

# Menus de boot com a marca do Morfo e início automático (o padrão do
# live-build espera para sempre no menu, com a marca do Debian).
mkdir -p config/bootloaders
for b in grub-pc isolinux; do
    [ -d "/usr/share/live/build/bootloaders/$b" ] && cp -r "/usr/share/live/build/bootloaders/$b" config/bootloaders/
done
echo "arquivos dos menus de boot:"; find config/bootloaders -type f | sort
for f in config/bootloaders/grub-pc/grub.cfg config/bootloaders/grub-pc/config.cfg \
         config/bootloaders/grub-pc/theme.cfg config/bootloaders/grub-pc/live-theme/theme.txt \
         config/bootloaders/isolinux/isolinux.cfg; do
    [ -f "$f" ] && { echo "----- $f"; cat "$f"; }
done
{ grep -rl "Live system" config/bootloaders 2>/dev/null || true; } | xargs -r sed -i 's/Live system/Morfo Linux/g'
if [ -f config/bootloaders/grub-pc/splash.png ]; then
    cp "$LINUX/live/splash-grub.png" config/bootloaders/grub-pc/splash.png
fi
if [ -f config/bootloaders/isolinux/splash.png ]; then
    cp "$LINUX/live/splash-isolinux.png" config/bootloaders/isolinux/splash.png
fi
# Fundo claro (Areia): texto do menu em tons escuros, sem o título do Debian.
T=config/bootloaders/grub-pc/live-theme/theme.txt
if [ -f "$T" ]; then
    sed -i -e 's/"#ffffff"/"#2B2420"/g' -e 's/"#a8a8a8"/"#7D7066"/g' \
        -e 's/^title-text: .*/title-text: ""/' -e 's/fg_color = "#2B2420"/fg_color = "#7A3F6E"/' \
        -e 's/bg_color = "#7D7066"/bg_color = "#E2D6C6"/' -e 's/text_color = "#000000"/text_color = "#FFFFFF"/' "$T"
fi
if [ -f config/bootloaders/grub-pc/config.cfg ]; then
    printf '\nset timeout=4\nset timeout_style=menu\n' >> config/bootloaders/grub-pc/config.cfg
fi
find config/bootloaders/isolinux -name '*.cfg' -exec sed -i -E 's/^timeout .*/timeout 40/I' {} + 2>/dev/null || true
grep -rn "timeout" config/bootloaders 2>/dev/null | head || true

say "3/4 Montando a imagem (demora)"
lb build 2>&1 | tee build.log | grep -E '^(P:|E:|W: )' || true
ISO=$(ls -1 ./*.iso 2>/dev/null | head -1)
[ -n "$ISO" ] || { echo "a ISO não foi gerada; fim do log:"; tail -60 build.log; exit 1; }

say "4/4 Pronto"
mkdir -p "$LINUX/dist"
SAIDA="$LINUX/dist/morfo-linux-live-$VERSAO-amd64.iso"
mv "$ISO" "$SAIDA"
(cd "$LINUX/dist" && sha256sum "$(basename "$SAIDA")" > "$(basename "$SAIDA").sha256")
cp build.log "$LINUX/dist/build-live.log"
chown -R "$(stat -c %u:%g "$REPO")" "$LINUX/dist"
echo "$SAIDA ($(du -h "$SAIDA" | cut -f1))"
