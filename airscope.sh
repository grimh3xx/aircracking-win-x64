#!/usr/bin/env bash
# Atalho pra rodar o airscope sem instalar. Uso: ./airscope.sh [--demo] [--wordlist PATH]
# Modo real precisa de root; reexecuta com sudo se necessario (a menos que --demo).
cd "$(dirname "$0")" || exit 1
for a in "$@"; do [ "$a" = "--demo" ] && DEMO=1; done
if [ -z "$DEMO" ] && [ "$(id -u)" -ne 0 ]; then
    exec sudo python3 -m airscope "$@"
fi
exec python3 -m airscope "$@"
