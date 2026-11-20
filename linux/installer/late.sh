#!/bin/sh
# Morfo Linux — último passo do instalador (roda no ambiente do d-i, busybox).
# Copia o Morfo para o sistema novo e roda o setup.sh dentro dele.

TEMA=$(sed -n 's/.*morfo_tema=\([a-z]*\).*/\1/p' /proc/cmdline)
[ -n "$TEMA" ] || TEMA=grafite

mkdir -p /target/opt/morfo
cp -r /cdrom/morfo/. /target/opt/morfo/

if in-target bash /opt/morfo/setup.sh --instalador "$TEMA" > /target/var/log/morfo-setup.log 2>&1; then
    exit 0
fi

# Falhou (quase sempre: sem internet). O Debian fica instalado; dá para
# terminar depois com um comando.
cat > /target/etc/motd <<'EOF'

  O Morfo Linux não terminou de instalar (veja /var/log/morfo-setup.log).
  Conecte a internet (cabo de rede) e rode:

      sudo bash /opt/morfo/setup.sh

EOF
exit 0
