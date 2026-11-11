"""Original scalable artwork. No fonts, external images or desktop dependencies."""
from pathlib import Path
from xml.sax.saxutils import escape

VERSION = 4
# Name, metal/light, midtone, shadow, face, decorative language.
STYLES = {
    'ghostbusters': ('Ghostbusters', '#e1ff88', '#b4ff00', '#60b800', '#08110f', 'ghostbusters'),
    'leviathan': ('Leviathan', '#eed7b2', '#c6a06c', '#a47ac0', '#17151d', 'leviathan'),
    'polaris': ('Polaris', '#d8f8ff', '#4de5f5', '#a391fa', '#16243c', 'polaris'),
    'infernalencore': ('Infernal Encore', '#f4dfbd', '#d6975b', '#ff472c', '#181414', 'encore'),
    'midnightrun': ('Midnight Run', '#c8faff', '#42e5f5', '#ed38b5', '#111b28', 'neonrun'),
    'mystery98': ('Windows 98 Mystery', '#fff2c9', '#d5ac53', '#806233', '#38271a', 'mystery98'), 'platform95': ('Platform 95', '#fff2c9', '#d5ac53', '#806233', '#38271a', 'platform95'),
    'mycelium': ('Mycelium', '#f1dfc8', '#c7a1df', '#806079', '#322630', 'mycelium'),
    'atomicafterglow': ('Atomic Afterglow', '#eadba5', '#b5ed29', '#687047', '#21281d', 'reactor'),
    'blackwood': ('Blackwood', '#efdbab', '#bc9c61', '#655033', '#292e27', 'walnut'),
    'midnighttransit': ('Midnight Transit', '#f5e5bd', '#ffb239', '#895820', '#0d3036', 'enamel'),
    'hyperfusionblue': ('HyperFusion Blue', '#effaff', '#22bfff', '#0061a9', '#152b3b', 'fusion'),
    'raw': ('Xetal Raw', '#a4fff4', '#41d6ce', '#175e72', '#102c38', 'circuit'),
    'modern': ('Xetal Modern', '#edf6ff', '#86b9ee', '#405d99', '#233b61', 'glass'),
    'breakpoint': ('BreakPoint', '#ffdad6', '#ef485b', '#842839', '#271c27', 'signal'),
    'binaryknife': ('Binary Knife', '#d3f4ff', '#41baff', '#204d9f', '#12233e', 'blade'),
    'tidalglass': ('Tidal Glass', '#f1fff7', '#81e5d9', '#328aaf', '#164a65', 'water'),
    'porcelainink': ('Porcelain Ink', '#fff4dd', '#e8d7ba', '#8d8176', '#383b3c', 'ink'),
    'obsidianforge': ('Obsidian Forge', '#ffe0a4', '#ed9a44', '#8a482b', '#2d2928', 'forge'),
    'candycloud': ('Candy Cloud', '#fff5ff', '#eebce9', '#9a7bb9', '#6a628d', 'cloud'),
    'shadowedge': ('Shadow Edge', '#f0f3f4', '#b0bdc4', '#566571', '#242a33', 'edge'),
    'hollowgrove': ('Hollow Grove', '#e8efe0', '#a8c09d', '#5d7a71', '#263d38', 'leaves'),
    'gildedhollow': ('The Gilded Hollow', '#fff0b7', '#dfb469', '#836137', '#303c32', 'brass'),
}
DESCRIPTIONS = {
    'ghostbusters': 'Slime-green folders, liquid edges and midnight enamel badges.',
    'leviathan': 'Engraved brass folders, obsidian plaques and amethyst details.',
    'polaris': 'Sapphire glass tiles, luminous cyan symbols and violet folder depths.',
    'infernalencore': 'Brass-framed black folders, red symbols and riveted corners.',
    'midnightrun': 'Cyan folder outlines, magenta symbols and graphite silhouettes.',
    'mystery98': 'Brass keys, leather-bound books, parchment folders and emerald glass.', 'platform95': 'Gold file folders, ivory office equipment and classic espresso symbols.',
    'mycelium': 'Sculpted lilac caps, plum folders, ivory roots and moss details.',
    'atomicafterglow': 'Graphite instrument cases, phosphor tabs and brass fasteners.',
    'blackwood': 'Aged-brass folders, walnut cases and engraved ivory symbols.',
    'midnighttransit': 'Teal enamel folders, ivory nickel outlines and amber station details.',
    'hyperfusionblue': 'Sapphire glass folders, silver hardware and polished graphite application tiles.',
    'raw': 'Luminous cyan circuits and precision-cut panels.',
    'modern': 'Frosted blue glass with polished silver edges.',
    'breakpoint': 'Crimson signals, smoked panels and inset indicator lights.',
    'binaryknife': 'Faceted cobalt crystal and sharp electric edges.',
    'tidalglass': 'Sea glass, pearl rims and flowing ocean lines.',
    'porcelainink': 'Ivory paper, brushed ink and tiny vermilion seals.',
    'obsidianforge': 'Riveted basalt, copper bevels and molten seams.',
    'candycloud': 'Soft lilac pillows, pearly highlights and little stars.',
    'shadowedge': 'Brushed silver blades with a fine crimson signature.',
    'hollowgrove': 'Moonlit metal, sage glass and delicate silver leaves.',
    'gildedhollow': 'Engraved brass, moss-dark leather and lantern highlights.',
}
# Canonical names are also the names used in Individual Icons. Aliases share
# artwork and overrides, so a folder keeps its design when opened or selected.
CATALOG = {
    'folder': ('Folder', 'Places', 'folder', ('inode-directory','folder-open','folder-blue','folder-saved-search')),
    'user-home': ('Home', 'Places', 'home', ('folder-home',)),
    'user-desktop': ('Desktop', 'Places', 'desktop', ('folder-desktop',)),
    'folder-documents': ('Documents', 'Places', 'documents', ()),
    'folder-download': ('Downloads', 'Places', 'download', ('folder-downloads',)),
    'folder-pictures': ('Pictures', 'Places', 'pictures', ()),
    'folder-music': ('Music', 'Places', 'music', ()),
    'folder-videos': ('Videos', 'Places', 'video', ()),
    'folder-publicshare': ('Shared folder', 'Places', 'network', ('folder-remote','folder-network')),
    'folder-templates': ('Templates', 'Places', 'documents', ()),
    'folder-favorites': ('Favorites', 'Places', 'star', ('user-bookmarks','bookmarks')),
    'user-trash': ('Trash', 'Places', 'trash', ('user-trash-symbolic',)),
    'user-trash-full': ('Full Trash', 'Places', 'trash-full', ()),
    'computer': ('This PC', 'Devices', 'computer', ('fusion-computer','xetal-files-computer','video-display')),
    'drive-harddisk': ('Internal drive', 'Devices', 'drive', ('drive-harddisk-system','drive-harddisk-solidstate','drive-harddisk-root')),
    'drive-removable-media-usb': ('USB drive', 'Devices', 'usb', ('drive-removable-media','drive-removable','media-flash')),
    'drive-optical': ('Optical disc', 'Devices', 'disc', ('media-optical',)),
    'network-workgroup': ('Network', 'Devices', 'network', ('network-server','network-wired','network')),
    'system-file-manager': ('Fusion Files', 'Apps', 'folder', ('xetal-files','org.kde.dolphin','system-file-manager-symbolic')),
    'utilities-terminal': ('Terminal', 'Apps', 'terminal', ('terminal','org.gnome.Terminal','kitty','Alacritty','org.kde.konsole')),
    'web-browser': ('Browser', 'Apps', 'compass', ('internet-web-browser',)),
    'accessories-text-editor': ('Text editor', 'Apps', 'quill', ('text-editor',)),
    'multimedia-video-player': ('Media player', 'Apps', 'reel', ('applications-multimedia',)),
    'preferences-system': ('Control Panel', 'Apps', 'gear', ('systemsettings','xetal-control-panel','preferences-other','applications-system')),
    'xetal-fusion-settings': ('Fusion Settings', 'Apps', 'sliders', ('preferences-desktop','preferences-desktop-theme','preferences-desktop-icons')),
    'xetal-kvm-settings': ('KVM Settings', 'Apps', 'chip', ('computer-vm','virt-manager')),
    'utilities-system-monitor': ('System monitor', 'Apps', 'monitor', ('org.kde.plasma-systemmonitor','org.gnome.SystemMonitor')),
    'accessories-calculator': ('Calculator', 'Apps', 'calculator', ('xetal-calculator','org.kde.kcalc')),
    'preferences-desktop-wallpaper': ('Wallpapers', 'Apps', 'landscape', ('xetal-wallpaper-browser',)),
    'xetal-launcher': ('Apps menu', 'Apps', 'apps', ('view-app-grid','applications-other','start-here')),
    'system-shutdown': ('Session & power', 'Apps', 'power', ('system-log-out','system-reboot')),
    'text-x-generic': ('Document', 'Files', 'file-text', ('application-x-zerosize','text-plain','text-x-log','unknown')),
    'text-x-script': ('Script / source code', 'Files', 'file-code', ('text-x-python','text-x-csrc','text-x-c++src','text-x-shellscript','application-x-shellscript','application-json','application-javascript','text-html','text-css','application-xml')),
    'application-pdf': ('PDF', 'Files', 'file-pdf', ('application-postscript',)),
    'image-x-generic': ('Image', 'Files', 'file-image', ('image-png','image-jpeg','image-gif','image-svg+xml','image-svg-xml','image-webp','xetal-image-viewer')),
    'audio-x-generic': ('Audio', 'Files', 'file-audio', ('audio-mpeg','audio-flac','audio-x-wav','audio-ogg')),
    'video-x-generic': ('Video', 'Files', 'file-video', ('video-mp4','video-webm','video-x-matroska')),
    'package-x-generic': ('Archive', 'Files', 'archive', ('application-zip','application-x-compressed-tar','application-x-tar','application-x-7z-compressed','application-x-rar','application-gzip','application-x-xz')),
    'application-x-executable': ('Application', 'Files', 'executable', ('application-x-desktop','application-vnd.appimage','application-x-sharedlib')),
}
ALIASES = {alias: key for key, (_, _, _, aliases) in CATALOG.items() for alias in (key, *aliases)}
APPLICATIONS = {
    'xetal-files.desktop':'system-file-manager', 'xetal-files-computer.desktop':'computer',
    'xetal-calculator.desktop':'accessories-calculator', 'xetal-kvm-settings.desktop':'xetal-kvm-settings',
    'xetal-control-panel.desktop':'preferences-system', 'xetal-image-viewer.desktop':'image-x-generic',
    'xetal-wallpaper-browser.desktop':'preferences-desktop-wallpaper',
}


def symbol(kind):
    """Symbols occupy a 64px canvas; sculpted surfaces supply the material."""
    paths = {
        'home':'M17 32 32 19 47 32M21 29V46H29V36H36V46H43V29',
        'desktop':'M17 21H47V40H17ZM26 47H38M32 40V47',
        'documents':'M22 18H37L44 25V47H22ZM36 18V27H44M27 33H39M27 38H39M27 43H35',
        'download':'M32 18V38M24 30 32 39 40 30M19 39V47H45V39',
        'pictures':'M17 22H47V44H17ZM19 41 28 31 36 39 41 34 47 40',
        'music':'M28 39V23L43 19V35M28 29 43 25',
        'video':'M19 20H45V46H19ZM24 20V46M40 20V46M19 27H24M19 39H24M40 27H45M40 39H45M29 28 36 33 29 38Z',
        'network':'M25 18H39V28H25ZM32 28V35M18 35H46M18 35V40M46 35V40M12 40H24V48H12ZM40 40H52V48H40Z',
        'star':'M32 18 36 27 47 28 39 36 41 47 32 42 23 47 25 36 17 28 28 27Z',
        'terminal':'M15 19H49V46H15ZM23 27 29 32 23 37M33 38H41',
        'compass':'M32 15V19M32 45V49M15 32H19M45 32H49M40 23 35 35 23 40 28 28Z',
        'quill':'M18 47 39 20M22 36C21 23 39 15 49 15 46 31 34 42 22 39M27 30 38 30M32 23 42 23M24 40 36 38',
        'sliders':'M20 17V47M32 17V47M44 17V47M16 28H24M28 39H36M40 25H48',
        'chip':'M22 22H42V42H22ZM28 28H36V36H28ZM26 16V22M38 16V22M26 42V48M38 42V48M16 26H22M16 38H22M42 26H48M42 38H48',
        'monitor':'M15 20H49V43H15ZM19 33H25L29 26 33 38 37 30H45M26 49H38M32 43V49',
        'calculator':'M21 16H43V49H21ZM26 21H38V27H26ZM26 34H28M36 34H38M26 40H28M36 40H38M26 45H28M36 45H38',
        'landscape':'M15 20H49V45H15ZM17 42 29 29 36 37 41 32 48 41',
        'apps':'M18 18H28V28H18ZM36 18H46V28H36ZM18 36H28V46H18ZM36 36H46V46H36Z',
        'power':'M32 16V31M23 22A15 15 0 1 0 41 22',
        'file-text':'M24 25H38M24 32H40M24 39H37M24 46H33',
        'file-code':'M27 28 21 34 27 40M37 28 43 34 37 40M34 24 30 44',
        'file-pdf':'M22 41C30 31 30 21 30 22 28 37 42 42 44 38 41 34 24 38 22 41Z',
        'file-image':'M21 25H43V43H21ZM22 41 29 32 35 39 39 34 43 40',
        'file-audio':'M28 39V25L40 22V36M28 29 40 26',
        'file-video':'M21 25H43V43H21ZM29 29 37 34 29 39Z',
        'usb':'M26 13H38V24H26ZM24 24H40V49H24ZM30 17V20M34 17V20M28 30H36',
        'drive':'M18 20H46L51 39V48H13V39ZM14 39H50M20 44H33',
        'trash':'M21 23 23 49H41L43 23M18 23H46M26 22V18H38V22M29 29V43M35 29V43',
        'trash-full':'M21 26 23 49H41L43 26M18 26H46M23 23 26 15 34 19 40 14 44 23M29 32V43M35 32V43',
        'executable':'M24 21 44 32 24 43Z',
    }
    if kind == 'computer': kind = 'desktop'
    if kind == 'archive': return '<path d="M17 22H47V47H17ZM14 17H50V25H14ZM28 25V40H36V25M30 31H34M30 35H34"/>'
    if kind == 'gear':
        return '<path d="m28 16 8 0 1 6 5 3 5-2 4 7-4 4v5l4 3-4 7-5-2-5 3-1 5h-8l-1-5-5-3-5 2-4-7 4-3v-5l-4-4 4-7 5 2 5-3z" transform="translate(0 -3)"/><circle cx="32" cy="32" r="7"/>'
    if kind in ('reel','disc'):
        holes = ''.join(f'<circle cx="{x}" cy="{y}" r="4.5"/>' for x,y in ((26,23),(41,27),(38,41),(23,38))) if kind=='reel' else '<path d="M21 24A14 14 0 0 1 31 18M43 38A14 14 0 0 1 35 46"/>'
        return '<circle cx="32" cy="32" r="18"/><circle cx="32" cy="32" r="2"/>'+holes
    extra = '<circle cx="39" cy="27" r="2"/>' if kind in ('landscape','pictures','file-image') else ''
    if kind in ('music','file-audio'): extra='<ellipse cx="24" cy="41" rx="4" ry="3" fill="url(#metal)"/><ellipse cx="39" cy="37" rx="4" ry="3" fill="url(#metal)"/>'
    return '<path d="'+paths.get(kind, paths['apps'])+'"/>'+extra


def ornament(style, accent):
    if style == 'leaves':
        return '<g fill="url(#metal)" stroke="'+accent+'" stroke-width=".55"><path d="M6 55Q17 56 24 49M9 54Q4 45 8 41 15 47 9 54M13 54Q13 45 20 44 21 51 13 54M17 52Q22 45 27 47 25 53 17 52M49 12Q53 5 58 7 58 13 49 12M51 15Q57 13 60 17 55 21 51 15"/></g>'
    if style == 'brass':
        return '<g fill="url(#metal)" stroke="#493c26" stroke-width=".7"><circle cx="11" cy="12" r="1.6"/><circle cx="53" cy="12" r="1.6"/><circle cx="11" cy="52" r="1.6"/><circle cx="53" cy="52" r="1.6"/><path d="M24 54 32 50 40 54 32 58ZM8 24Q14 27 8 32 14 37 8 40M56 24Q50 27 56 32 50 37 56 40"/></g>'
    if style == 'water': return '<path d="M8 48Q19 41 31 48T57 46M10 52Q24 46 35 51T54 50" fill="none" stroke="'+accent+'" stroke-width="1" opacity=".8"/><circle cx="51" cy="17" r="2.2" fill="#effffa" opacity=".8"/>'
    if style == 'ink': return '<path d="m7 14 10-2m31 40 9-1" stroke="#4b504e" stroke-width="2"/><rect x="46" y="47" width="9" height="9" rx="1" fill="#b5473c"/><path d="M49 49v5m3-5v5m-4-3h5" stroke="#f7dfc3" stroke-width=".7"/>'
    if style == 'cloud': return '<g fill="#fff4ff"><path d="m50 7 1.4 4.5L56 13l-4.6 1.5L50 19l-1.5-4.5L44 13l4.5-1.5ZM10 45l1 3 3 1-3 1-1 3-1-3-3-1 3-1Z"/><circle cx="55" cy="23" r="1.3"/></g>'
    if style == 'forge': return '<g fill="#b47844" stroke="#34291e"><circle cx="12" cy="13" r="2"/><circle cx="52" cy="13" r="2"/><circle cx="12" cy="51" r="2"/><circle cx="52" cy="51" r="2"/></g><path d="m9 45 6 3-2 8M49 8l-2 6 8 4" fill="none" stroke="#f5a149" stroke-width="1"/>'
    if style in ('blade','edge'): return '<path d="m7 21 7-12h14m8 47h16l6-12" fill="none" stroke="'+accent+'" stroke-width="1.6"/><path d="m44 53 10-9" stroke="'+('#db5263' if style=='edge' else '#b1efff')+'" stroke-width="2"/>'
    if style in ('signal','circuit'): return '<path d="M9 18v-7h13M42 54h13v-8" fill="none" stroke="'+accent+'" stroke-width="1"/><g fill="'+accent+'"><rect x="17" y="52" width="7" height="2"/><circle cx="48" cy="13" r="1.4"/><circle cx="53" cy="13" r="1.4"/></g>'
    return '<path d="M14 13Q27 9 41 13" fill="none" stroke="#ffffff" stroke-opacity=".6" stroke-width="1.4"/>'


def svg(style, name):
    if style == 'ghostbusters':
        from .ghostbusters import svg as ghostbusters_svg
        return ghostbusters_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'leviathan':
        from .leviathan import svg as leviathan_svg
        return leviathan_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'infernalencore':
        from .infernalencore import svg as encore_svg
        return encore_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'polaris':
        from .polaris import svg as polaris_svg
        return polaris_svg(name,CATALOG,symbol)
    if style == 'midnightrun':
        from .midnightrun import svg as neon_svg
        return neon_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'mystery98':
        from .mystery98 import svg as mystery98_svg
        return mystery98_svg(ALIASES.get(name,name),CATALOG,symbol)
    elif style == 'platform95':
        from .platform95 import svg as platform95_svg
        return platform95_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'mycelium':
        from .mycelium import svg as mycelium_svg
        return mycelium_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'atomicafterglow':
        from .atomic import svg as atomic_svg
        return atomic_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'blackwood':
        from .blackwood import svg as blackwood_svg
        return blackwood_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'midnighttransit':
        from .transit import svg as transit_svg
        return transit_svg(ALIASES.get(name,name),CATALOG,symbol)
    if style == 'hyperfusionblue':
        from .blue import svg as blue_svg
        return blue_svg(ALIASES.get(name,name),CATALOG,symbol)
    name = ALIASES.get(name, name)
    label, group, shape, _ = CATALOG[name]
    _, light, mid, dark, face, material = STYLES[style]
    folder = shape == 'folder' or group == 'Places' and name.startswith('folder-')
    file = shape.startswith('file-')
    angular = material in ('blade','edge','forge','circuit')
    contour = ('M15 7H49L57 15V49L49 57H15L7 49V15Z' if angular else
               'M17 7H47Q57 7 57 18V46Q57 57 46 57H18Q7 57 7 46V18Q7 7 17 7Z')
    if material == 'water': contour='M17 9Q33 3 49 10 60 17 56 34 59 51 45 56 28 60 13 53 4 44 8 26 6 15 17 9Z'
    if material == 'cloud': contour='M17 8Q32 4 48 9 59 16 57 33 59 50 47 55 31 60 16 55 4 49 7 32 5 15 17 8Z'
    if file: contour='M17 7H38L50 19V56H17ZM38 7V20H50'
    if folder: contour='M7 20V14Q7 11 11 11H26L32 18H53Q57 18 57 23V51Q57 55 53 55H11Q7 55 7 51ZM8 25H56'
    natural=material in ('leaves','brass') and shape in ('compass','quill','gear','reel','disc')
    content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label+' · '+STYLES[style][0])}</title><defs>
<linearGradient id="metal" x1="0" y1="0" x2=".65" y2="1"><stop stop-color="{light}"/><stop offset=".3" stop-color="{mid}"/><stop offset=".53" stop-color="{light}"/><stop offset=".65" stop-color="{mid}"/><stop offset="1" stop-color="{dark}"/></linearGradient>
<linearGradient id="face" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="{mid}" stop-opacity=".58"/><stop offset=".45" stop-color="{face}"/><stop offset="1" stop-color="{face}"/></linearGradient>
<linearGradient id="shine" x1="0" y1="0" x2="0" y2="1"><stop stop-color="white" stop-opacity=".22"/><stop offset="1" stop-color="white" stop-opacity="0"/></linearGradient></defs>
'''
    if natural:
        if shape=='compass':
            content+='<circle cx="32" cy="32" r="23" fill="url(#face)" stroke="url(#metal)" stroke-width="2.2"/><circle cx="32" cy="32" r="19" fill="none" stroke="url(#metal)" stroke-width=".8"/>'
            content+='<g stroke="url(#metal)" stroke-width="1">'+''.join(f'<path d="M32 12v3" transform="rotate({a} 32 32)"/>' for a in range(0,360,30))+'</g>'
            content+='<path d="M32 12 36 27 52 32 36 36 32 52 28 36 12 32 28 28Z" fill="url(#metal)" stroke="'+dark+'" stroke-width=".6"/><path d="M32 17V32L47 32 35 35 32 47V32L17 32 29 29Z" fill="'+face+'" opacity=".8"/><circle cx="32" cy="32" r="3" fill="url(#metal)"/>'
        elif shape=='quill':
            content+='<path d="M12 54Q29 39 49 10 54 6 57 7 54 25 41 36L32 36 36 40 23 44Z" fill="url(#metal)" stroke="'+dark+'" stroke-width="1"/><path d="M12 54Q38 24 55 9M27 38l12-2M33 30l12-2M40 22l10-1M26 38l-1-7M32 31l-2-8" fill="none" stroke="'+face+'" stroke-width=".9"/><path d="M14 55h30" stroke="url(#metal)" stroke-width="1.6"/>'
        elif shape in ('reel','disc'):
            content+='<circle cx="32" cy="31" r="24" fill="url(#metal)" stroke="'+dark+'"/><circle cx="32" cy="31" r="20.5" fill="none" stroke="'+face+'" stroke-width=".7"/>'
            if shape=='reel':content+=''.join(f'<circle cx="{x}" cy="{y}" r="6.8" fill="{face}" stroke="{dark}" stroke-width="1.1"/>' for x,y in ((25,20),(43,24),(39,42),(21,38)))+'<path d="M39 54Q49 58 55 50" stroke="url(#metal)" stroke-width="2" fill="none"/>'
            content+='<circle cx="32" cy="31" r="3.5" fill="'+face+'" stroke="'+light+'" stroke-width=".7"/>'
        else:
            content+='<g transform="translate(-4 -4) scale(1.125)" fill="url(#metal)" stroke="'+dark+'" stroke-width="1">'+symbol(shape)+'</g><circle cx="32" cy="32" r="11" fill="url(#face)" stroke="'+light+'" stroke-width=".7"/><circle cx="32" cy="32" r="7" fill="'+face+'" stroke="url(#metal)" stroke-width="2"/>'
        return content+(ornament(material,mid) if material=='leaves' else '')+'</svg>\n'
    content+=f'''<path d="{contour}" transform="translate(0 1.8)" fill="#061317" opacity=".38"/>
<path d="{contour}" fill="url(#face)" stroke="url(#metal)" stroke-width="1.7" stroke-linejoin="round"/>
<path d="{contour}" transform="translate(4 4) scale(.875)" fill="none" stroke="{light}" stroke-width=".65" opacity=".35"/>
'''
    if material == 'brass': content+='<path d="M15 18Q32 14 49 18M15 46Q32 50 49 46" fill="none" stroke="#b99a5d" stroke-width=".6" opacity=".3"/>'
    if folder:
        content+='<path d="M9 27H55L51 49H13Z" fill="url(#shine)"/>'
        if shape != 'folder': content+='<g transform="translate(10 11) scale(.69)" fill="none" stroke="url(#metal)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>'
        else: content+='<path d="M28 33H36V40H28ZM31 35V38" fill="url(#metal)" stroke="'+dark+'" stroke-width=".8"/>'
    else:
        content+='<g fill="none" stroke="'+dark+'" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" transform="translate(0 .8)">'+symbol(shape)+'</g>'
        content+='<g fill="none" stroke="url(#metal)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>'
    content+=ornament(material, mid)
    return content+'</svg>\n'


def build(root=None):
    root = Path(root or Path(__file__).parent/'packs')
    for style, (label,*_) in STYLES.items():
        target=root/('Xetal-System-'+style); icons=target/'scalable';icons.mkdir(parents=True,exist_ok=True)
        (target/'index.theme').write_text(f'[Icon Theme]\nName={label}\nComment={DESCRIPTIONS[style]}\nDirectories=scalable\n\n[scalable]\nSize=64\nType=Scalable\nMinSize=16\nMaxSize=512\n')
        for name, (_,_,_,aliases) in CATALOG.items():
            image=svg(style,name)
            for alias in (name,*aliases):
                (icons/(alias+'.svg')).write_text(image)


if __name__ == '__main__': build()
