# Profile-local interactive Bash features. Never sourced for command-only shells.
# The account's .bashrc has already run, including its aliases and prompt.
[[ $- == *i* && -t 0 && -t 1 && -z ${BASH_EXECUTION_STRING-} ]] || return 0
[[ ${TERM:-dumb} != dumb ]] || return 0
_fusion_terminal_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! _fusion_terminal_options=$(python3 "$_fusion_terminal_dir/preferences.py" shell); then
    unset _fusion_terminal_options _fusion_terminal_dir
    return 0
fi
# The generator emits only validated, shell-quoted assignments from a fixed schema.
eval "$_fusion_terminal_options"
unset _fusion_terminal_options

HISTSIZE=$FUSION_HISTORY_SIZE
HISTFILESIZE=$FUSION_HISTORY_SIZE
HISTFILE=$FUSION_HISTORY_FILE
shopt -s histappend cmdhist
[[ $FUSION_HISTORY_IGNORE_SPACE == 1 ]] && HISTCONTROL=ignorespace || HISTCONTROL=
if [[ $FUSION_HISTORY_IGNORE_DUPLICATES == 1 ]]; then
    HISTCONTROL=${HISTCONTROL:+$HISTCONTROL:}ignoredups
fi
[[ $FUSION_HISTORY_ENABLED == 1 ]] && set -o history || set +o history

function _fusion_history_guard {
    local previous_status=$? next_generation
    if [[ $FUSION_HISTORY_ENABLED != 1 ]]; then
        HISTFILE=
        return "$previous_status"
    fi
    if IFS= read -r next_generation < "$FUSION_HISTORY_ROOT/generation" &&
       [[ $next_generation =~ ^[a-f0-9]{32}$ && $next_generation != "$FUSION_HISTORY_GENERATION" ]]; then
        # history is ble.sh's wrapper when loaded, so its suggestion cache clears too.
        history -c
        FUSION_HISTORY_GENERATION=$next_generation
        HISTFILE=$FUSION_HISTORY_ROOT/$next_generation/commands.bash
        [[ -r $HISTFILE ]] && history -r "$HISTFILE"
    fi
    return "$previous_status"
}

function _fusion_history_prompt {
    local previous_status=$?
    _fusion_history_guard
    if [[ $FUSION_HISTORY_ENABLED == 1 && $FUSION_HISTORY_SHARE == 1 && -f $HISTFILE ]]; then
        history -a
        history -n
    fi
    return "$previous_status"
}

function _fusion_history_before_add {
    # ble.sh adds history before PREEXEC. Switch generations first so the first
    # command after Clear is retained and cannot be appended to the retired file.
    _fusion_history_guard
    return 0
}

# Prepend without flattening Bash's array form or replacing the user's prompt.
PROMPT_COMMAND=(_fusion_history_prompt "${PROMPT_COMMAND[@]}")
bind 'set completion-ignore-case on'
[[ $FUSION_COMPLETION_IGNORE_CASE == 1 ]] || bind 'set completion-ignore-case off'
bind 'set show-all-if-ambiguous on'
bind 'set colored-stats on'
bind 'set colored-completion-prefix on'
bind '"\e[A": history-search-backward'
bind '"\e[B": history-search-forward'

if [[ $FUSION_ENHANCED == 1 ]] && mkdir -p -- "${XDG_CACHE_HOME:-$HOME/.cache}/blesh"; then
    if [[ ! ${BLE_VERSION-} ]]; then
        source "$_fusion_terminal_dir/vendor/blesh/ble.sh" --attach=none --rcfile "$_fusion_terminal_dir/blerc"
    fi
    if [[ ${BLE_VERSION-} ]]; then
        source "$_fusion_terminal_dir/blerc"
        blehook ADDHISTORY!=_fusion_history_before_add
        # Guard before executing commands (including exit) as well as at prompts.
        blehook PREEXEC!=_fusion_history_guard
        blehook EXIT!=_fusion_history_guard
    fi
fi
if [[ ! ${BASH_COMPLETION_VERSINFO-} ]]; then
    source "$_fusion_terminal_dir/vendor/bash-completion/bash_completion"
fi
if [[ $FUSION_KEYMAP == vi ]]; then set -o vi; else set -o emacs; fi
[[ ${BLE_VERSION-} && $FUSION_ENHANCED == 1 ]] && ble-attach
unset _fusion_terminal_dir
