# Morfo Linux — repassa o teclado para as sessões gráficas. O sway e o cage
# (wlroots) leem o layout das variáveis XKB_DEFAULT_*; sem elas, assumem o
# teclado americano.
# Ordem: escolha feita na Central do Morfo (/var/lib/morfo/teclado), senão o
# teclado do sistema (/etc/default/keyboard).
# Uso: . /usr/local/lib/morfo-teclado.sh
if [ -r /etc/default/keyboard ]; then
    # shellcheck disable=SC1091
    . /etc/default/keyboard
fi
if [ -s /var/lib/morfo/teclado ]; then
    # Formato: layout modelo variante (ex.: "br abnt2 -" ou "us pc105 intl")
    read -r XKBLAYOUT XKBMODEL XKBVARIANT < /var/lib/morfo/teclado
    [ "$XKBVARIANT" = "-" ] && XKBVARIANT=""
fi
export XKB_DEFAULT_LAYOUT="${XKBLAYOUT:-us}"
export XKB_DEFAULT_MODEL="${XKBMODEL:-pc105}"
export XKB_DEFAULT_VARIANT="${XKBVARIANT:-}"
export XKB_DEFAULT_OPTIONS="${XKBOPTIONS:-}"
