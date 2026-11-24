"""Search destinations reuse Control Panel's tool IDs and Fusion Settings pages."""
import json
import shlex

PAGES = [
    ('home','Home','Account and desktop overview','user-home','account dashboard'),
    ('hotkeys','Hotkeys','Keyboard shortcuts and bindings','preferences-desktop-keyboard-shortcuts','keyboard shortcut keys'),
    ('audio','Audio','Devices, application mixer and system sounds','audio-volume-high','sound speaker microphone output input volume startup shutdown notification chimes sound pack system audio'),
    ('network','Network','Wi-Fi and network connections','network-wireless','wifi wireless ethernet internet'),
    ('bluetooth','Bluetooth','Pair and manage Bluetooth devices','preferences-system-bluetooth','pair headphones wireless'),
    ('displays','Displays','Monitor arrangement, brightness, color and HDR','video-display','monitor screen resolution scaling rotation brightness colour color hdr'),
    ('input','Input','Mouse, keyboard and touchpad preferences','input-keyboard','mouse keyboard touchpad repeat sensitivity'),
    ('theme','Theme & wallpaper','Themes, wallpapers and window effects','preferences-desktop-theme','appearance wallpaper video pictures colors focus cursor icons titlebar protection window behavior offscreen'),
    ('context-menu','Context Menu','Desktop and file context menus','view-list-details','right click menu'),
    ('default-apps','Default Apps','Choose which applications open files and links','preferences-desktop-default-applications','browser file association mime'),
    ('calendar','Calendar','Date and calendar preferences','view-calendar','date time clock'),
    ('capture','Recorder','Screen and audio recording','media-record','screenshot capture record video microphone'),
    ('system','Session & power','Session dashboard and power actions','system-shutdown','logout restart reboot shutdown suspend'),
    ('power','Power settings','Persistent CPU, battery and laptop policies','battery','cpu governor boost energy laptop lid battery charge idle suspend'),
    ('phone','Phone','Pair a phone, send files and open messages','smartphone','kde connect sms whatsapp messages android phone share'),
    ('terminal','Terminal','Terminal appearance and welcome screen','utilities-terminal','shell terminal fetch'),
]


def entries(root, entry_type):
    class SearchEntry(entry_type):
        search_target=True
        def get_keywords(self): return self.search_keywords.split()
        def get_categories(self): return 'Settings;'

    result={}
    def add(ident,title,description,icon,keywords,argv,source):
        entry=SearchEntry(ident,None,{'name':title+' · '+source,'description':description,
                'icon':icon,'command':shlex.join([str(a) for a in argv])},custom=True)
        entry.search_keywords=keywords+' '+source
        result[ident]=entry
    for ident,title,description,icon,keywords in PAGES:
        add('fusion-settings:'+ident,title,description,icon,keywords,
            [root/'scripts/control-center.sh','--tab',ident],'Fusion Settings')
    try:
        groups=json.loads((root/'control_panel/tools.json').read_text())
        for group in groups:
            for tool in group['tools']:
                add('fusion-control-panel:'+tool['id'],tool['title'],tool['description'],tool['icon'],
                    tool.get('keywords','')+' '+group['title'],
                    [root/'scripts/control-panel.sh','--section',tool['id']],'Control Panel')
        add('fusion-control-panel:rdp-host','Share this desktop','RDP and VNC hosting in Remote Desktop',
            'preferences-desktop-remote-desktop','rdp vnc remote server hosting incoming share desktop control',
            [root/'scripts/control-panel.sh','--section','rdp-host'],'Control Panel')
    except (OSError,ValueError,KeyError,TypeError):
        pass  # An unavailable tool catalog must not hide installed applications.
    return result
