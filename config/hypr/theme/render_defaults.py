#!/usr/bin/env python3
"""Render the packaged theme for a fresh profile without contacting a desktop."""
import argparse
import configparser
import importlib
import io
import json
from pathlib import Path
import backend
import bar_styles
import designs
import runtime
import update_widget


def render(asset_root):
    root=runtime.ROOT.parent;state=runtime.state();design=state['design'];mode=state['mode']
    colors=runtime.colors(mode,design);style=bar_styles.resolve(state.get('bar_style','follow'),design)
    variation=bar_styles.variant(state.get('bar_variant'),style)
    scheme=backend.kde_colors(mode,design)
    (root/'theme/current.colors').write_text(scheme)
    (root/'theme/kitty-colors.conf').write_text(backend.kitty_colors(mode,design))
    config=configparser.ConfigParser(interpolation=None,strict=False);config.optionxform=str
    config.read(root/'dolphin/config/kdeglobals')
    palette=configparser.ConfigParser(interpolation=None);palette.optionxform=str;palette.read_string(scheme)
    for section in palette.sections():
        if section.startswith(('Colors:','ColorEffects:')):config[section]=dict(palette[section])
    if 'General' not in config:config['General']={}
    config['General']['ColorScheme']='Xetal'+design.title()+mode.title()
    out=io.StringIO();config.write(out,space_around_delimiters=False)
    (root/'dolphin/config/kdeglobals').write_text(out.getvalue().rstrip()+'\n')
    bar=runtime.stylesheet((runtime.ROOT/'waybar-dark.css').read_text(),mode,design,qt=False)
    if style!='raw':bar+=designs.waybar_style(colors,style)
    bar+=bar_styles.stylesheet(colors,style,root=Path(asset_root),variation=variation)
    (root/'waybar/style.css').write_text(update_widget.attach(bar))
    (root/'waybar/updates.css').write_text(update_widget.style(colors))
    path=root/'waybar/config.json'
    path.write_text(json.dumps(bar_styles.configure(json.loads(path.read_text()),style,variation),indent=2)+'\n')
    css='/* Profile-local notification colors. */\n'
    for name,key in [('cc-bg','Window'),('noti-bg','Window'),('noti-bg-hover','Button'),
                     ('text-color','Text'),('text-color-disabled','Disabled'),('noti-border-color','Midlight')]:
        css+='@define-color '+name+' '+colors[key]+';\n'
    if design!='raw':css+=designs.notification_style(colors,design)
    (root/'swaync/style.css').write_text(css.rstrip()+'\n')
    path=root/'control_center/theme.conf'
    content='# Managed by Hyprland Theme; only this compositor inherits these values.\n'
    content+='\n'.join(line for line in path.read_text().splitlines() if line.startswith('env ='))+'\n'
    content+=importlib.import_module(design).compositor(colors)
    path.write_text(content)
    (root/'hyprlock.conf').write_text(backend.modern_lock(colors,design))
    startup=(root/'theme/startup-raw.conf').read_text()
    (root/'startup/kitty.conf').write_text(startup+'\n'+backend.kitty_colors(mode,design))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root',required=True)
    render(parser.parse_args().asset_root)
