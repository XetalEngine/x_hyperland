typeset _fusion_fetch="${ZDOTDIR:h}/model.py"
ZDOTDIR=${XETAL_USER_ZDOTDIR:-$HOME}
# Print before the user's instant-prompt preamble redirects stdout. This keeps
# truecolor detection working and leaves Powerlevel10k's startup quiet.
[[ -o interactive ]] && python3 "$_fusion_fetch"
unset _fusion_fetch
[[ -r $ZDOTDIR/.zshrc ]] && source "$ZDOTDIR/.zshrc"
if [[ -n ${KITTY_INSTALLATION_DIR:-} && ${KITTY_SHELL_INTEGRATION:-} != disabled && -r $KITTY_INSTALLATION_DIR/shell-integration/zsh/kitty-integration ]]; then
    autoload -Uz -- "$KITTY_INSTALLATION_DIR/shell-integration/zsh/kitty-integration"
    kitty-integration
    unfunction kitty-integration
fi
