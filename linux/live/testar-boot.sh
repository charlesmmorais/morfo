#!/bin/bash
# Morfo Linux — testa a ISO viva no QEMU (UEFI): confere o conteúdo da imagem
# e tira fotos da tela durante o boot. As fotos saem no log em base64, entre
# marcadores, para quem só tem acesso ao log conseguir vê-las.
set -uo pipefail
ISO="${1:?uso: testar-boot.sh <iso>}"
T=$(mktemp -d)

echo "== Conteúdo da imagem"
mkdir -p "$T/iso" "$T/sq"
sudo mount -o loop,ro "$ISO" "$T/iso"
sudo mount -o loop,ro "$T/iso/live/filesystem.squashfs" "$T/sq"
for f in /etc/greetd/config.toml /usr/local/bin/morfo-sessao-viva /usr/share/morfo/boasvindas/morfo-boasvindas.py \
         /etc/calamares/settings.conf /usr/share/calamares/branding/morfo/show.qml /usr/bin/calamares \
         /usr/share/plymouth/themes/morfo/morfo.script /usr/local/sbin/morfo-tema /opt/morfo/setup.sh \
         /usr/bin/cage /usr/sbin/greetd /usr/bin/nmcli; do
    if [ -e "$T/sq$f" ]; then echo "ok   $f"; else echo "FALTA $f"; fi
done
echo "kernel: $(ls "$T/sq/boot" | tr '\n' ' ')"
echo "wl.ko (Wi-Fi Broadcom): $(find "$T/sq/lib/modules" -name 'wl.ko*' | head -1)"
echo "plymouth: $(grep -h Theme "$T/sq/etc/plymouth/plymouthd.conf" 2>/dev/null)"
echo "greetd:"; sed 's/^/    /' "$T/sq/etc/greetd/config.toml"
du -sh "$T/iso/live/filesystem.squashfs"
sudo umount "$T/sq" "$T/iso"

echo "== Boot no QEMU"
OVMF=/usr/share/OVMF/OVMF_CODE_4M.fd
[ -f "$OVMF" ] || OVMF=/usr/share/ovmf/OVMF.fd
ACEL=""
[ -w /dev/kvm ] && ACEL="-enable-kvm -cpu host"
# shellcheck disable=SC2086
qemu-system-x86_64 -M q35 -m 4G -smp 2 $ACEL -display none -vga std \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF" \
    -cdrom "$ISO" -monitor unix:"$T/mon",server,nowait -serial file:"$T/serial.log" &
QEMU=$!

foto() {
    echo "screendump $T/$1.ppm" | socat - UNIX-CONNECT:"$T/mon" >/dev/null 2>&1
    sleep 1
    python3 - "$T/$1.ppm" "$1" <<'PY'
import base64, io, sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
im.thumbnail((720, 540))
b = io.BytesIO(); im.save(b, "JPEG", quality=70)
dados = base64.b64encode(b.getvalue()).decode()
print(f"=====FOTO {sys.argv[2]} {im.size[0]}x{im.size[1]}=====")
# Linhas curtas: o log do GitHub descarta linhas muito longas.
for i in range(0, len(dados), 900):
    print("F|" + dados[i:i + 900])
print("=====FIM=====", flush=True)
PY
}

tecla() { echo "sendkey $1" | socat - UNIX-CONNECT:"$T/mon" >/dev/null 2>&1; }
brilho() {
    echo "screendump $T/b.ppm" | socat - UNIX-CONNECT:"$T/mon" >/dev/null 2>&1
    sleep 0.3
    python3 -c 'import sys; from PIL import Image, ImageStat; print(int(ImageStat.Stat(Image.open(sys.argv[1]).convert("L")).mean[0]))' "$T/b.ppm" 2>/dev/null || echo 0
}
# Espera o menu do GRUB (fundo Areia, claro), para a contagem com uma seta,
# fotografa e inicia com Enter.
for _ in $(seq 1 40); do
    [ "$(brilho)" -gt 120 ] && { tecla up; break; }
    sleep 0.5
done
sleep 1; foto 1-grub; tecla ret
sleep 50; foto 2-boot
sleep 60; foto 3-sessao
sleep 60; foto 4-sessao
kill "$QEMU" 2>/dev/null
echo "== Fim do serial"; tail -5 "$T/serial.log" 2>/dev/null
exit 0
