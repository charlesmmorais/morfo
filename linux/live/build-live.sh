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
    --bootappend-live "boot=live components quiet splash username=morfo hostname=morfo locales=pt_BR.UTF-8 timezone=America/Sao_Paulo" \
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
cp -r "$LINUX/setup.sh" "$LINUX/rootfs" "$LINUX/offline" "$M/"
cp -r "$LINUX/branding/out" "$M/branding/"
chmod +x config/hooks/normal/*.hook.chroot

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
