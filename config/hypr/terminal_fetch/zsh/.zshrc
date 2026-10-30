typeset _fusion_fetch="${ZDOTDIR:h}/model.py"
ZDOTDIR=${XETAL_USER_ZDOTDIR:-$HOME}
[[ -r $ZDOTDIR/.zshrc ]] && source "$ZDOTDIR/.zshrc"
[[ -o interactive ]] && python3 "$_fusion_fetch"
unset _fusion_fetch
