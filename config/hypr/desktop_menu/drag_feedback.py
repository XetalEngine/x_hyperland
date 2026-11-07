"""File drag actions and feedback on the native GTK drag surface."""
import math
import json
import os
import socket
import time
from gi.repository import Gdk, GLib, Gtk
from trash_animation import snapshot


def drop_operation(state, possible):
    control = bool(state & Gdk.ModifierType.CONTROL_MASK)
    shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
    if control and shift:
        return Gdk.DragAction.LINK if possible & (Gdk.DragAction.LINK | Gdk.DragAction.COPY) else Gdk.DragAction(0)
    requested = Gdk.DragAction.COPY if control else Gdk.DragAction.MOVE
    if possible & requested: return requested
    if not control and not shift and possible & Gdk.DragAction.COPY: return Gdk.DragAction.COPY
    return Gdk.DragAction(0)


def wire_action(operation, possible):
    # Wayland transports a shortcut's URLs as Copy: its source must survive.
    return Gdk.DragAction.COPY if operation == Gdk.DragAction.LINK and not possible & Gdk.DragAction.LINK else operation


class DragFeedback(Gtk.DrawingArea):
    def __init__(self, tile, context, count):
        super().__init__()
        self.context, self.count = context, count
        self.asset = snapshot(tile, tile.canvas.surface, 48)
        self.accepted = self.action = Gdk.DragAction(0)
        runtime, signature = os.environ.get('XDG_RUNTIME_DIR'), os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
        self.socket_path = f'{runtime}/hypr/{signature}/.socket.sock' if runtime and signature else None
        self.probe = None
        self.pending, self.polled, self.reply, self.native_action = 0, 0, b'', None
        self.set_size_request(64, 64)
        self.connect('draw', self.draw_icon)
        self.handler = context.connect('action-changed', self.action_changed)
        self.timer = GLib.timeout_add(32, self.update_action)
        self.show()
        Gtk.drag_set_icon_widget(context, self, -12, -8)

    def action_changed(self, _context, action):
        self.accepted = action
        self.update_action()

    def update_action(self):
        self.poll_compositor()
        state = Gdk.Keymap.get_for_display(self.get_display()).get_modifier_state()
        action = self.accepted
        if action == Gdk.DragAction.COPY and state & Gdk.ModifierType.CONTROL_MASK and state & Gdk.ModifierType.SHIFT_MASK:
            action = Gdk.DragAction.LINK
        if self.native_action is not None:
            action = {'copy':Gdk.DragAction.COPY, 'move':Gdk.DragAction.MOVE, 'link':Gdk.DragAction.LINK}.get(self.native_action, Gdk.DragAction(0))
        if action != self.action:
            self.action = action
            self.queue_draw()
        return True

    def poll_compositor(self):
        # Keyboard focus follows the destination under Wayland. Read modifiers
        # at the compositor so the source's badge keeps updating after crossing
        # into another application. Never block the GTK event loop.
        if not self.socket_path: return
        now = time.monotonic()
        try:
            if self.probe:
                chunk = self.probe.recv(4096)
                if chunk:
                    self.reply += chunk
                    if len(self.reply) > 4096: raise ValueError('Oversized drag feedback')
                else:
                    value = json.loads(self.reply)
                    self.native_action = value.get('action') if value.get('active') else None
                    self.probe.close(); self.probe = None
            elif now-self.polled >= .05:
                self.polled = self.pending = now
                self.reply = b''
                self.probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.probe.setblocking(False)
                self.probe.connect(self.socket_path)
                self.probe.sendall(b'j/xetal-file-drag')
        except BlockingIOError:
            pass
        except (OSError, ValueError):
            if self.probe: self.probe.close(); self.probe = None
            self.native_action = None
        if self.probe and now-self.pending > .25:
            self.probe.close(); self.probe = None; self.native_action = None

    def close(self):
        if self.timer: GLib.source_remove(self.timer); self.timer = 0
        if self.handler: self.context.disconnect(self.handler); self.handler = 0
        if self.probe: self.probe.close(); self.probe = None
        self.destroy()

    def draw_icon(self, _widget, cr):
        if self.asset:
            cr.set_source_surface(self.asset[0], 10, 4)
            cr.paint_with_alpha(.45 if self.action == Gdk.DragAction.MOVE else 1)
        if self.count > 1:
            cr.set_source_rgb(.14, .41, .73); cr.rectangle(38, 0, 26, 20); cr.fill()
            cr.set_source_rgb(1, 1, 1); cr.set_font_size(12)
            text = str(self.count); extents = cr.text_extents(text)
            cr.move_to(51-extents.width/2-extents.x_bearing, 14); cr.show_text(text)
        if self.action == Gdk.DragAction.MOVE: return False
        denied = not self.action
        cr.set_line_width(1.5)
        if denied:
            cr.set_source_rgb(.84, .21, .27); cr.arc(14, 50, 10, 0, math.tau)
        else:
            cr.set_source_rgb(.14, .41, .73)
            for x, y, angle in [(20,44,-90),(20,56,0),(8,56,90),(8,44,180)]:
                cr.arc(x, y, 4, math.radians(angle), math.radians(angle+90))
            cr.close_path()
        cr.fill_preserve(); cr.set_source_rgb(1, 1, 1); cr.stroke(); cr.set_line_width(2)
        if denied:
            cr.move_to(8, 44); cr.line_to(20, 56)
        elif self.action == Gdk.DragAction.LINK:
            cr.move_to(9, 55); cr.line_to(9, 48); cr.line_to(19, 48)
            cr.move_to(15, 44); cr.line_to(19, 48); cr.line_to(15, 52)
        else:
            cr.move_to(9, 50); cr.line_to(19, 50); cr.move_to(14, 45); cr.line_to(14, 55)
        cr.stroke()
        return False
