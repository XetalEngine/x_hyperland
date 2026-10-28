"""Draggable monitor arrangement with an independently guarded live preview."""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QLinearGradient
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QFormLayout, QScrollArea, QDialog, QMessageBox)

import desktop_settings as settings
import runtime as theme_runtime


def label(text, name=''):
    item = QLabel(text); item.setObjectName(name); item.setWordWrap(True); return item


def button(text, callback, primary=False):
    item = QPushButton(text); item.clicked.connect(callback)
    if primary: item.setObjectName('primary')
    return item


class Arrangement(QWidget):
    selected = pyqtSignal(str)
    edited = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.models = []; self.current = ''; self.drag = None; self.rects = []
        self.setMinimumSize(400, 270)
        self.setMouseTracking(True)
        self.setToolTip('Drag displays to match their physical positions. Edges snap together.')

    def view(self):
        if self.drag: return self.drag['view']
        active = [m for m in self.models if m['enabled'] and not m['mirror']]
        if not active: return 1, 20, 20
        left, top = min(m['x'] for m in active), min(m['y'] for m in active)
        right = max(m['x']+settings.logical_size(m)[0] for m in active)
        bottom = max(m['y']+settings.logical_size(m)[1] for m in active)
        space = 100 if any(not m['enabled'] or m['mirror'] for m in self.models) else 0
        scale = min((self.width()-70)/max(right-left, 1), (self.height()-85-space)/max(bottom-top, 1))
        return scale, (self.width()-(right-left)*scale)/2-left*scale, (self.height()-space-(bottom-top)*scale)/2-top*scale

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme_runtime.qcolor('#101821'))
        p.setPen(QPen(theme_runtime.qcolor('#192630'), 1))
        for x in range(0, self.width(), 24): p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 24): p.drawLine(0, y, self.width(), y)
        self.rects = []; scale, ox, oy = self.view(); parked = 0
        for m in self.models:
            if not m['enabled'] or m['mirror']:
                rect = QRectF(18+parked*155, self.height()-82, 145, 65); parked += 1
            else:
                w, h = settings.logical_size(m)
                rect = QRectF(m['x']*scale+ox, m['y']*scale+oy, w*scale, h*scale).adjusted(2, 2, -2, -2)
            self.rects.append((m, rect))
            active = m['name'] == self.current
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, theme_runtime.qcolor('#264e58' if active else '#243240'))
            gradient.setColorAt(1, theme_runtime.qcolor('#182d38' if active else '#17232f'))
            p.setBrush(gradient); p.setPen(QPen(theme_runtime.qcolor('#78e4d2' if active else '#546a7d'), 2 if active else 1))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(theme_runtime.qcolor('#e6f5f5')); p.setFont(QFont('DejaVu Sans', 19 if rect.height() > 95 else 13, QFont.Weight.Bold))
            top = rect.top()+max(4, (rect.height()-85)/2)
            p.drawText(QRectF(rect.left()+5, top, rect.width()-10, 30), Qt.AlignmentFlag.AlignCenter, str(m['number']))
            p.setFont(QFont('DejaVu Sans', 10, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left()+4, top+30, rect.width()-8, 22), Qt.AlignmentFlag.AlignCenter, m['name'])
            if rect.height() > 95:
                p.setPen(theme_runtime.qcolor('#a5becb')); p.setFont(QFont('DejaVu Sans', 8))
                text = f"{m['width']} × {m['height']}  ·  {m['rate']:g} Hz\n{m['scale']*100:g}%  ·  {m['x']}, {m['y']}"
                p.drawText(rect.adjusted(4, top-rect.top()+54, -4, -5), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)
            elif not m['enabled'] or m['mirror']:
                p.setFont(QFont('DejaVu Sans', 8)); p.setPen(theme_runtime.qcolor('#9bb1c4'))
                p.drawText(rect.adjusted(3, 47, -3, -2), Qt.AlignmentFlag.AlignCenter, 'Disabled' if not m['enabled'] else 'Mirrors '+m['mirror'])
        if not self.models:
            p.setPen(theme_runtime.qcolor('#9bb1c4')); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Loading connected displays…')

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        for m, rect in reversed(self.rects):
            if rect.contains(event.position()):
                self.current = m['name']; self.selected.emit(m['name'])
                if m['enabled'] and not m['mirror']:
                    self.drag = {'model': m, 'start': event.position(), 'x': m['x'], 'y': m['y'], 'view': self.view(), 'moved': False}
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update(); break

    def mouseMoveEvent(self, event):
        if not self.drag:
            self.setCursor(Qt.CursorShape.OpenHandCursor if any(r.contains(event.position()) for _, r in self.rects) else Qt.CursorShape.ArrowCursor)
            return
        d = self.drag; m = d['model']; scale = d['view'][0]
        delta = event.position()-d['start']
        if abs(delta.x())+abs(delta.y()) < 3: return
        d['moved'] = True
        x, y = round(d['x']+delta.x()/scale), round(d['y']+delta.y()/scale)
        width, height = settings.logical_size(m); xs = [0]; ys = [0]
        for other in self.models:
            if other is m or not other['enabled'] or other['mirror']: continue
            w, h = settings.logical_size(other)
            xs += [other['x'], other['x']+w, other['x']-width, other['x']+w-width]
            ys += [other['y'], other['y']+h, other['y']-height, other['y']+h-height]
        snap = 10/scale
        nx, ny = min(xs, key=lambda v: abs(v-x)), min(ys, key=lambda v: abs(v-y))
        m['x'] = nx if abs(nx-x) < snap else x; m['y'] = ny if abs(ny-y) < snap else y
        self.edited.emit(); self.update()

    def mouseReleaseEvent(self, event):
        if self.drag and self.drag['moved']: settings.normalize(self.models); self.edited.emit()
        self.drag = None; self.setCursor(Qt.CursorShape.OpenHandCursor); self.update()


class ConfirmDisplay(QDialog):
    decision = pyqtSignal(str)
    def __init__(self, parent, seconds):
        super().__init__(parent); self.setWindowTitle('Keep display changes?'); self.setModal(True)
        self.setMinimumWidth(440); self.deadline = time.monotonic()+seconds; self.decided = False
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label('Does everything look right?', 'brand'))
        self.countdown = label('', 'status'); layout.addWidget(self.countdown)
        layout.addWidget(label('Keep saves this arrangement for future logins. Closing this dialog restores your previous settings.', 'muted'))
        row = QHBoxLayout(); self.revert = button('Revert now', lambda: self.choose('revert'))
        self.keep = button('Keep changes', lambda: self.choose('keep'), True)
        self.revert.setDefault(True); row.addWidget(self.revert); row.addWidget(self.keep); layout.addLayout(row)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(100); self.tick()

    def tick(self):
        remaining = max(0, math.ceil(self.deadline-time.monotonic()))
        self.countdown.setText(f'Reverting automatically in {remaining} seconds…')
        if remaining == 0: self.choose('revert')

    def choose(self, value):
        if self.decided: return
        self.decided = True; self.timer.stop(); self.keep.setEnabled(False); self.revert.setEnabled(False)
        self.countdown.setText('Saving…' if value == 'keep' else 'Restoring previous settings…')
        self.decision.emit(value)

    def reject(self): self.choose('revert')


class DisplaysPage(QWidget):
    def __init__(self, async_run):
        super().__init__(); self.async_run = async_run; self.store = settings.Store('displays')
        self.models = []; self.baseline = []; self.token = ''; self.loading = False; self.busy = False; self.dirty = False
        self.process = None; self.dialog = None; self.buffer = b''; self.received_result = False
        layout = QVBoxLayout(self); layout.setContentsMargins(22, 18, 22, 18)
        layout.addWidget(label('Displays & arrangement', 'brand'))
        layout.addWidget(label('Drag screens to match your desk, then choose a display to adjust its picture.', 'muted'))
        toolbar = QHBoxLayout()
        toolbar.addWidget(button('Identify displays', self.identify))
        toolbar.addWidget(button('Arrange horizontally', lambda: self.arrange(False)))
        toolbar.addWidget(button('Arrange vertically', lambda: self.arrange(True)))
        toolbar.addStretch(); toolbar.addWidget(button('Reload displays', lambda: self.refresh(force=True)))
        layout.addLayout(toolbar)
        body = QHBoxLayout(); self.canvas = Arrangement(); body.addWidget(self.canvas, 1)
        self.canvas.selected.connect(self.select); self.canvas.edited.connect(self.canvas_changed)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumWidth(295); scroll.setMaximumWidth(350)
        panel = QWidget(); self.form = QFormLayout(panel); self.form.setContentsMargins(16, 12, 14, 12); self.form.setVerticalSpacing(13)
        self.selector = QComboBox(); self.selector.currentIndexChanged.connect(self.select_index); self.form.addRow('Display', self.selector)
        self.enabled = QCheckBox('Enabled'); self.form.addRow('', self.enabled)
        self.resolution = QComboBox(); self.rate = QComboBox(); self.scale = QComboBox()
        self.scale.setEditable(True); self.scale.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for value in [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3]: self.scale.addItem(f'{value*100:g}%', value)
        self.rotation = QComboBox()
        for index, name in enumerate(['Landscape', '90°', 'Upside down', '270°', 'Flipped', 'Flipped 90°', 'Flipped 180°', 'Flipped 270°']): self.rotation.addItem(name, index)
        self.mirror = QComboBox()
        self.x = QSpinBox(); self.y = QSpinBox()
        for spin in (self.x, self.y): spin.setRange(-32000, 32000); spin.setKeyboardTracking(False)
        for title, widget in [('Resolution', self.resolution), ('Refresh rate', self.rate), ('Scale', self.scale),
                              ('Rotation', self.rotation), ('Mode', self.mirror), ('Position X', self.x), ('Position Y', self.y)]: self.form.addRow(title, widget)
        self.info = label('', 'muted'); self.form.addRow(self.info)
        scroll.setWidget(panel); body.addWidget(scroll); layout.addLayout(body, 1)
        self.panel = panel
        self.pending = label('', 'status'); self.pending.hide(); layout.addWidget(self.pending)
        actions = QHBoxLayout(); self.status = label('Loading connected displays…', 'muted'); actions.addWidget(self.status, 1)
        self.discard = button('Discard', self.discard_changes); self.apply = button('Apply & preview', self.start_preview, True)
        actions.addWidget(self.discard); actions.addWidget(self.apply); layout.addLayout(actions)
        self.resolution.currentIndexChanged.connect(self.change_resolution)
        for widget in [self.enabled, self.rate, self.scale, self.rotation, self.mirror, self.x, self.y]:
            signal = widget.toggled if isinstance(widget, QCheckBox) else widget.valueChanged if isinstance(widget, QSpinBox) else widget.currentTextChanged
            signal.connect(self.edit)
        self.poll = QTimer(self); self.poll.timeout.connect(self.read_guard)
        QApplication.instance().aboutToQuit.connect(lambda: self.send_decision('revert'))
        self.update_state()

    def selected_model(self): return next((m for m in self.models if m['name'] == self.canvas.current), None)

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force): return
        if self.dirty and force and QMessageBox.question(self, 'Discard display edits?', 'Reload displays and discard this draft?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard: return
        self.busy = True; self.update_state(); self.status.setText('Reading connected displays…')
        self.async_run(lambda: (settings.display_models(settings.monitors()), self.store.load()[1]), self.loaded, self.failed)

    def loaded(self, result):
        models, self.token = result; self.baseline = copy.deepcopy(models); self.models = models; self.busy = False
        self.canvas.models = self.models
        self.loading = True; self.selector.clear()
        for m in models: self.selector.addItem(f"{m['number']} · {m['name']} · {m['label']}", m['name'])
        self.loading = False
        self.select(self.canvas.current if any(m['name'] == self.canvas.current for m in models) else models[0]['name'] if models else '')
        self.update_state()

    def failed(self, message):
        self.busy = False; self.update_state(); self.status.setText(message)

    def select_index(self):
        if not self.loading: self.select(self.selector.currentData())

    def select(self, name):
        self.canvas.current = name; self.sync_form(); self.canvas.update()

    def sync_form(self):
        m = self.selected_model()
        if not m: return
        self.loading = True
        self.selector.setCurrentIndex(self.selector.findData(m['name'])); self.enabled.setChecked(m['enabled'])
        self.resolution.clear()
        sizes = list(dict.fromkeys(settings.mode_parts(mode)[:2] for mode in m['modes']))
        for width, height in sizes: self.resolution.addItem(f'{width} × {height}', (width, height))
        self.resolution.setCurrentIndex(sizes.index((m['width'], m['height'])))
        self.fill_rates(m)
        self.scale.setCurrentText(f"{m['scale']*100:g}%"); self.rotation.setCurrentIndex(m['transform'])
        self.mirror.clear(); self.mirror.addItem('Extend desktop', '')
        for other in self.models:
            if other['name'] != m['name'] and other['enabled'] and not other['mirror']: self.mirror.addItem('Mirror '+other['name'], other['name'])
        if self.mirror.findData(m['mirror']) < 0: self.mirror.addItem('Mirror '+m['mirror'], m['mirror'])
        self.mirror.setCurrentIndex(self.mirror.findData(m['mirror']))
        self.x.setValue(m['x']); self.y.setValue(m['y'])
        for widget in [self.resolution, self.rate, self.scale, self.rotation, self.mirror, self.x, self.y]: widget.setEnabled(m['enabled'])
        self.x.setEnabled(m['enabled'] and not m['mirror']); self.y.setEnabled(m['enabled'] and not m['mirror'])
        w, h = settings.logical_size(m); self.info.setText(f"{m['label']}\nDesktop size: {w} × {h}\nOnly advertised display modes are listed.")
        self.loading = False

    def fill_rates(self, m):
        rates = sorted({settings.mode_parts(mode)[2] for mode in m['modes'] if settings.mode_parts(mode)[:2] == (m['width'], m['height'])}, reverse=True)
        self.rate.clear()
        for rate in rates: self.rate.addItem(f'{rate:g} Hz', rate)
        if rates: self.rate.setCurrentIndex(min(range(len(rates)), key=lambda i: abs(rates[i]-m['rate'])))

    def change_resolution(self):
        if self.loading: return
        m = self.selected_model(); size = self.resolution.currentData()
        if not m or not size: return
        m['width'], m['height'] = size
        self.loading = True; self.fill_rates(m); self.loading = False; self.edit()

    def edit(self):
        if self.loading or self.busy: return
        m = self.selected_model()
        if not m: return
        try: scale = float(self.scale.currentText().removesuffix('%'))/100
        except ValueError: self.status.setText('Enter a scale such as 100% or 125%.'); self.apply.setEnabled(False); return
        if not math.isfinite(scale) or not .5 <= scale <= 4:
            self.status.setText('Choose a scale between 50% and 400%.'); self.apply.setEnabled(False); return
        m.update(enabled=self.enabled.isChecked(), rate=self.rate.currentData() or m['rate'], scale=scale,
                 transform=self.rotation.currentData(), mirror=self.mirror.currentData() or '', x=self.x.value(), y=self.y.value())
        for widget in [self.resolution, self.rate, self.scale, self.rotation, self.mirror, self.x, self.y]: widget.setEnabled(m['enabled'])
        self.x.setEnabled(m['enabled'] and not m['mirror']); self.y.setEnabled(m['enabled'] and not m['mirror'])
        self.canvas.update(); self.update_state()

    def canvas_changed(self): self.sync_form(); self.update_state()

    def arrange(self, vertical):
        if self.busy: return
        position = 0
        for m in sorted(self.models, key=lambda v: (v['x'], v['y'])):
            if not m['enabled'] or m['mirror']: continue
            m['x'], m['y'] = (0, position) if vertical else (position, 0)
            position += settings.logical_size(m)[int(vertical)]
        self.sync_form(); self.canvas.update(); self.update_state()

    def update_state(self):
        self.dirty = settings.layout_state(self.models) != settings.layout_state(self.baseline)
        error = ''
        if self.models:
            try: settings.validate_displays(self.models, self.baseline)
            except ValueError as exc: error = str(exc)
        self.apply.setEnabled(self.dirty and not self.busy and not error)
        self.discard.setEnabled(self.dirty and not self.busy); self.canvas.setEnabled(not self.busy)
        self.panel.setEnabled(not self.busy)
        self.pending.setVisible(self.dirty)
        changes = [m['name'] for m, old in zip(self.models, self.baseline) if settings.layout_state([m]) != settings.layout_state([old])]
        self.pending.setText('UNSAVED DISPLAY CHANGES  ·  '+', '.join(changes)+'\nApply starts a 20-second preview. Keep changes saves it for future logins.')
        if not self.busy: self.status.setText(error or f'{len(self.models)} connected displays · Changes revert unless you keep them')

    def discard_changes(self):
        self.models = copy.deepcopy(self.baseline); self.canvas.models = self.models; self.sync_form(); self.canvas.update(); self.update_state()

    def identify(self):
        subprocess.Popen([sys.executable, str(Path(__file__).with_name('identify_displays.py'))], start_new_session=True)

    def start_preview(self):
        if not self.dirty or self.busy: return
        try:
            settings.validate_displays(self.models, self.baseline)
            self.process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('display_guard.py'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            request = {'models': self.models, 'baseline': settings.layout_state(self.baseline), 'token': self.token}
            self.process.stdin.write((json.dumps(request)+'\n').encode()); self.process.stdin.flush()
            os.set_blocking(self.process.stdout.fileno(), False)
            self.buffer = b''; self.received_result = False; self.busy = True; self.update_state()
            self.status.setText('Validating and previewing display settings…'); self.poll.start(60)
        except Exception as exc: self.failed(str(exc))

    def send_decision(self, value):
        if self.process and self.process.poll() is None:
            try: self.process.stdin.write((value+'\n').encode()); self.process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError): pass

    def read_guard(self):
        if not self.process: return
        try: self.buffer += os.read(self.process.stdout.fileno(), 65536)
        except BlockingIOError: pass
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: message = json.loads(line)
            except ValueError: continue
            if message['event'] == 'preview':
                self.dialog = ConfirmDisplay(self, message['seconds']); self.dialog.decision.connect(self.send_decision); self.dialog.show()
            else:
                self.received_result = True
                if self.dialog: self.dialog.timer.stop(); self.dialog.done(0); self.dialog.deleteLater(); self.dialog = None
                self.busy = False
                if message['event'] == 'kept': self.dirty = False; self.refresh()
                else: self.update_state(); self.status.setText(message.get('message') or message.get('reason', 'Previous settings restored'))
        if self.process.poll() is not None:
            self.poll.stop()
            if not self.received_result:
                if self.dialog: self.dialog.done(0); self.dialog = None
                self.failed('Display preview ended unexpectedly. Check the display state with Reload displays.')
            for stream in [self.process.stdin, self.process.stdout, self.process.stderr]: stream.close()
            self.process = None

    def can_close(self):
        if self.busy:
            self.send_decision('revert'); self.status.setText('Restoring display settings before closing…'); return False
        return True
