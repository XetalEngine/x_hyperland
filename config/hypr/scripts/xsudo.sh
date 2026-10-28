#!/usr/bin/env bash
# Temporary root access to this display; passwords stay in sudo's askpass pipe.
set -euo pipefail
if (( $# == 0 )); then printf 'Usage: xsudo.sh command [arguments...]\n' >&2; exit 2; fi
sudo_options=()
if [[ ! -t 0 && -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
    export SUDO_ASKPASS="$HOME/.config/hypr/scripts/sudo-askpass.sh"
    sudo_options+=(--askpass)
fi
if [[ -z ${DISPLAY:-} ]]; then exec sudo "${sudo_options[@]}" -- "$@"; fi

display_access=$(LC_ALL=C xhost)
revoke_root=0
cleanup() {
    if (( revoke_root )); then xhost -SI:localuser:root >/dev/null; fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ ! $display_access =~ (^|$'\n')SI:localuser:root($|$'\n') ]]; then
    xhost +SI:localuser:root >/dev/null
    revoke_root=1
fi
sudo "${sudo_options[@]}" --preserve-env=DISPLAY,XAUTHORITY -- "$@"
