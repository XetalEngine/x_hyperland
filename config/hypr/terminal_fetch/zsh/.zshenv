# Respect the user's startup configuration while keeping the Fusion rc wrapper local.
typeset _fusion_zdotdir=$ZDOTDIR
ZDOTDIR=${XETAL_USER_ZDOTDIR:-$HOME}
[[ -r $ZDOTDIR/.zshenv ]] && source "$ZDOTDIR/.zshenv"
export XETAL_USER_ZDOTDIR=$ZDOTDIR
ZDOTDIR=$_fusion_zdotdir
unset _fusion_zdotdir
