#!/usr/bin/env bash
# Morfo — compila o kernel e gera as mídias de boot.
#
#   ./build.sh            compila e gera tudo (dist/)
#   ./build.sh run        roda no QEMU (UEFI)
#   ./build.sh run-bios   roda no QEMU (BIOS)
set -euo pipefail
cd "$(dirname "$0")"

LIMINE_DIR="${LIMINE_DIR:-limine}"
LIMINE_BRANCH="v9.x-binary"
KERNEL=kernel/target/x86_64-unknown-none/release/morfo-kernel

fetch_limine() {
    if [ ! -f "$LIMINE_DIR/BOOTX64.EFI" ]; then
        git clone --depth=1 --branch="$LIMINE_BRANCH" \
            https://github.com/limine-bootloader/limine.git "$LIMINE_DIR"
    fi
    make -s -C "$LIMINE_DIR"
}

build_kernel() {
    # RUSTC_BOOTSTRAP libera recursos instáveis (build-std, x86-interrupt)
    # no Rust estável. Com nightly não é necessário.
    (cd kernel && RUSTC_BOOTSTRAP=1 cargo build --release)
}

make_usb_dir() {
    # Conteúdo para copiar num pendrive formatado em FAT32.
    local d=dist/pendrive
    rm -rf "$d" && mkdir -p "$d/EFI/BOOT" "$d/boot/limine"
    cp "$LIMINE_DIR/BOOTX64.EFI" "$d/EFI/BOOT/"
    cp limine.conf "$d/boot/limine/"
    cp "$KERNEL" "$d/boot/morfo-kernel"
}

make_iso() {
    local iso=dist/iso_root
    rm -rf "$iso" && mkdir -p "$iso/boot/limine" "$iso/EFI/BOOT"
    cp "$KERNEL" "$iso/boot/morfo-kernel"
    cp limine.conf "$LIMINE_DIR/limine-bios.sys" "$LIMINE_DIR/limine-bios-cd.bin" \
       "$LIMINE_DIR/limine-uefi-cd.bin" "$iso/boot/limine/"
    cp "$LIMINE_DIR/BOOTX64.EFI" "$iso/EFI/BOOT/"
    xorriso -as mkisofs -R -r -J -b boot/limine/limine-bios-cd.bin \
        -no-emul-boot -boot-load-size 4 -boot-info-table -hfsplus \
        -apm-block-size 2048 --efi-boot boot/limine/limine-uefi-cd.bin \
        -efi-boot-part --efi-boot-image --protective-msdos-label \
        "$iso" -o dist/morfo.iso 2>/dev/null
    "$LIMINE_DIR/limine" bios-install dist/morfo.iso 2>/dev/null
    rm -rf "$iso"
}

ovmf() {
    for f in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/ovmf/OVMF.fd; do
        [ -f "$f" ] && { echo "$f"; return; }
    done
    echo "OVMF não encontrado (instale o pacote ovmf)" >&2; exit 1
}

all() {
    fetch_limine
    build_kernel
    mkdir -p dist
    make_usb_dir
    make_iso
    echo "Pronto: dist/morfo.iso e dist/pendrive/"
}

case "${1:-all}" in
    all) all ;;
    run) all; qemu-system-x86_64 -M q35 -m 2G -serial stdio \
            -device ich9-usb-ehci1,id=ehci -device usb-kbd,bus=ehci.0 \
            -drive if=pflash,unit=0,format=raw,readonly=on,file="$(ovmf)" \
            -cdrom dist/morfo.iso ;;
    run-bios) all; qemu-system-x86_64 -M q35 -m 2G -serial stdio -cdrom dist/morfo.iso ;;
    *) echo "uso: $0 [all|run|run-bios]"; exit 1 ;;
esac
