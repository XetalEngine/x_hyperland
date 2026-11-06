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

from gtk_ui import GTK, TextIter
import install
import runtime_install
import login_setup

LOGIN_WARNING = '''Changing the login service can leave you at a text console if setup fails.

Changes: /etc/xetal-fusion-login/; /etc/pam.d/greetd; /etc/polkit-1/rules.d/49-xetal-fusion-login.rules; /etc/systemd/system/{display-manager.service,default.target,xetal-fusion-login.service} and their enablement links; /usr/local/lib/xetal-fusion-login/.
Existing /etc/greetd/config.toml and /etc/X11/default-display-manager are backed up. Fusion's previous getty@tty1.service.d/99-xetal-autologin.conf and marked ~/.zprofile block are backed up and removed if present. A temporary /run/systemd/system/greetd.service mask prevents startup during package installation. Installs greetd/keyring/X11 helpers and creates a dedicated greeter account.

Backups: /var/lib/xetal-fusion-login/backups/
Recovery from a console (Ctrl+Alt+F2):
sudo /usr/local/lib/xetal-fusion-login/system_setup.py --restore original

Please take a picture of this screen for safety!'''

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
#login-tested { color: #ffda9e; font-size: 12px; font-weight: bold; }
#login-warning { background: #30271c; color: #ffda9e; border: 1px solid #80613b; border-radius: 10px; padding: 14px; font-size: 12px; }
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
        setup_scroll = g.scrolled_window_new(None, None); g.scrolled_window_set_policy(setup_scroll, 2, 1)
        g.box_pack_start(page, setup_scroll, 1, 1, 0)
        page = g.box_new(1, 10); g.container_add(setup_scroll, page)
        card = self.box(page, spacing=8, name='card')
        self.label(card, 'COMPOSITOR', 'eyebrow')
        self.label(card, 'Detected '+self.actual['version']+'   →   Required '+self.target['hyprland'])
        self.label(card, 'Setup installs the tested version and holds its package.\nFuture desktop releases manage changes to this requirement.', 'copy')
        if runtime_install.policy.fedora_host():
            self.label(card, 'Fedora 44: includes signed packages from giperborey/Hyprland (COPR).\nThe matching libraries are held too; no third-party repository is enabled.', 'copy')
        self.keep_preferences = None
        if update:
            self.keep_preferences = g.check_button_new_with_label(b'Keep my existing desktop and startup preferences')
            g.toggle_button_set_active(self.keep_preferences, 1); g.box_pack_start(page, self.keep_preferences, 0, 0, 0)
            self.label(page, 'Uncheck to use the current desktop and startup defaults.\nYour existing profile will be backed up.', 'copy')
        else:
            self.label(page, 'Welcome opens at login and shows your plugin checks.\nYou can turn off startup from Welcome after signing in.', 'copy')
        self.login_was_enabled = login_setup.enabled()
        self.label(page, 'Tested on Arch with SDDM only', 'login-tested')
        self.fusion_login = g.check_button_new_with_label(b'Use Fusion sign-in at boot instead of my current login screen')
        g.toggle_button_set_active(self.fusion_login, self.login_was_enabled)
        g.box_pack_start(page, self.fusion_login, 0, 0, 0)
        self.label(page, 'Sign in with your theme and animated account photo.\nChoose Hyprland, KDE, XFCE or another installed desktop.', 'copy')
        self.login_warning = self.label(page, LOGIN_WARNING, 'login-warning')
        g.label_set_selectable(self.login_warning, 1)
        g.label_set_line_wrap_mode(self.login_warning, 2)
        g.widget_set_no_show_all(self.login_warning, 1)
        g.widget_set_visible(self.login_warning, self.login_was_enabled)
        g.connect(self.fusion_login, 'toggled', lambda: g.widget_set_visible(
            self.login_warning, g.toggle_button_get_active(self.fusion_login)))
        packages = ('Debian: Setup installs packages and enables administrator access if needed.\n'
                    'Use the root or administrator password when prompted.'
                    if runtime_install.policy.debian_host() else
                    'Desktop and build dependencies are installed as needed.\n'
                    'An administrator password may be requested in a separate window.')
        self.label(page, packages+
                   '\nKVM components download separately from KVM Settings.', 'copy')
        import dependencies
        if dependencies.distro() == 'arch':
            self.label(page, 'Arch-based systems: Setup upgrades system packages together and installs\n'
                       'the matching Hyprland libraries. Keep an internet connection available.\n'
                       'Runtime recovery restores replaced Hyprland packages; system updates remain.', 'copy')
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
        self.log_adjustment = g.scrolled_window_get_vadjustment(scroll)
        self.follow_log = True; self.editing_log = False
        g.connect(self.log_adjustment, 'changed', self.follow_log_end)
        g.connect(self.log_adjustment, 'value-changed', self.log_scrolled)
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
            selected = self.update and bool(self.g.toggle_button_get_active(self.keep_preferences))
            preferences = ('Keep existing desktop and startup preferences' if selected else
                           'Use current desktop and startup defaults') if self.update else (
                           'Welcome at login: on · includes fusion-check')
            text = ('Desktop folder\n'+str(Path.home()/'.config/hypr')+'\n\nHyprland '+self.target['hyprland']+
                    '  ·  Cube and Burn included\nUse all '+str(cpu_count())+' available CPU threads for compilation\n\n'+
                    preferences+'\n'+('Login: Fusion sign-in · installed desktop selector · system backups' if
                    self.g.toggle_button_get_active(self.fusion_login) else
                    'Login: restore previous login screen' if self.login_was_enabled else 'Login: keep current login screen')+
                    '\n\nSource '+self.revision[:8])
            self.g.label_set_text(self.review, text.encode())
        if self.index == 2:
            self.busy = True; self.lines = []; self.cancel_file.unlink(missing_ok=True)
            self.g.text_buffer_set_text(self.log_buffer, b'', 0); self.follow_log = True
            self.g.widget_set_sensitive(self.cancel, 1); self.g.label_set_text(self.error, b'')
            self.g.progress_bar_set_fraction(self.progress, 0.03); self.show(3)
            self.preserve_preferences = self.update and bool(self.g.toggle_button_get_active(self.keep_preferences))
            selected_login = bool(self.g.toggle_button_get_active(self.fusion_login))
            self.login_choice = True if selected_login else False if self.login_was_enabled else None
            threading.Thread(target=self.worker, daemon=True).start()
        else: self.show(self.index+1)

    def worker(self):
        try:
            if self.preserve_preferences:
                args = [sys.executable, str(install.REPO/'installer/update.py'), '--revision', self.revision,
                        '--manual', '--runtime', '--activate', '--cancel-file', str(self.cancel_file)]
            else:
                args = [sys.executable, str(install.REPO/'installer/install.py'), '--yes', '--cancel-file', str(self.cancel_file)]
            if self.login_choice is not None:
                args.append('--fusion-login' if self.login_choice else '--no-fusion-login')
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

    def log_scrolled(self):
        if not self.editing_log:
            g = self.g; adjustment = self.log_adjustment
            self.follow_log = (g.adjustment_get_value(adjustment) + g.adjustment_get_page_size(adjustment)
                               >= g.adjustment_get_upper(adjustment) - 2)

    def follow_log_end(self):
        # GTK lays out wrapped text after insertion. Follow the updated range,
        # rather than the old height available when the worker emits a line.
        if self.follow_log:
            g = self.g; adjustment = self.log_adjustment
            g.adjustment_set_value(adjustment, max(0, g.adjustment_get_upper(adjustment)
                                                  - g.adjustment_get_page_size(adjustment)))

    def append_log(self, lines):
        if not lines:
            return
        g = self.g; end = TextIter(); start = TextIter()
        self.editing_log = True
        try:
            g.text_buffer_get_end_iter(self.log_buffer, C.byref(end))
            text = ('\n'.join(lines)+'\n').encode()
            g.text_buffer_insert(self.log_buffer, C.byref(end), text, len(text))
            # Retain the same 500-line display limit; the file keeps the full
            # log. Incremental edits preserve selection and reading position.
            excess = g.text_buffer_get_line_count(self.log_buffer) - 501
            if excess > 0:
                g.text_buffer_get_start_iter(self.log_buffer, C.byref(start))
                g.text_buffer_get_iter_at_line(self.log_buffer, C.byref(end), excess)
                g.text_buffer_delete(self.log_buffer, C.byref(start), C.byref(end))
            self.follow_log_end()
        finally:
            self.editing_log = False

    def poll(self):
        pending = []
        while not self.events.empty():
            event, value = self.events.get()
            if event == 'line':
                self.lines.append(value); self.lines = self.lines[-500:]
                pending.append(value)
                prefixes = ('Required desktop', 'Downloading ', 'Package command:', 'Building ', 'Built ', 'Checking Hyprland', 'Validating ', 'Installed.', 'Ready.')
                if value.startswith(prefixes):
                    self.g.label_set_text(self.status, value[:150].encode())
                    fraction = .2 if value.startswith('Package') else .4 if value.startswith('Building') else .8 if value.startswith('Built') else .9 if value.startswith(('Checking','Validating')) else .1
                    self.g.progress_bar_set_fraction(self.progress, fraction)
            else:
                self.append_log(pending); pending.clear()
                self.busy = False; self.success = value == 0; self.g.widget_set_sensitive(self.cancel, 1)
                if self.success:
                    message = ('Hyprland '+self.target['hyprland']+' and your desktop are installed.\n\n'+
                               ('Reboot to use Fusion sign-in. Choose your account and desktop.\nWelcome opens after signing in if it is enabled.\n\n' if self.login_choice else
                                'Log out, then select Hyprland and sign in again.\nYour Cube, effects and desktop tools will start together.\n\n')+
                               'Installation log: '+str(self.log_path))
                    self.g.label_set_text(self.complete, message.encode()); self.show(4)
                else:
                    self.g.label_set_text(self.error, failure_message(self.lines).encode())
                    self.g.label_set_text(self.status, ('Setup stopped. Details: '+str(self.log_path)).encode())
                    self.g.expander_set_expanded(self.expander, 1)
                    self.g.widget_set_sensitive(self.back, 0); self.g.widget_set_sensitive(self.next, 1)
                    self.g.button_set_label(self.next, b'Retry'); self.g.button_set_label(self.cancel, b'Close')
                    self.index = 2
        self.append_log(pending)
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
