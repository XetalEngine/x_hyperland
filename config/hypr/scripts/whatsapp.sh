#!/bin/sh
exec python3 "$(dirname -- "$(readlink -f -- "$0")")/../desktop_services/whatsapp.py" "$@"
