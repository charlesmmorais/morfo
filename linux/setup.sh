#!/bin/bash
# =============================================================================
# Morfo Linux — transforma um Debian 12/13 (sem desktop) no Morfo Linux.
#
# Num Debian já instalado:      sudo ./setup.sh [grafite|areia]
# Pelo instalador (automático): setup.sh --instalador [grafite|areia]
# Montando a ISO viva:          setup.sh --imagem [grafite|areia]
#   (sem o Claude, sem GRUB; o Wi-Fi Broadcom entra sempre)
#
# O Claude Desktop NÃO vem embutido: é instalado do repositório oficial da
# Anthropic, na sua máquina, como qualquer usuário faria.
# =============================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALADOR=0
IMAGEM=0
TEMA=grafite
for a in "$@"; do
    case "$a" in
        --instalador) INSTALADOR=1 ;;
        --imagem) IMAGEM=1 ;;
        grafite|areia) TEMA="$a" ;;
        *) echo "uso: $0 [--instalador|--imagem] [grafite|areia]" >&2; exit 1 ;;
    esac
done

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mErro: %s\033[0m\n' "$*" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
APT=(apt-get install -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

[ "$(id -u)" -eq 0 ] || die "rode com sudo"
. /etc/os-release
[ "${ID:-}" = debian ] || die "o Morfo Linux é feito sobre Debian (encontrado: ${ID:-?})"
[ "${VERSION_ID%%.*}" -ge 12 ] 2>/dev/null || die "precisa de Debian 12 ou mais novo"
[ "$(dpkg --print-architecture)" = amd64 ] || die "só amd64 por enquanto"

# Assets: do repositório (branding/out) ou do pacote copiado pelo instalador (temas/).
if [ -d "$AQUI/temas" ]; then TEMAS_DIR="$AQUI/temas"; else TEMAS_DIR="$AQUI/branding/out"; fi
[ -f "$TEMAS_DIR/grafite/fundo.jpg" ] || die "assets não encontrados; rode: python3 branding/gerar.py"

# -----------------------------------------------------------------------------
# Sem internet? Instala, a partir do pendrive, o kit offline que vem na ISO
# (Wi-Fi Broadcom + NetworkManager), deixa a instalação pendente e termina
# sozinha quando a internet chegar (morfo-continuar).
# -----------------------------------------------------------------------------
tem_internet() { timeout 5 bash -c 'exec 3<>/dev/tcp/deb.debian.org/80' 2>/dev/null; }
KIT="$AQUI/offline/kit"
if [ "$IMAGEM" = 0 ] && ! tem_internet; then
    [ -f "$KIT/Packages.gz" ] || die "sem internet. Conecte um cabo de rede (ou celular Android em ancoragem USB) e rode de novo."
    say "Sem internet: instalando o Wi-Fi a partir do pendrive"
    [ -f /etc/apt/sources.list ] && sed -i -E 's/^(deb cdrom:)/# \1/' /etc/apt/sources.list
    echo "deb [trusted=yes] file:$KIT ./" > /etc/apt/sources.list.d/morfo-offline.list
    apt-get update || true
    ABI=$(cat "$KIT/ABI" 2>/dev/null || uname -r)
    PACOTES=(network-manager wpasupplicant pciutils)
    if ! command -v lspci >/dev/null || lspci -nn | grep -qiE 'network controller.*broadcom'; then
        PACOTES+=(dkms "linux-headers-$ABI" broadcom-sta-dkms)
    fi
    "${APT[@]}" "${PACOTES[@]}" || echo "Aviso: parte do kit offline não instalou."

    install -D -m 0755 "$AQUI/offline/morfo-continuar" /usr/local/sbin/morfo-continuar
    install -D -m 0644 "$AQUI/offline/morfo-continuar.service" /etc/systemd/system/morfo-continuar.service
    install -D -m 0755 "$AQUI/offline/90-morfo-continuar" /etc/NetworkManager/dispatcher.d/90-morfo-continuar
    systemctl enable morfo-continuar.service
    mkdir -p /var/lib/morfo
    echo "$TEMA" > /var/lib/morfo/pendente
    cat > /etc/motd <<'EOF'

  Morfo Linux: falta só a internet.

  O Wi-Fi já está instalado. Para conectar, rode:

      sudo nmtui

  Escolha "Ativar uma conexão", a sua rede e digite a senha.
  Assim que conectar, o Morfo termina de instalar sozinho
  (alguns minutos) e reinicia na tela de login.

EOF
    say "Pronto para terminar quando houver internet"
    exit 0
fi

# -----------------------------------------------------------------------------
say "1/9 Repositórios contrib e non-free (firmwares e Wi-Fi)"
# -----------------------------------------------------------------------------
if [ -f /etc/apt/sources.list ]; then
    sed -i -E '/^deb(-src)? /{ / contrib/! s/ main/ main contrib/; / non-free( |$)/! s/ contrib/ contrib non-free/; / non-free-firmware/! s/$/ non-free-firmware/ }' /etc/apt/sources.list
fi
for f in /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] && grep -q '^Components:' "$f" && \
        sed -i -E 's/^Components:.*/Components: main contrib non-free non-free-firmware/' "$f"
done
# Instalação feita sem internet: o apt só conhece o pendrive. Usa o espelho oficial.
[ -f /etc/apt/sources.list ] && sed -i -E 's/^(deb cdrom:)/# \1/' /etc/apt/sources.list
if ! grep -rhsE '^(deb |URIs:)' /etc/apt/sources.list /etc/apt/sources.list.d/ | grep -q 'debian'; then
    CODINOME="${VERSION_CODENAME:-trixie}"
    cat > /etc/apt/sources.list.d/debian.sources <<EOF
Types: deb
URIs: http://deb.debian.org/debian
Suites: $CODINOME $CODINOME-updates
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: http://security.debian.org/debian-security
Suites: $CODINOME-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
fi
apt-get update

# -----------------------------------------------------------------------------
say "2/9 Base: login, quiosque, rede, som, fontes, boot gráfico"
# -----------------------------------------------------------------------------
"${APT[@]}" \
    curl gnupg ca-certificates \
    greetd cage xwayland foot \
    python3 python3-gi gir1.2-gtk-4.0 \
    fonts-inter fonts-noto-core fonts-noto-color-emoji \
    gnome-keyring libpam-gnome-keyring libsecret-1-0 dbus-user-session \
    network-manager \
    pipewire pipewire-pulse pipewire-alsa wireplumber alsa-utils \
    plymouth plymouth-themes grub-common \
    intel-microcode firmware-misc-nonfree firmware-amd-graphics

# -----------------------------------------------------------------------------
say "3/9 Wi-Fi Broadcom (Mac mini e outros Macs antigos)"
# -----------------------------------------------------------------------------
if [ "$IMAGEM" = 1 ]; then
    # Na ISO viva o driver vai sempre: ela precisa funcionar em qualquer Mac.
    "${APT[@]}" linux-headers-amd64 broadcom-sta-dkms
elif command -v lspci >/dev/null || "${APT[@]}" pciutils >/dev/null; then
    if lspci -nn | grep -qiE 'network controller.*broadcom'; then
        "${APT[@]}" linux-headers-amd64 broadcom-sta-dkms || \
            echo "Aviso: driver de Wi-Fi não instalado; use cabo e rode o setup de novo."
    fi
fi

# -----------------------------------------------------------------------------
say "4/9 Claude Desktop, do repositório oficial da Anthropic"
# -----------------------------------------------------------------------------
if [ "$IMAGEM" = 1 ]; then
    # A ISO não leva software da Anthropic: o Claude é baixado na máquina de quem instala.
    echo "Modo imagem: o Claude Desktop fica para o pós-instalação."
else
    bash "$AQUI/rootfs/usr/local/sbin/morfo-instalar-claude" || die "não consegui instalar o Claude Desktop"
fi

# -----------------------------------------------------------------------------
say "5/9 Arquivos do Morfo Linux"
# -----------------------------------------------------------------------------
# Arquivo por arquivo, para não herdar dono/permissões das pastas do checkout.
(cd "$AQUI/rootfs" && find . -type f) | while read -r f; do
    case "$f" in
        ./usr/local/bin/*|./usr/local/sbin/*) modo=0755 ;;
        *) modo=0644 ;;
    esac
    install -D -o root -g root -m "$modo" "$AQUI/rootfs/$f" "/${f#./}"
done
mkdir -p /usr/share/morfo/temas
for t in grafite areia; do
    # Cópia recursiva (o tema tem a subpasta plymouth/), sem herdar o dono do checkout.
    install -d -m 0755 "/usr/share/morfo/temas/$t"
    cp -r --no-preserve=ownership,mode "$TEMAS_DIR/$t/." "/usr/share/morfo/temas/$t/"
    chmod -R u=rwX,go=rX "/usr/share/morfo/temas/$t"
done
printf 'Morfo Linux\nbase: %s\n' "$PRETTY_NAME" > /etc/morfo-release

# -----------------------------------------------------------------------------
say "6/9 Tela de login (greetd) e chaveiro destravado no login"
# -----------------------------------------------------------------------------
GREETER_USER=$(awk -F'"' '/^user/ {print $2}' /etc/greetd/config.toml)
id "$GREETER_USER" >/dev/null 2>&1 || GREETER_USER=_greetd
id "$GREETER_USER" >/dev/null 2>&1 || useradd -r -M -s /usr/sbin/nologin -G video,render "$GREETER_USER"
sed -i "s/^user = .*/user = \"$GREETER_USER\"/" /etc/greetd/config.toml

install -d -m 0775 -o root -g "$(id -gn "$GREETER_USER")" /var/lib/morfo
echo "$TEMA" > /var/lib/morfo/tema
chgrp "$(id -gn "$GREETER_USER")" /var/lib/morfo/tema
chmod 0664 /var/lib/morfo/tema

PAM=/etc/pam.d/greetd
if [ -f "$PAM" ] && ! grep -q pam_gnome_keyring "$PAM"; then
    sed -i '/@include common-auth/a auth       optional   pam_gnome_keyring.so' "$PAM"
    sed -i '/@include common-session/a session    optional   pam_gnome_keyring.so auto_start' "$PAM"
fi

systemctl enable greetd.service
systemctl enable morfo-tema.path
systemctl set-default graphical.target
# A tela de login ocupa o terminal 1, logo depois da animação de boot.
# Um console de texto continua em Ctrl+Alt+F2, para manutenção.
systemctl disable getty@tty1.service 2>/dev/null || true

# -----------------------------------------------------------------------------
say "7/9 Cowork: virtualização"
# -----------------------------------------------------------------------------
echo vhost_vsock > /etc/modules-load.d/vhost_vsock.conf
[ "$IMAGEM" = 1 ] || modprobe vhost_vsock 2>/dev/null || true
for u in $(awk -F: '$3 >= 1000 && $3 < 60000 {print $1}' /etc/passwd); do
    usermod -aG kvm,video,render,netdev "$u" 2>/dev/null || usermod -aG kvm "$u"
done
# Usuários criados depois também entram nos grupos.
sed -i -E 's/^#?EXTRA_GROUPS=.*/EXTRA_GROUPS="kvm video render netdev"/; s/^#?ADD_EXTRA_GROUPS=.*/ADD_EXTRA_GROUPS=1/' /etc/adduser.conf 2>/dev/null || true

# -----------------------------------------------------------------------------
say "8/9 Boot em Macs: GRUB no caminho que o firmware da Apple procura"
# -----------------------------------------------------------------------------
if [ "$IMAGEM" = 1 ]; then
    echo "Modo imagem: o GRUB é instalado pelo instalador (Calamares)."
elif [ -d /sys/firmware/efi ] || [ "$INSTALADOR" = 1 ]; then
    echo "grub-efi-amd64 grub2/force_efi_extra_removable boolean true" | debconf-set-selections
    if [ -d /boot/efi/EFI ]; then
        grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable --no-nvram >/dev/null 2>&1 || \
            echo "Aviso: não copiei o GRUB para o caminho removível."
    fi
fi

# -----------------------------------------------------------------------------
say "9/9 Tema $TEMA (boot, login e terminal)"
# -----------------------------------------------------------------------------
MORFO_FORCAR=1 /usr/local/sbin/morfo-tema "$TEMA"

say "Morfo Linux instalado"
if [ "$INSTALADOR" = 0 ] && [ "$IMAGEM" = 0 ]; then
    cat <<EOF

  Reinicie com:  sudo reboot

  Na tela de login: escolha o usuário, digite a senha e o Claude abre em tela cheia.
  - Embaixo dá para trocar o tema e abrir "Configurar Wi-Fi" ou "Terminal".
  - Fechar o Claude volta para a tela de login.
  - Atualizar tudo (inclusive o Claude): sudo apt update && sudo apt upgrade
EOF
fi
