# A background profile update does not install global commands.
if not type -q fusion-check
    function fusion-check --description 'Check Hyper Fusion plugins'
        /bin/sh "$HOME/.config/hypr/bin/fusion-check" $argv
    end
end
