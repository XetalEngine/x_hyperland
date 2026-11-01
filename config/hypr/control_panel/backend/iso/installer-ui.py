#!/usr/bin/env python3
"""Mouse and keyboard restore wizard for Hyper Fusion's System ISO.

The shell owns device discovery, validation and all writes. This process only
returns a supplied menu tag, a confirmation, or a read-only checksum result.
Exit 10 means return to Actions; exit 2 asks the shell to use dialog instead.
The read-only preview uses sample devices and never discovers or writes disks.
"""
import argparse
import base64
import curses
import functools
import json
import locale
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import installer_account
import installer_mouse

console_mouse = None


BACK = 10
UNAVAILABLE = 2
ACTIONS = {
    "wipe": ("Install ISO — Erase Full Disk", "Install your snapshot on a whole drive",
             "Restore the snapshot onto a whole drive. The selected drive will "
             "be erased and recreated with a new ext4 filesystem.",
             "Choose drive", "Review target", "Confirm restore"),
    "verify": ("Check snapshot", "Optional check",
               "Check the snapshot against its SHA-256 checksum. This reads "
               "the installation media and does not change any target disk.",
               "Read snapshot", "Compare checksum", "View result"),
    "free": ("Use free space", "Keep partitions",
             "Create new Linux and EFI partitions in an unused region of a "
             "GPT disk. Existing partitions are kept.",
             "Choose free region", "Review layout", "Confirm restore"),
    "parts": ("Use partitions", "Pick ROOT + EFI",
              "Restore into prepared partitions. Only the selected ROOT and "
              "dedicated EFI partition will be formatted.",
              "Choose ROOT + EFI", "Review layout", "Confirm restore"),
}
ASCII_LOGO = (
    "X   X EEEEE TTTTT  AAA  L      EEEEE N   N  GGGG  III N   N EEEEE",
    " X X  E       T   A   A L      E     NN  N G       I  NN  N E",
    "  X   EEEE    T   AAAAA L      EEEE  N N N G  GG   I  N N N EEEE",
    " X X  E       T   A   A L      E     N  NN G   G   I  N  NN E",
    "X   X EEEEE   T   A   A LLLLL  EEEEE N   N  GGGG  III N   N EEEEE",
)
# The compact wordmark is used when the supplied ASCII art cannot fit in full.
# Full blocks are part of the standard Linux console font; no image renderer
# or unusual Unicode glyphs are needed. Every letter has an explicit gutter.
LOGO_GLYPHS = {
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "N": ("#   #", "##  #", "##  #", "# # #", "#  ##", "#  ##", "#   #"),
    "G": (" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"),
}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def clean(text):
    """Device labels are text, never terminal commands or dialog markup."""
    text = re.sub(r"\\Z[0-9bBrRuUnN]", "", text.replace("\\n", "\n"))
    return "".join(c for c in ANSI.sub("", text)
                   if c == "\n" or not unicodedata.category(c).startswith("C"))


def clip(text, width):
    result, cells = [], 0
    for char in text:
        n = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        if cells + n > width:
            break
        result.append(char)
        cells += n
    return "".join(result)


def lines(text, width):
    return [line for paragraph in clean(text).splitlines()
            for line in (textwrap.wrap(paragraph, max(1, width)) or [""])]


@functools.lru_cache(maxsize=8)
def logo(width, height, utf8):
    artwork = ascii_logo()
    if artwork and len(artwork) <= height and max(map(len, artwork)) <= width:
        # Keep the original characters and spacing, including the descender.
        # The wordmark fades from red through yellow to green; its tail is green.
        shades = (9, 9, 1, 3, 11, 11, 10, 2, 2, 2, 2)
        return [[(c, shades[min(i, len(shades) - 1)], False) for c in row]
                for i, row in enumerate(artwork)]
    if utf8 and width >= 68 and height >= 7:
        shades = (9, 1, 3, 11, 2, 10, 2)
        rows = ["    ".join(" ".join(LOGO_GLYPHS[c][row] for c in word)
                            for word in ("XETAL", "ENGINE")) for row in range(7)]
        scale = 2 if width >= len(rows[0]) * 2 else 1
        return [[("\u2588" if c == "#" else " ", shades[i], False)
                 for c in row for _ in range(scale)] for i, row in enumerate(rows)]
    if width >= 65 and height >= 5:
        return [[(c, (1, 1, 3, 2, 2)[i], True) for c in row] for i, row in enumerate(ASCII_LOGO)]
    return [[(c, 2, True) for c in "XETAL ENGINE"[:width]]]


@functools.lru_cache(maxsize=1)
def ascii_logo():
    try:
        return Path(__file__).with_name("installer-logo.txt").read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return []


def print_logo(width, height, colors):
    """Keep shell fallback branding aligned with the restore wizard."""
    utf8 = "UTF-8" in locale.getencoding().upper().replace("UTF8", "UTF-8")
    if not utf8 or colors < 8:
        print("HYPER FUSION"[:max(1,width)])
        return
    for row in emblem(min(22,width), min(11,height), colors):
        text=' '*max(0,(width-len(row))//2)
        for char,fg,bg in row:
            if colors>=256:text+=f'\x1b[38;5;{fg};48;5;{bg}m'+char
            else:text+=f'\x1b[{30+fg%8};{40+bg%8}m'+char
        print(text+'\x1b[0m')


@functools.lru_cache(maxsize=12)
def emblem(width, height, colors):
    """Render the transparent PNG as terminal cells, including on a Linux VT."""
    if height < 3: return []
    # A Linux VT has only eight base colors, and its font may not contain
    # half-block glyphs. Quantizing a shaded PNG there produces a broken mark.
    # Use a deliberately drawn, symmetric silhouette with ordinary characters.
    if colors < 256:
        art = ['          /\\', '         /  \\', '        /    \\',
               '       /      \\', '      /   /\\   \\', '     /   /  \\   \\',
               '    /   /    \\   \\', '   /___/      \\___\\', '', '         ARCH']
        return [[(c, 6, 0) for c in row[:width]] for row in art[:height]]
    image = Path(__file__).with_name('logo.png')
    if not image.exists(): image = Path(__file__).with_name('installer-logo.png')
    try:
        output = subprocess.run(['chafa', '--format=symbols', '--symbols=vhalf',
            '--colors='+('256' if colors >= 256 else '16'), '--size='+str(width)+'x'+str(height),
            '--bg=#101820', '--animate=off', '--polite=on', '--probe=off', '--optimize=0', str(image)],
            capture_output=True, text=True, timeout=3, check=True).stdout
        fg, bg, result = 7, 234 if colors >= 256 else 0, []
        for line in output.splitlines()[:height]:
            row = []
            for part in re.split(r'(\x1b\[[0-9;]*m)', line):
                if part.startswith('\x1b['):
                    codes = [int(n or 0) for n in part[2:-1].split(';')]
                    i=0
                    while i<len(codes):
                        c=codes[i]
                        if c in (38,48) and codes[i+1:i+2]==[5] and i+2<len(codes):
                            if c==38:fg=codes[i+2]
                            else:bg=codes[i+2]
                            i+=2
                        elif 30<=c<=37:fg=c-30
                        elif 90<=c<=97:fg=c-90+8
                        elif 40<=c<=47:bg=c-40
                        elif 100<=c<=107:bg=c-100+8
                        elif c==39:fg=7
                        elif c==49:bg=234 if colors>=256 else 0
                        elif c==0:fg,bg=7,234 if colors>=256 else 0
                        i+=1
                else: row.extend((c,fg,bg) for c in clean(part))
            result.append(row[:width])
        if result:return result
    except (OSError,subprocess.SubprocessError):pass
    # Pre-rendered from the same transparent PNG for desktop previews without
    # chafa. The live ISO always carries chafa for terminal-specific rendering.
    if colors >= 256:
        try:
            cells=json.loads(Path(__file__).with_name('installer-logo.cells.json').read_text())
            return [row[:width] for row in cells[:height]]
        except (OSError,ValueError):pass
    art=['       /\\','      /  \\', '     / /\\ \\', '    / /  \\ \\', '   /_/    \\_\\', '      ARCH']
    return [[(c,6,0) for c in row[:width]] for row in art[:height]]


def png_logo(position=None):
    """Full transparent PNG in Kitty; Linux VTs use the colored-cell emblem."""
    if os.environ.get('TERM') != 'xterm-kitty' or not os.isatty(1): return
    identity=1900000000+os.getpid()%1000000
    sequence=f'\x1b_Ga=d,d=I,i={identity},q=2\x1b\\'
    if position:
        y,x,width,height=position
        path=Path(__file__).with_name('logo.png')
        if not path.exists():path=Path(__file__).with_name('installer-logo.png')
        if path.is_file():
            name=base64.b64encode(os.fsencode(path)).decode('ascii')
            sequence+=f'\x1b7\x1b[{y+1};{x+1}H\x1b_Ga=T,t=f,f=100,i={identity},q=2,C=1,c={width},r={height};{name}\x1b\\\x1b8'
    sys.stdout.write(sequence);sys.stdout.flush()


class Palette:
    def __init__(self):
        self.colors = curses.COLORS if curses.has_colors() else 0
        self.pairs = {}
        self.bg = 233 if self.colors >= 256 else 0
        self.panel = 234 if self.colors >= 256 else 0
        self.raised = 236 if self.colors >= 256 else 0
        self.fg = 252 if self.colors >= 256 else 7
        self.muted = 245 if self.colors >= 256 else 7
        self.accent = 75 if self.colors >= 256 else 6
        self.warning = 215 if self.colors >= 256 else 3

    def attr(self, fg=None, bg=None, bold=False, reverse=False):
        attr = curses.A_BOLD if bold else 0
        if reverse:
            attr |= curses.A_REVERSE
        if not self.colors:
            return attr
        fg = self.fg if fg is None else fg
        bg = self.bg if bg is None else bg
        if fg >= self.colors:
            fg %= 8
            attr |= curses.A_BOLD
        if bg >= self.colors: bg %= 8
        key = (fg, bg)
        if key not in self.pairs:
            number = len(self.pairs) + 1
            if number >= curses.COLOR_PAIRS:
                return attr
            curses.init_pair(number, fg, bg)
            self.pairs[key] = number
        return attr | curses.color_pair(self.pairs[key])


class InstallerUI:
    def __init__(self, screen, args):
        self.screen, self.args = screen, args
        self.palette = Palette()
        self.utf8 = "UTF-8" in locale.getencoding().upper().replace("UTF8", "UTF-8")
        self.actions = ["wipe", "verify"] + (["free", "parts"] if args.uefi else [])
        self.items = list(zip(args.items[::2], args.items[1::2]))
        if args.kind == "home":
            self.actions = [tag for tag, _ in self.items if tag in ACTIONS]
        self.mode = args.mode if args.mode in self.actions else self.actions[0]
        self.index = self.actions.index(self.mode) if args.kind == "home" else 0
        self.button = 0  # Every confirmation starts on Back, never on approval.
        self.scroll = 0
        self.max_scroll = 0
        self.page = 1
        self.result = ""
        self.hits = []
        self.pressed = None
        self.focus = 'list'
        self.user_index = 0
        self.error = ''
        self.account_focus = 'username'
        self.fields = {'username': '', 'password': '', 'confirm': ''}
        self.carets = dict.fromkeys(self.fields, 0)
        self.users = []
        self.reserved_names = set()
        if args.kind == 'account':
            account_file = Path(args.clone_dir)/'accounts.tsv'
            if account_file.is_file(): self.users = installer_account.accounts(account_file)
            elif args.dummy: self.users = [dict(name='fusion', uid=1000, gid=1000, home='/home/fusion')]
            reserved = Path(args.clone_dir)/'account-names.txt'
            if reserved.is_file(): self.reserved_names = set(reserved.read_text().splitlines())
        self.progress_state = '0'
        self.progress_text = 'Preparing your installation…'
        self.preview_started = time.monotonic()

    def put(self, y, x, text, attr=0, width=None):
        rows, cols = self.screen.getmaxyx()
        if not 0 <= y < rows or not 0 <= x < cols - 1:
            return
        text = clean(text).replace("\n", " ")
        if not self.utf8:
            text = text.encode("ascii", "replace").decode("ascii")
        text = clip(text, min(cols - x - 1, width if width is not None else cols))
        try:
            self.screen.addstr(y, x, text, attr)
        except curses.error:
            # A resize can occur between measuring and drawing a cell.
            pass

    def fill(self, y, x, h, w, bg):
        for row in range(y, y + max(0, h)):
            self.put(row, x, " " * max(0, w), self.palette.attr(bg=bg))

    def paragraph(self, y, x, text, width, limit, attr):
        wrapped = lines(text, width)
        for i, line in enumerate(wrapped[:max(0, limit)]):
            self.put(y + i, x, line, attr, width)
        return min(len(wrapped), max(0, limit))

    def hit(self, y, x, height, width, action):
        self.hits.append((y, x, height, width, action))

    def button_at(self, y, x, label, action, active=False):
        p = self.palette
        text = '  '+label+'  '
        fg, bg = (0, p.accent) if active and p.colors else (p.fg, p.raised)
        self.put(y, x, text, p.attr(fg, bg, bold=True, reverse=active and not p.colors))
        self.hit(y, x, 1, len(text), action)

    def draw(self):
        p = self.palette
        rows, cols = self.screen.getmaxyx()
        self.hits = []
        logo_position=None
        self.screen.bkgd(' ', p.attr()); self.screen.erase()
        if cols < 40 or rows < 20 or (self.args.kind == 'account' and (cols < 70 or rows < 24)):
            self.put(1, 2, 'HYPER FUSION', p.attr(p.accent, bold=True))
            self.put(3, 2, 'Make this terminal larger to continue.')
            self.put(5, 2, 'Account setup needs 70 x 24; other pages need 40 x 20.')
            self.put(7, 2, 'Esc: back / exit')
            self.screen.refresh(); png_logo(); return False
        width = min(cols-4, 150); x = (cols-width)//2
        self.put(1, x, 'HYPER FUSION  /  SYSTEM RESTORE', p.attr(p.accent, bold=True), width)
        badge = 'PREVIEW · no disk changes' if self.args.dummy else ('UEFI' if self.args.uefi else 'BIOS')
        if width > 80: self.put(1, x+width-len(badge), badge, p.attr(p.muted))
        if width > 80: self.put(2, x+width-30, 'Snapshot: '+self.args.snapshot, p.attr(p.muted), 30)
        step = {'home': 0, 'menu': 1, 'account': 2, 'confirm': 3, 'verify': 0, 'progress': 4, 'message': 5}[self.args.kind]
        if self.args.kind == 'progress' and self.progress_state in ('done','failed'): step = 5
        labels = ['Welcome', 'Your drive', 'Your account', 'Review', 'Install', 'Done']
        y, height = 4, rows-8
        self.split = width >= 100 and rows >= 30
        if self.split:
            left = 26
            self.fill(y, x, height, left, p.panel)
            art = emblem(22, min(11, height-17), p.colors) if height >= 25 else []
            if art and os.environ.get('TERM')=='xterm-kitty' and os.isatty(1):
                logo_position=(y+1,x+2,22,len(art))
            else:
                for i, row in enumerate(art):
                    for j, (char, fg, bg) in enumerate(row):
                        self.put(y+1+i, x+2+j, char, p.attr(fg, bg))
            start = y+len(art)+2
            self.put(start, x+2, 'YOUR WORKSPACE.', p.attr(p.muted, p.panel), left-4)
            for i, label in enumerate(labels):
                active = i == step
                self.put(start+2+i*2, x+2, f'{i+1:02d}  '+label,
                         p.attr(p.accent if active else p.muted, p.panel, bold=active), left-4)
            self.content = (y, x+left+2, height, width-left-2)
        else:
            self.put(2, x, f'STEP {step+1} / 6  ·  '+labels[step], p.attr(p.muted), width)
            self.content = (y, x, height, width)
        cy,cx,ch,cw = self.content
        self.fill(cy,cx,ch,cw,p.panel)
        if self.args.kind == 'home': self.draw_home(cy,cx,ch,cw)
        elif self.args.kind == 'menu': self.draw_menu(cy,cx,ch,cw)
        elif self.args.kind == 'account': self.draw_account(cy,cx,ch,cw)
        elif self.args.kind == 'progress': self.draw_progress(cy,cx,ch,cw)
        else: self.draw_text(cy,cx,ch,cw)
        footer = rows-3
        busy = self.args.kind == 'verify' or (self.args.kind == 'progress' and self.progress_state not in ('done','failed'))
        if not busy:
            back = 'Exit' if self.args.kind == 'home' else 'Back'
            if self.args.kind not in ('message','progress'):
                active = self.button == 0 if self.args.kind == 'confirm' else self.focus == 'back'
                self.button_at(footer,x,back,'back',active)
            next_label = self.args.accept if self.args.kind == 'confirm' else ('Done' if self.args.kind in ('message','progress') else 'Next →')
            active = self.button == 1 if self.args.kind == 'confirm' else self.focus != 'back'
            self.button_at(footer,x+width-len(next_label)-4,next_label,'next',active)
        self.put(rows-1,x,'Click to choose · Tab / arrows to navigate · Enter to continue',p.attr(p.muted),width)
        self.screen.refresh(); png_logo(logo_position)
        if console_mouse:console_mouse.draw_pointer(rows,cols)
        return True

    def draw_home(self,y,x,height,width):
        p=self.palette
        self.put(y+1,x+2,'Your system. A fresh start.',p.attr(bg=p.panel,bold=True),width-4)
        self.put(y+3,x+2,'Choose how to restore your snapshot.',p.attr(p.muted,p.panel),width-4)
        self.put(y+4,x+2,'ACTIONS',p.attr(p.muted,p.panel),width-4)
        step=3 if height>=20 else 2
        self.page=max(1,(height-7)//step)
        first=max(0,self.index-self.page+1)
        for i in range(first,min(len(self.actions),first+self.page)):
            tag=self.actions[i]
            row=y+6+(i-first)*step
            if row>=y+height-1:break
            active=i==self.index
            fg,bg=(0,p.accent) if active and p.colors else (p.fg,p.raised)
            self.put(row,x+2,' '*(width-4),p.attr(fg,bg))
            self.put(row,x+3,('● ' if active else '○ ')+ACTIONS[tag][0],p.attr(fg,bg,bold=active),width-6)
            self.hit(row,x+2,step,width-4,('select',i))
            if step==3:self.put(row+1,x+5,ACTIONS[tag][1],p.attr(p.muted,p.panel),width-8)

    def draw_menu(self, y, x, height, width):
        p = self.palette
        self.put(y + 1, x + 2, clean(self.args.title).strip().upper(), p.attr(p.accent, p.panel), width - 4)
        used = self.paragraph(y + 3, x + 2, self.args.text, width - 4, min(3, max(1, height - 7)), p.attr(p.muted, p.panel))
        start = y + 4 + used
        step = 3 if height >= 20 else 2
        self.page = max(1, (y + height - start - 2) // step)
        first = max(0, self.index - self.page + 1)
        for i in range(first, min(len(self.items), first + self.page)):
            tag, description = self.items[i]
            # Keep capacity and model visible even when filesystem labels are
            # long. The confirmation screen shows the complete metadata.
            if " | " in description:
                labels, model = description.rsplit(" | ", 1)
                description = f"{model}  /  {labels}"
            row = start + (i - first) * step
            selected = i == self.index
            fg, bg = (0, p.accent) if selected and p.colors else (p.fg, p.raised if selected else p.panel)
            a = p.attr(fg, bg, bold=selected, reverse=selected and not p.colors)
            self.put(row, x + 1, " " * (width - 2), a)
            self.put(row, x + 2, ("> " if selected else "  ") + tag, a, width - 4)
            self.hit(row, x + 1, step, width - 2, ("select", i))
            self.put(row + 1, x + 4, description, p.attr(p.fg if selected else p.muted, p.panel), width - 6)
        self.put(y + height - 1, x + 2, f"{self.index + 1} / {len(self.items)}   Select a drive, then Next", p.attr(p.muted, p.panel), width - 4)

    def draw_text(self, y, x, height, width):
        p = self.palette
        warning = self.args.kind == "confirm"
        self.put(y + 1, x + 2, clean(self.args.title).strip().upper(), p.attr(p.warning if warning else p.accent, p.panel, bold=True), width - 4)
        text = lines(self.args.text, width - 4)
        self.page = max(1, height - 7)
        self.max_scroll = max(0, len(text) - self.page)
        self.scroll = min(self.scroll, self.max_scroll)
        for i, line in enumerate(text[self.scroll:self.scroll + self.page]):
            self.put(y + 3 + i, x + 2, line, p.attr(bg=p.panel), width - 4)
        if self.max_scroll:
            self.put(y + height - 4, x + 2, f"Text {self.scroll + 1}-{min(len(text), self.scroll + self.page)} / {len(text)}   Up/Down to scroll", p.attr(p.muted, p.panel), width - 4)
        if self.args.kind == "verify":
            return

    def draw_account(self,y,x,height,width):
        p=self.palette
        self.put(y+1,x+2,'Make it yours.',p.attr(bg=p.panel,bold=True),width-4)
        self.put(y+3,x+2,'Create a new administrator account.',p.attr(p.fg,p.panel),width-4)
        user=self.users[self.user_index]['name'] if self.users else 'No regular accounts in this snapshot'
        self.put(y+5,x+2,'Desktop from: '+user+('  ‹ ›' if len(self.users)>1 else ''),p.attr(p.accent if self.account_focus=='user' else p.muted,p.panel),width-4)
        self.hit(y+5,x+2,1,width-4,('field','user'))
        for offset,(key,label) in enumerate([('username','Username'),('password','New password'),('confirm','Confirm password')]):
            row=y+7+offset*2
            self.put(row,x+2,label,p.attr(p.fg,p.panel),18)
            value=self.fields[key] if key=='username' else '•'*len(self.fields[key])
            if not value:value='Choose a new password' if key=='password' else ('Repeat new password' if key=='confirm' else 'Choose a new username')
            active=self.account_focus==key
            attr=p.attr(p.fg,p.raised,reverse=active)
            self.put(row,x+21,' '*(width-24),attr)
            self.put(row,x+22,value[-max(1,width-26):],attr,width-26)
            self.hit(row,x+20,1,width-22,('field',key))
        note=self.error or 'New username and password required. Any password strength. Files and desktop transfer to your new account.'
        self.paragraph(y+height-3,x+2,note,width-4,2,p.attr(p.warning if self.error else p.muted,p.panel))

    def draw_progress(self,y,x,height,width):
        p=self.palette
        title={'done':'Welcome home.', 'failed':'Installation needs attention.'}.get(self.progress_state,'Building your workspace.')
        self.put(y+1,x+2,title,p.attr(bg=p.panel,bold=True),width-4)
        self.paragraph(y+3,x+2,self.progress_text,width-4,4,p.attr(p.warning if self.progress_state=='failed' else p.fg,p.panel))
        stages=['Prepare drive','Create filesystems','Restore files','Account preferences','Make bootable','Finish']
        stage=int(self.progress_state) if self.progress_state.isdecimal() else (6 if self.progress_state=='done' else 0)
        if height>=17:
            for i,label in enumerate(stages):
                self.put(y+8+i,x+3,('✓ ' if i<stage else '· ')+label,p.attr(p.accent if i<stage else p.muted,p.panel),width-6)
        count=max(1,width-6);filled=count*min(stage,6)//6
        self.put(y+height-2,x+3,'━'*filled,p.attr(p.accent,p.panel),count)
        self.put(y+height-2,x+3+filled,'─'*(count-filled),p.attr(p.raised,p.panel),count-filled)

    def accept(self):
        kind=self.args.kind
        if kind=='confirm':return 0 if self.button==1 else BACK
        if kind=='account':
            try:
                plan=installer_account.choice(self.users,self.user_index,self.fields['username'],self.fields['password'],self.fields['confirm'],self.reserved_names)
                self.result=json.dumps(plan)
                self.fields['password']=self.fields['confirm']=''
                return 0
            except (ValueError,IndexError,OSError,subprocess.SubprocessError) as error:
                self.error=str(error);return None
        if kind in ('home','menu'):
            self.result=self.actions[self.index] if kind=='home' else self.items[self.index][0]
        if kind=='progress' and self.progress_state not in ('done','failed'):return None
        return 0

    def mouse(self, event=None):
        try:_,mx,my,_,state=event if event is not None else curses.getmouse()
        except curses.error:return None
        if state & curses.BUTTON4_PRESSED:return self.handle(curses.KEY_UP)
        if state & getattr(curses,'BUTTON5_PRESSED',0):return self.handle(curses.KEY_DOWN)
        target=next((action for y,x,h,w,action in self.hits if y<=my<y+h and x<=mx<x+w),None)
        if state & curses.BUTTON1_PRESSED:
            self.pressed=target
            return None
        if state & curses.BUTTON1_RELEASED:
            pressed,self.pressed=self.pressed,None
            if target is None or pressed!=target:return None
        if not state & (curses.BUTTON1_CLICKED|curses.BUTTON1_RELEASED):return None
        for y,x,h,w,action in reversed(self.hits):
            if not (y<=my<y+h and x<=mx<x+w):continue
            if action=='back':return 1 if self.args.kind=='home' else BACK
            if action=='next':
                self.button=1
                return self.accept()
            if action[0]=='select':
                self.index=action[1];self.focus='list'
                if self.args.kind=='home':self.mode=self.actions[self.index]
            elif action[0]=='field':
                self.account_focus=action[1]
                if action[1]=='user' and len(self.users)>1:
                    self.user_index=(self.user_index+1)%len(self.users)
                    self.fields.update(username='',password='',confirm='')
                elif action[1] in self.fields:self.carets[action[1]]=len(self.fields[action[1]])
            break
        return None

    def account_key(self,key):
        fields=(['user'] if len(self.users)>1 else [])+['username','password','confirm','back','next']
        current=self.account_focus
        if key in (9,curses.KEY_BTAB,curses.KEY_DOWN,curses.KEY_UP):
            i=fields.index(current) if current in fields else 0
            self.account_focus=fields[(i+(-1 if key in (curses.KEY_BTAB,curses.KEY_UP) else 1))%len(fields)]
            self.focus='back' if self.account_focus=='back' else 'next'
            if self.account_focus in self.fields:self.carets[self.account_focus]=len(self.fields[self.account_focus])
        elif current=='user' and key in (32,10,13,curses.KEY_LEFT,curses.KEY_RIGHT) and self.users:
            self.user_index=(self.user_index+1)%len(self.users)
            self.fields.update(username='',password='',confirm='')
        elif key in (10,13):return BACK if current=='back' else self.accept()
        elif current in self.fields:
            value=self.fields[current];pos=min(self.carets[current],len(value))
            if key in (curses.KEY_BACKSPACE,127,8):
                if pos:value=value[:pos-1]+value[pos:];pos-=1
            elif key==curses.KEY_DC:value=value[:pos]+value[pos+1:]
            elif key==curses.KEY_LEFT:pos=max(0,pos-1)
            elif key==curses.KEY_RIGHT:pos=min(len(value),pos+1)
            elif key==curses.KEY_HOME:pos=0
            elif key==curses.KEY_END:pos=len(value)
            elif key==21:value='';pos=0
            elif 32<=key<=0x10ffff and chr(key).isprintable():
                char=chr(key).lower() if current=='username' else chr(key)
                value=value[:pos]+char+value[pos:];pos+=len(char)
            self.fields[current]=value;self.carets[current]=pos;self.error=''
        return None
    def handle(self, key, usable=True):
        if isinstance(key,str):key=ord(key)
        if self.args.kind=='progress' and self.progress_state not in ('done','failed'):return None
        if key == 27 or (key==ord('q') and self.args.kind!='account'):
            if self.args.kind == "message":
                return 0
            return 1 if self.args.kind == "home" else BACK
        if not usable:
            return None
        if key==curses.KEY_MOUSE:return self.mouse()
        if self.args.kind=='account':return self.account_key(key)
        up, down = key in (curses.KEY_UP, ord("k")), key in (curses.KEY_DOWN, ord("j"))
        enter = key in (10, 13, curses.KEY_ENTER)
        if self.args.kind in ("home", "menu"):
            count = len(self.actions) if self.args.kind == "home" else len(self.items)
            if up or down:
                self.index = (self.index + (1 if down else -1)) % count
            elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                self.index = min(count - 1, max(0, self.index + (self.page if key == curses.KEY_NPAGE else -self.page)))
            elif key in (curses.KEY_HOME, curses.KEY_END):
                self.index = 0 if key == curses.KEY_HOME else count - 1
            elif self.args.kind == "menu" and key == curses.KEY_LEFT:
                return BACK
            elif key in (9,curses.KEY_BTAB):
                order=['list','back','next'];self.focus=order[(order.index(self.focus)+(1 if key==9 else -1))%3]
            elif enter or (self.args.kind == "home" and key == curses.KEY_RIGHT):
                if self.focus=='back':return 1 if self.args.kind=='home' else BACK
                return self.accept()
            if self.args.kind == "home":
                self.mode = self.actions[self.index]
        else:
            if up or down:
                self.scroll = min(self.max_scroll, max(0, self.scroll + (1 if down else -1)))
            elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                self.scroll = min(self.max_scroll, max(0, self.scroll + (self.page if key == curses.KEY_NPAGE else -self.page)))
            elif self.args.kind == "confirm" and key in (9, curses.KEY_BTAB, curses.KEY_LEFT, curses.KEY_RIGHT):
                self.button = 1 - self.button
            elif enter:
                return self.accept()
        return None

    def verify(self):
        self.args.title = "Checking snapshot"
        self.args.text = "Reading the complete snapshot and comparing its SHA-256 checksum.\n\nThis may take several minutes. No disks are being changed."
        self.draw()
        process = None
        outcome = "failed"
        try:
            clone = Path(self.args.clone_dir)
            if (clone / "snapshot.sha256").is_file() and (clone / "rootfs-snapshot.tar.zst").is_file():
                process = subprocess.Popen(["sha256sum", "--check", "--strict", "snapshot.sha256"], cwd=clone,
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.screen.timeout(150)
                while process.poll() is None:
                    key = self.screen.getch()
                    if key in (27, ord("q")):
                        outcome = "cancelled"
                        break
                    if key == curses.KEY_RESIZE:
                        self.draw()
                else:
                    outcome = "passed" if process.returncode == 0 else "failed"
        except OSError:
            pass
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            self.screen.timeout(-1)
        self.args.kind = "message"
        self.args.title = "Snapshot check " + outcome
        self.args.text = {
            "passed": "Snapshot integrity check passed.\n\nThe snapshot matches its checksum. Return to Actions to choose an installation mode.",
            "failed": "The snapshot could not be verified.\n\nInstallation is blocked until a check passes. Recreate the ISO or installation media if the problem persists.",
            "cancelled": "The check was cancelled. The previous integrity status is unchanged.\n\nNo disks were changed.",
        }[outcome]
        if outcome != "cancelled":
            self.args.snapshot = outcome
        self.result = outcome

    def run(self):
        self.screen.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        curses.set_escdelay(40)
        curses.mouseinterval(0)
        native_mouse=console_mouse is not None and console_mouse.fd>=0
        if not native_mouse:curses.mousemask(curses.ALL_MOUSE_EVENTS)
        if self.args.kind == "confirm":
            curses.flushinp()  # Do not carry Enter/typeahead across warnings.
        if self.args.kind == "verify":
            self.verify()
        # Kitty can finish its initial terminal-mode switch after the first
        # frame. Refresh once when idle so the PNG survives that switch, then
        # block normally instead of continuously repainting an idle menu.
        warmup=True
        self.screen.timeout(50 if native_mouse else 100 if self.args.kind=='progress' else 150)
        redraw=True
        while True:
            if self.args.kind=='progress':
                if self.args.progress_file:
                    try:
                        record=Path(self.args.progress_file).read_text().split('\n',1)
                        if len(record)==2:self.progress_state,self.progress_text=record
                    except OSError:pass
                elif self.args.dummy:
                    stage=min(6,int((time.monotonic()-self.preview_started)/.45))
                    self.progress_state=str(stage) if stage<6 else 'done'
                    self.progress_text='Preview only. Your disks and accounts are unchanged.' if stage==6 else 'Simulating the restore steps…'
                redraw=True
            if redraw:usable = self.draw();redraw=False
            try:key=self.screen.get_wch()
            except curses.error:
                event=console_mouse.read() if native_mouse else None
                if event is not None:
                    status=self.mouse(event) if usable else None
                    if status is not None:return status
                    redraw=True
                if warmup:
                    warmup=False
                    redraw=True
                    if self.args.kind!='progress' and not native_mouse:self.screen.timeout(-1)
                continue
            redraw=True
            status = self.handle(key, usable)
            if status is not None:
                return status


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("home", "menu", "confirm", "message", "verify", "logo", "account", "progress", "preview"))
    parser.add_argument("--mode", choices=tuple(ACTIONS), default="wipe")
    parser.add_argument("--uefi", action="store_true")
    parser.add_argument("--dummy", action="store_true")
    parser.add_argument("--snapshot", default="not checked")
    parser.add_argument("--clone-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--title", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--accept", default="Continue")
    parser.add_argument("--width", type=int, default=110)
    parser.add_argument("--height", type=int, default=11)
    parser.add_argument("--colors", type=int, default=0)
    parser.add_argument('--progress-file',default='')
    parser.add_argument("items", nargs="*")
    args = parser.parse_args(argv)
    if args.kind in ("home", "menu") and (not args.items or len(args.items) % 2):
        parser.error("menus need tag/description pairs")
    if args.kind == "home" and not any(tag in ACTIONS for tag in args.items[::2]):
        parser.error("no supported actions")
    return args


def preview(screen, args):
    """Exercise the actual wizard widgets with sample data and no disk tools."""
    stages=['home','menu','account','confirm','confirm','progress']
    index=0;mode='wipe';drive='Preview SSD';account='Keep existing accounts and passwords.'
    while True:
        kind=stages[index]
        options=argparse.Namespace(**vars(args));options.kind=kind;options.dummy=True;options.uefi=True;options.mode=mode
        options.items=[]
        if kind=='home':options.items=['wipe',ACTIONS['wipe'][0],'free','Use free space','parts','Use partitions']
        if kind=='menu':
            options.title='Choose your drive';options.text='Sample drives for this preview. Nothing will be erased.'
            options.items=['Preview SSD','1 TB · Fusion NVMe · sample drive','Preview USB','256 GB · USB SSD · sample drive']
        if kind=='confirm':
            options.title='Ready to restore?' if index==4 else 'Review your choices'
            options.text='Target: '+drive+'\n\n'+account+'\n\nThis is a design preview. Real restores show the selected drive and exactly what will be erased.\n\nYour disks, files and accounts are unchanged.'
            options.accept='Confirm preview' if index==4 else 'Next →'
        ui=InstallerUI(screen,options);status=ui.run()
        if status in (BACK,1):
            if index==0:return 0
            index-=1;continue
        if kind=='home':mode=ui.result
        if kind=='menu':drive=ui.result
        if kind=='account':
            plan=json.loads(ui.result)
            account='New administrator: '+plan['username']+'. New login and sudo password. Desktop inherited from '+plan['original']+'.'
        if index==len(stages)-1:return 0
        index+=1


def main(argv=None):
    global console_mouse
    args = arguments(argv)
    if os.environ.get('XETAL_INSTALLER_SOCKET') and args.kind != 'logo':
        import installer_protocol
        try:
            answer = installer_protocol.request(os.environ['XETAL_INSTALLER_SOCKET'], vars(args))
            if answer.get('status') == 0 and answer.get('result'):
                print(answer['result'])
            return answer['status']
        except (OSError, ValueError, RuntimeError) as error:
            # An interrupted graphical confirmation is never an approval or
            # a request to fall through to another frontend.
            print('Installer interface disconnected: '+str(error), file=sys.stderr)
            return 1
    if args.kind == "logo":
        print_logo(args.width, args.height, args.colors)
        return 0
    if not os.isatty(0) or os.environ.get("TERM", "dumb") == "dumb":
        return UNAVAILABLE
    try:
        locale.setlocale(locale.LC_ALL, "")
        tty = os.open(os.ttyname(0), os.O_RDWR | os.O_NOCTTY)
    except (OSError, locale.Error):
        return UNAVAILABLE
    result_fd = os.dup(1)
    console_mouse = installer_mouse.ConsoleMouse()
    try:
        # stdout is normally a Bash command substitution. Draw only on the TTY;
        # send the selected tag, and nothing else, back through the original fd.
        sys.stdout.flush()
        os.dup2(tty, 1)
        ui = None

        def run(screen):
            nonlocal ui
            if args.kind=='preview':return preview(screen,args)
            ui = InstallerUI(screen, args)
            return ui.run()

        status = curses.wrapper(run)
        if status == 0 and ui is not None and ui.result:
            os.write(result_fd, (ui.result + "\n").encode("utf-8"))
        return status
    except KeyboardInterrupt:
        return 130
    except (curses.error, OSError, ValueError):
        return UNAVAILABLE
    finally:
        console_mouse.close()
        png_logo()
        os.dup2(result_fd, 1)
        os.close(result_fd)
        os.close(tty)


if __name__ == "__main__":
    sys.exit(main())
