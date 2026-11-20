# Morfo Linux — repassa o teclado do sistema (/etc/default/keyboard) para
# as sessões gráficas. O cage (wlroots) lê o layout das variáveis XKB_DEFAULT_*;
# sem elas, assume o teclado americano.
# Uso: . /usr/local/lib/morfo-teclado.sh
if [ -r /etc/default/keyboard ]; then
    # shellcheck disable=SC1091
    . /etc/default/keyboard
    export XKB_DEFAULT_LAYOUT="${XKBLAYOUT:-us}"
    export XKB_DEFAULT_MODEL="${XKBMODEL:-pc105}"
    export XKB_DEFAULT_VARIANT="${XKBVARIANT:-}"
    export XKB_DEFAULT_OPTIONS="${XKBOPTIONS:-}"
fi
