#!/usr/bin/env python3
"""Hyper Fusion's GTK setup. Opens before PyQt/PyGObject are installed."""
import ctypes as C
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
from string import Template

from gtk_ui import GTK
import install
import runtime_install

CSS = b'''
window { background: #10191f; color: #e5f1f8; font-family: Sans; font-size: 14px; }
#sidebar { background-image: linear-gradient(150deg, #153d52, #102330, #131c2c); padding: 30px; }
#brand { font-size: 30px; font-weight: bold; color: #f2faff; }
#eyebrow { font-size: 11px; font-weight: bold; color: #56d5ff; letter-spacing: 2px; }
#steps { color: #a9cbdc; font-size: 13px; }
#title { font-size: 29px; font-weight: bold; color: #f3faff; }
#copy { color: #a4bdcc; }
#card { background: #182c38; border: 1px solid #284858; border-radius: 12px; padding: 18px; }
#error { color: #ffba9d; }
#footer { border-top: 1px solid #263c48; padding-top: 16px; }
button { background: #20323e; color: #e6f5ff; border: 1px solid #355264;
         border-radius: 8px; padding: 10px 18px; box-shadow: none; text-shadow: none; }
button:hover { background: #294656; border-color: #54c7fa; }
button:disabled { color: #6c8290; background: #192730; border-color: #243742; }
button:focus { outline: 2px solid #9ce7ff; outline-offset: 2px; }
#primary { background: #37baff; color: #071c28; border-color: #7ad8ff; font-weight: bold; }
#primary:hover { background: #73d4ff; }
#primary:disabled { background: #192730; color: #6c8290; border-color: #243742; }
checkbutton { color: #dcecf7; padding: 8px 0; }
check { background: #14232e; border: 1px solid #60859b; border-radius: 4px; }
check:checked { background: #37baff; color: #071c28; }
progressbar trough { background: #20333f; border-radius: 6px; min-height: 10px; }
progressbar progress { background: #48caff; border-radius: 6px; min-height: 10px; }
textview, textview text { background: #0a1218; color: #bcd4e3; font-size: 11px; }
expander { color: #a4bdcc; }
'''


def cpu_count():
    try: return len(os.sched_getaffinity(0))
    except (AttributeError, OSError): return os.cpu_count() or 1


def failure_message(lines):
    # The build summary is printed again after recovery, followed by its compiler
    # output. Keep that summary visible instead of the last traceback line.
    for line in reversed(lines):
        if line.startswith(('Installation stopped:', 'Build failed:')):
            return line[:500]
    return next((line[-350:] for line in reversed(lines) if line.strip()),
                'Setup stopped. See installation details.')


class Wizard:
    def __init__(self, update=False):
        self.update = update
        self.target = runtime_install.policy.manifest()
        self.actual = runtime_install.policy.installed()
        self.revision = install.source_revision()
        self.temporary = tempfile.TemporaryDirectory(prefix='xetal-setup-')
        self.g = g = GTK()
        if not g.init_check(None, None): raise RuntimeError('Open Setup inside a graphical desktop session, or use --cli.')
        provider = g.css_provider_new(); g.css_provider_load_from_data(provider, CSS, len(CSS), None)
        g.style_context_add_provider_for_screen(g.gdk_screen_get_default(), provider, 600)
        self.window = g.window_new(0); g.window_set_title(self.window, b'Hyper Fusion / Setup')
        g.window_set_default_size(self.window, 980, 680); g.window_set_position(self.window, 1)
        g.connect(self.window, 'delete-event', self.close, close=True)
        outer = g.box_new(0, 0); g.container_add(self.window, outer)
        sidebar = self.box(outer, spacing=20, name='sidebar'); g.widget_set_size_request(sidebar, 215, -1)
        self.label(sidebar, 'XETAL DESKTOP', 'eyebrow')
        self.label(sidebar, 'HYPER\nFUSION', 'brand')
        artwork = Path(self.temporary.name)/'arch.svg'
        artwork.write_text(Template((install.PAYLOAD/'terminal_fetch/assets/arch-neon.svg').read_text()).substitute(
            accent='#48caff', bright='#d6f5ff', deep='#23465c'))
        pixbuf = g.pixbuf.gdk_pixbuf_new_from_file_at_scale(str(artwork).encode(), 170, 155, 1, None)
        if pixbuf:
            icon = g.image_new_from_pixbuf(pixbuf); g.obj.g_object_unref(pixbuf)
            g.box_pack_start(sidebar, icon, 0, 0, 0)
        self.steps = self.label(sidebar, '', 'steps')
        space = self.box(sidebar); g.widget_set_vexpand(space, 1)
        self.label(sidebar, 'Made for your workspace.', 'copy')
        self.label(sidebar, 'Source '+self.revision[:8], 'copy')
        main = self.box(outer, spacing=18, expand=True); g.container_set_border_width(main, 32)
        self.stack = g.stack_new(); g.stack_set_transition_type(self.stack, 1); g.box_pack_start(main, self.stack, 1, 1, 0)
        self.pages = []
        page = self.page('Your desktop.\nA little extraordinary.', 'A complete workspace, built for your machine.')
        self.label(page, 'Animated workspaces. Beautiful themes. A control panel that\nputs your desktop, devices and virtual machines within reach.', 'copy')
        card = self.box(page, spacing=8, name='card')
        self.label(card, 'ONE TESTED FOUNDATION', 'eyebrow')
        self.label(card, 'Hyprland '+self.target['hyprland']+'  ·  Cube + Burn')
        self.label(card, 'The same compositor used on the development desktop.\nSetup builds the effects and tools against its matching headers.', 'copy')
        page = self.page('Make yourself at home.', 'Setup adapts to your monitors and your account.')
        card = self.box(page, spacing=8, name='card')
        self.label(card, 'COMPOSITOR', 'eyebrow')
        self.label(card, 'Detected '+self.actual['version']+'   →   Required '+self.target['hyprland'])
        self.label(card, 'Setup installs the tested version and holds its package.\nFuture desktop releases manage changes to this requirement.', 'copy')
        if runtime_install.policy.fedora_host():
            self.label(card, 'Fedora 44: includes signed packages from giperborey/Hyprland (COPR).\nThe matching libraries are held too; no third-party repository is enabled.', 'copy')
        self.startup = g.check_button_new_with_label(b'Keep my existing desktop and startup preferences' if update else
                                                   b'Show the animated dashboard when I sign in')
        g.toggle_button_set_active(self.startup, 1); g.box_pack_start(page, self.startup, 0, 0, 0)
        if update:
            self.label(page, 'Uncheck to use the current desktop and startup defaults.\nYour existing profile will be backed up.', 'copy')
        self.label(page, 'Desktop and build dependencies are installed as needed.\nAn administrator password may be requested in a separate window.\nKVM components download separately from KVM Settings.', 'copy')
        page = self.page('Ready when you are.', 'Review your setup, then let us handle the rest.')
        card = self.box(page, spacing=12, name='card')
        self.review = self.label(card, '')
        self.label(page, 'Your current desktop is backed up before replacement.\nThe finished desktop starts at your next Hyprland login.', 'copy')
        page = self.page('Building your workspace.', 'You can follow each step here.', spacing=12)
        self.status = self.label(page, 'Preparing…')
        self.progress = g.progress_bar_new(); g.box_pack_start(page, self.progress, 0, 0, 8)
        self.detail_caption = self.label(page, 'Package setup → Build → Validate → Install', 'copy')
        self.expander = g.expander_new(b'Installation details'); g.box_pack_start(page, self.expander, 1, 1, 0)
        g.widget_set_vexpand(self.expander, 1); g.expander_set_expanded(self.expander, 1)
        self.log_scroll = scroll = g.scrolled_window_new(None, None); g.scrolled_window_set_policy(scroll, 1, 1)
        g.widget_set_size_request(scroll, -1, 260); g.widget_set_vexpand(scroll, 1)
        g.container_add(self.expander, scroll)
        self.log_view = g.text_view_new(); g.text_view_set_editable(self.log_view, 0)
        g.widget_set_vexpand(self.log_view, 1)
        g.text_view_set_monospace(self.log_view, 1); g.text_view_set_wrap_mode(self.log_view, 2)
        self.log_buffer = g.text_view_get_buffer(self.log_view); g.container_add(scroll, self.log_view)
        page = self.page('Your next login starts here.', 'Your workspace is ready.')
        self.complete = self.label(page, '', 'copy')
        self.error = self.label(main, '', 'error')
        # The complete diagnostic stays in the scrollable log; a long summary
        # must not push Retry/Close below a small laptop display.
        g.label_set_ellipsize(self.error, 3); g.label_set_lines(self.error, 3)
        footer = self.box(main, vertical=False, spacing=10, name='footer')
        self.cancel = self.button(footer, 'Cancel', self.close)
        spacer = self.box(footer); g.widget_set_hexpand(spacer, 1)
        self.back = self.button(footer, 'Back', self.previous)
        self.next = self.button(footer, 'Get started', self.advance, 'primary')
        self.busy = False; self.index = 0; self.events = queue.Queue(); self.lines = []; self.success = False
        self.cancel_file = Path(self.temporary.name)/'cancel'
        self.log_path = Path.home()/'.local/state/xetal-hyprland/setup.log'
        self.show(0)
        callback = C.CFUNCTYPE(C.c_int, C.c_void_p)(lambda _: self.poll())
        g.callbacks.append(callback); g.glib.g_timeout_add(100, callback, None)
        g.widget_show_all(self.window)

    def box(self, parent, vertical=True, spacing=0, expand=False, name=None):
        box = self.g.box_new(1 if vertical else 0, spacing)
        if name: self.g.widget_set_name(box, name.encode())
        self.g.box_pack_start(parent, box, expand, expand, 0)
        return box

    def label(self, parent, text, name=None):
        widget = self.g.label_new(text.encode()); self.g.label_set_xalign(widget, 0)
        self.g.label_set_line_wrap(widget, 1); self.g.label_set_max_width_chars(widget, 64)
        if name: self.g.widget_set_name(widget, name.encode())
        self.g.box_pack_start(parent, widget, 0, 0, 0)
        return widget

    def button(self, parent, text, action, name=None):
        widget = self.g.button_new_with_label(text.encode())
        if name: self.g.widget_set_name(widget, name.encode())
        self.g.box_pack_start(parent, widget, 0, 0, 0); self.g.connect(widget, 'clicked', action)
        return widget

    def page(self, title, subtitle, spacing=20):
        page = self.g.box_new(1, spacing)
        self.label(page, title, 'title'); self.label(page, subtitle, 'copy')
        self.g.stack_add_named(self.stack, page, str(len(self.pages)).encode()); self.pages.append(page)
        return page

    def show(self, index):
        self.index = index; g = self.g
        g.stack_set_visible_child_name(self.stack, str(index).encode())
        g.widget_set_sensitive(self.back, index in (1, 2)); g.widget_set_sensitive(self.next, index != 3)
        g.button_set_label(self.next, {0:b'Get started', 2:b'Install desktop', 3:'Installing…'.encode(), 4:b'Finish'}.get(index, b'Continue'))
        g.button_set_label(self.cancel, b'Stop after this step' if index == 3 else b'Close' if index == 4 else b'Cancel')
        names = ('Welcome', 'Your setup', 'Review', 'Install', 'Ready')
        text = '\n\n'.join('<b>●  '+name+'</b>' if i == index else '○  '+name for i, name in enumerate(names))
        g.label_set_markup(self.steps, text.encode()); g.widget_grab_focus(self.next)

    def previous(self):
        if not self.busy and self.index in (1, 2): self.show(self.index-1)

    def advance(self):
        if self.busy: return
        if self.index == 4: self.close(); return
        if self.index == 1:
            selected = bool(self.g.toggle_button_get_active(self.startup))
            preferences = ('Keep existing desktop and startup preferences' if selected else
                           'Use current desktop and startup defaults') if self.update else (
                           'Startup dashboard: on' if selected else 'Startup dashboard: off')
            text = ('Desktop folder\n'+str(Path.home()/'.config/hypr')+'\n\nHyprland '+self.target['hyprland']+
                    '  ·  Cube and Burn included\nUse all '+str(cpu_count())+' available CPU threads for compilation\n\n'+
                    preferences+'\n\nSource '+self.revision[:8])
            self.g.label_set_text(self.review, text.encode())
        if self.index == 2:
            self.busy = True; self.lines = []; self.cancel_file.unlink(missing_ok=True)
            self.g.widget_set_sensitive(self.cancel, 1); self.g.label_set_text(self.error, b'')
            self.g.progress_bar_set_fraction(self.progress, 0.03); self.show(3)
            selected = bool(self.g.toggle_button_get_active(self.startup))
            self.preserve_preferences = self.update and selected
            # Resetting an existing desktop restores its startup default too.
            self.startup_enabled = self.update or selected
            threading.Thread(target=self.worker, daemon=True).start()
        else: self.show(self.index+1)

    def worker(self):
        try:
            if self.preserve_preferences:
                args = [sys.executable, str(install.REPO/'installer/update.py'), '--revision', self.revision,
                        '--manual', '--runtime', '--activate', '--cancel-file', str(self.cancel_file)]
            else:
                args = [sys.executable, str(install.REPO/'installer/install.py'), '--yes', '--cancel-file', str(self.cancel_file)]
                if not self.startup_enabled: args.append('--no-startup')
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open('w') as log:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                           start_new_session=True,
                                           env={**os.environ, 'XETAL_SETUP_GUI':'1', 'PYTHONUNBUFFERED':'1'})
                for line in process.stdout:
                    log.write(line); log.flush(); self.events.put(('line', line.rstrip()))
                code = process.wait()
            self.events.put(('done', code))
        except Exception as error:
            self.events.put(('line', str(error))); self.events.put(('done', 1))

    def poll(self):
        while not self.events.empty():
            event, value = self.events.get()
            if event == 'line':
                self.lines.append(value); self.lines = self.lines[-500:]
                text = '\n'.join(self.lines).encode(); self.g.text_buffer_set_text(self.log_buffer, text, len(text))
                prefixes = ('Required desktop', 'Downloading ', 'Package command:', 'Building ', 'Built ', 'Checking Hyprland', 'Validating ', 'Installed.', 'Ready.')
                if value.startswith(prefixes):
                    self.g.label_set_text(self.status, value[:150].encode())
                    fraction = .2 if value.startswith('Package') else .4 if value.startswith('Building') else .8 if value.startswith('Built') else .9 if value.startswith(('Checking','Validating')) else .1
                    self.g.progress_bar_set_fraction(self.progress, fraction)
            else:
                self.busy = False; self.success = value == 0; self.g.widget_set_sensitive(self.cancel, 1)
                if self.success:
                    message = ('Hyprland '+self.target['hyprland']+' and your desktop are installed.\n\n'
                               'Log out, then select Hyprland and sign in again.\nYour Cube, effects and desktop tools will start together.\n\n'
                               'Installation log: '+str(self.log_path))
                    self.g.label_set_text(self.complete, message.encode()); self.show(4)
                else:
                    self.g.label_set_text(self.error, failure_message(self.lines).encode())
                    self.g.label_set_text(self.status, ('Setup stopped. Details: '+str(self.log_path)).encode())
                    self.g.expander_set_expanded(self.expander, 1)
                    self.g.widget_set_sensitive(self.back, 0); self.g.widget_set_sensitive(self.next, 1)
                    self.g.button_set_label(self.next, b'Retry'); self.g.button_set_label(self.cancel, b'Close')
                    self.index = 2
        return 1

    def close(self):
        if self.busy:
            self.cancel_file.touch(); self.g.widget_set_sensitive(self.cancel, 0)
            self.g.label_set_text(self.status, b'Stopping after the current package or build step finishes...')
        else:
            self.g.main_quit()
        return 1


def main(update=False):
    if os.geteuid() == 0: raise RuntimeError('Open Setup as your desktop user, without sudo.')
    app = Wizard(update=update)
    signal.signal(signal.SIGINT, lambda *_: app.close())
    signal.signal(signal.SIGTERM, lambda *_: app.close())
    try: app.g.main()
    finally: app.temporary.cleanup()
    return 0 if app.success else 1
