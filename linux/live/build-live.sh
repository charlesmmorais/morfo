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
apt-get install -y -qq live-build debootstrap squashfs-tools xorriso grub-common fonts-inter fontconfig >/dev/null

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

# Menu de boot do Morfo (UEFI e BIOS pelo GRUB). O padrão do live-build
# mostra a marca do Debian e "Live system"; trocamos tudo pelo tema Areia.
mkdir -p config/bootloaders
for b in grub-pc isolinux; do
    [ -d "/usr/share/live/build/bootloaders/$b" ] && cp -r "/usr/share/live/build/bootloaders/$b" config/bootloaders/
done
G=config/bootloaders/grub-pc
rm -f "$G"/install*.cfg "$G"/memtest.cfg
cat > "$G/config.cfg" <<'CFG'
# Morfo Linux — vídeo e tema do menu de boot.
set default=0
set timeout=5
set timeout_style=menu
insmod all_video
insmod gfxterm
insmod png
insmod jpeg
set gfxmode=auto
set gfxpayload=keep
CFG
cat > "$G/theme.cfg" <<'CFG'
loadfont $prefix/themes/morfo/morfo-14.pf2
loadfont $prefix/themes/morfo/morfo-18.pf2
terminal_output gfxterm
set theme=$prefix/themes/morfo/theme.txt
CFG
cat > "$G/grub.cfg" <<'CFG'
source /boot/grub/config.cfg
source /boot/grub/theme.cfg

menuentry "Iniciar o Morfo Linux" {
    linux  @KERNEL_LIVE@ @APPEND_LIVE@
    initrd @INITRD_LIVE@
}

menuentry "Compatibilidade de vídeo" {
    linux  @KERNEL_LIVE@ @APPEND_LIVE@ nomodeset
    initrd @INITRD_LIVE@
}

if [ "$grub_platform" = "efi" ]; then
menuentry "Configurações do firmware" {
    fwsetup
}
fi
CFG
# Arquivos do tema dentro da ISO, em /boot/grub/themes/morfo.
T=config/includes.binary/boot/grub/themes/morfo
mkdir -p "$T"
cp "$LINUX/branding/out/areia/grub.jpg" "$LINUX/branding/out/areia"/select_*.png "$T/"
sed -e 's/@TEXTO@/#2B2420/g' -e 's/@SUAVE@/#7D7066/g' \
    "$LINUX/rootfs/usr/share/morfo/boot/grub-theme.txt" > "$T/theme.txt"
FONTE=$(fc-match -f '%{file}' 'Inter:style=Regular')
for s in 14 18; do grub-mkfont -n "Morfo" -s "$s" -o "$T/morfo-$s.pf2" "$FONTE"; done
# Fundo também como splash.png: o live-build não gera a tela do Debian.
cp "$LINUX/live/splash-grub.png" config/bootloaders/splash.png
cp "$LINUX/live/splash-grub.png" "$G/splash.png"
echo "menu de boot:"; find "$G" "$T" -type f | sort

# BIOS antigo (isolinux): só fundo e textos.
{ grep -rl "Live system" config/bootloaders/isolinux 2>/dev/null || true; } | xargs -r sed -i 's/Live system/Morfo Linux/g'
[ -f config/bootloaders/isolinux/splash.png ] && cp "$LINUX/live/splash-isolinux.png" config/bootloaders/isolinux/splash.png
find config/bootloaders/isolinux -name '*.cfg' -exec sed -i -E 's/^timeout .*/timeout 40/I' {} + 2>/dev/null || true

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
