"""One persistent window-appearance editor with a local focus preview."""
from copy import deepcopy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QPalette
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QScrollArea, QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QLineEdit,
    QPlainTextEdit, QPushButton)
from visuals import model, controller
import desktop_settings as settings
from preferences_page import APPEARANCE, validate_values

SCHEMA = APPEARANCE + [('Focus', 'decoration:shadow:range', 'Shadow size', 'int', (0,40,' px'))]
INITIAL = {'decoration:rounding':10,'general:border_size':1,'general:gaps_in':'5','general:gaps_out':'5',
    'general:resize_on_border':False,'animations:enabled':True,'decoration:blur:enabled':True,
    'decoration:shadow:enabled':True,'decoration:active_opacity':1.,'decoration:inactive_opacity':1.,
    'decoration:shadow:range':16}


def note(text):
    result=QLabel(text);result.setWordWrap(True);result.setObjectName('muted');return result


class WindowPreview(QWidget):
    """Illustration only: changing it never moves or restyles real windows."""
    def __init__(self):
        super().__init__();self.values=dict(INITIAL);self.focus=deepcopy(model.FOCUS);self.active=1;self.boxes=[]
        self.setMinimumHeight(190);self.setMaximumHeight(230)
        self.setAccessibleName('Window appearance preview; click a sample window to change focus')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette=self.palette();accent=palette.color(QPalette.ColorRole.Highlight)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(palette.color(QPalette.ColorRole.AlternateBase))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),12,12)
        w=min(360.,self.width()*.51);h=self.height()-62
        self.boxes=[QRectF(max(22.,self.width()*.14),18,w,h),QRectF(self.width()*.40,38,w,h)]
        for index in (1-self.active,self.active):
            rect=self.boxes[index];active=index==self.active
            radius=min(self.values['decoration:rounding'],18)
            shadow=self.values['decoration:shadow:range'] if self.values['decoration:shadow:enabled'] else 0
            for spread in range(min(18,shadow),0,-2):
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,8));p.drawRoundedRect(rect.adjusted(-spread,-spread/2,spread,spread),radius+spread/2,radius+spread/2)
            if self.focus['enabled'] and self.focus['glow'] and active:
                for spread in range(min(18,self.focus['glow_size']),0,-1):
                    color=QColor(accent);color.setAlpha(16);p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(color,2))
                    p.drawRoundedRect(rect.adjusted(-spread,-spread,spread,spread),radius+spread,radius+spread)
            p.setOpacity(self.values['decoration:active_opacity' if active else 'decoration:inactive_opacity'])
            p.setBrush(palette.color(QPalette.ColorRole.Window))
            border=self.values['general:border_size']
            p.setPen(QPen(accent if active else palette.color(QPalette.ColorRole.Mid),border) if border else Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect,radius,radius)
            p.setPen(palette.color(QPalette.ColorRole.WindowText))
            p.drawText(rect.adjusted(14,8,-12,-h+34),Qt.AlignmentFlag.AlignVCenter,'Active window' if active else 'Inactive window')
            if self.focus['enabled']:
                p.setPen(QPen(accent if active else palette.color(QPalette.ColorRole.Mid),2))
                p.drawLine(rect.topLeft()+QPointF(12,38),rect.topRight()+QPointF(-12,38))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(palette.color(QPalette.ColorRole.Mid))
            for row,length in enumerate((.7,.5,.6)):
                p.drawRoundedRect(QRectF(rect.x()+16,rect.y()+57+row*14,(w-40)*length,5),2,2)
            p.setOpacity(1.)
        p.setPen(palette.color(QPalette.ColorRole.WindowText))
        p.drawText(QRectF(12,self.height()-24,self.width()-24,20),Qt.AlignmentFlag.AlignCenter,'Click either sample to change focus · preview only')

    def mousePressEvent(self,event):
        for index in (self.active,1-self.active):
            if self.boxes and self.boxes[index].contains(event.position()):self.active=index;self.update();break


class AppearancePage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=self.dirty=self.loading=False
        self.baseline={};self.baseline_focus=deepcopy(model.FOCUS);self.config=deepcopy(model.DEFAULTS);self.token=None;self.fields={};self.columns=0
        root=QVBoxLayout(self);root.setContentsMargins(16,12,16,12)
        title=QLabel('Window appearance');title.setObjectName('brand');root.addWidget(title)
        root.addWidget(note('Shape, spacing and focus in one place. Your saved choices stay the same when you apply a theme; accent colors follow the theme.'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body=QWidget();body=QVBoxLayout(self.body);body.setContentsMargins(0,0,0,0);body.setSpacing(12)
        self.preview=WindowPreview();body.addWidget(self.preview)
        self.grid=QGridLayout();self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(12);body.addLayout(self.grid)
        self.left=QWidget();left=QVBoxLayout(self.left);left.setContentsMargins(0,0,0,0)
        groups={}
        for caption in ('Window shape','Effects'):
            group=QGroupBox('Shape && spacing' if caption=='Window shape' else 'Effects && opacity')
            form=QFormLayout(group);form.setSpacing(10);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            groups[caption]=form;left.addWidget(group)
        self.focus_group=QGroupBox('Focus && emphasis');focus_form=QFormLayout(self.focus_group);focus_form.setSpacing(10)
        focus_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.coordinate=QCheckBox('Coordinate borders, shadows and headers');focus_form.addRow(self.coordinate)
        focus_form.addRow(note('Use the theme accent to distinguish the active window. These preferences apply across all themes.'))
        self.glow=QCheckBox('Glow around the active window');focus_form.addRow(self.glow)
        self.glow_size=QSpinBox();self.glow_size.setRange(1,30);self.glow_size.setSuffix(' px');focus_form.addRow('Glow size',self.glow_size)
        for section,key,label,kind,data in SCHEMA:
            if kind=='bool':field=QCheckBox('Enabled');field.toggled.connect(self.edited)
            elif kind in ('int','float'):
                field=QSpinBox() if kind=='int' else QDoubleSpinBox();field.setRange(data[0],data[1]);field.setKeyboardTracking(False)
                if kind=='int':field.setSuffix(data[2])
                else:field.setSingleStep(data[2]);field.setDecimals(2)
                field.valueChanged.connect(self.edited)
            else:field=QLineEdit();field.setPlaceholderText(data);field.textChanged.connect(self.edited)
            field.setAccessibleName(label);field.setMinimumWidth(100);self.fields[key]=field
            (focus_form if section=='Focus' else groups[section]).addRow(label,field)
        self.exceptions=QPlainTextEdit();self.exceptions.setPlaceholderText('One application class per line, for example: mpv')
        self.exceptions.setMaximumHeight(82);focus_form.addRow('No glow or shadow for',self.exceptions)
        focus_form.addRow(note('Use the exact class shown by the window lister. Other windows keep their normal controls.'))
        left.addStretch();body.addStretch();scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status=note('Reading saved appearance…');root.addWidget(self.status)
        buttons=QHBoxLayout();buttons.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));buttons.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(self.reset);buttons.addWidget(self.discard)
        self.apply=QPushButton('Apply appearance');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);buttons.addWidget(self.apply)
        root.addLayout(buttons)
        for field in (self.coordinate,self.glow):field.toggled.connect(self.edited)
        self.glow_size.valueChanged.connect(self.edited);self.exceptions.textChanged.connect(self.edited)
        self.fill(INITIAL,model.FOCUS);self.reflow()

    def resizeEvent(self,event):super().resizeEvent(event);self.reflow()
    def reflow(self):
        columns=2 if self.width()>=820 else 1
        if columns==self.columns:return
        self.columns=columns
        self.grid.removeWidget(self.left);self.grid.removeWidget(self.focus_group)
        self.grid.addWidget(self.left,0,0,Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(self.focus_group,0 if columns==2 else 1,1 if columns==2 else 0,Qt.AlignmentFlag.AlignTop)
        self.grid.setColumnStretch(0,1);self.grid.setColumnStretch(1,1 if columns==2 else 0)

    def values(self):
        return {key:(self.fields[key].isChecked() if kind=='bool' else self.fields[key].value() if kind in ('int','float') else self.fields[key].text().strip())
                for _,key,_,kind,_ in SCHEMA}
    def focus_values(self):
        values=self.values()
        return dict(enabled=self.coordinate.isChecked(),border=values['general:border_size'],
            shadow=values['decoration:shadow:range'],
            glow=self.glow.isChecked(),glow_size=self.glow_size.value(),
            exceptions=list(dict.fromkeys(line.strip() for line in self.exceptions.toPlainText().splitlines() if line.strip())))

    def fill(self,values,focus):
        self.loading=True
        for _,key,_,kind,_ in SCHEMA:
            field=self.fields[key];value=values[key]
            if kind=='bool':field.setChecked(bool(value))
            elif kind in ('int','float'):field.setValue(value)
            else:field.setText(str(value))
        self.coordinate.setChecked(focus['enabled']);self.glow.setChecked(focus['glow']);self.glow_size.setValue(focus['glow_size'])
        self.exceptions.setPlainText('\n'.join(focus['exceptions']));self.loading=False;self.edited()

    def reset(self):
        if not self.busy:self.fill(self.baseline or INITIAL,self.config['focus'])

    def edited(self,*_):
        if self.loading:return
        self.dirty=bool(self.baseline) and (self.values()!=self.baseline or self.focus_values()!=self.baseline_focus)
        self.preview.values=self.values();self.preview.focus=self.focus_values();self.preview.update()
        self.body.setEnabled(not self.busy and bool(self.baseline));self.reload.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy);self.discard.setEnabled(self.dirty and not self.busy)
        self.glow.setEnabled(self.coordinate.isChecked());self.glow_size.setEnabled(self.coordinate.isChecked() and self.glow.isChecked())
        self.exceptions.setEnabled(self.coordinate.isChecked())
        self.fields['decoration:shadow:range'].setEnabled(self.fields['decoration:shadow:enabled'].isChecked())

    def refresh(self,force=False):
        if self.busy or (self.dirty and not force):return
        self.busy=True;self.edited();self.status.setText('Reading saved appearance…')
        self.async_run(lambda:(settings.read_options(self.fields),model.load()),self.loaded,self.failed)

    def loaded(self,result):
        values,(self.config,self.token)=result;self.baseline=values;self.busy=False
        self.fill(values,self.config['focus']);self.baseline=self.values();self.baseline_focus=self.focus_values();self.edited()
        self.status.setText('Preview updates as you edit. Apply saves your choices across themes and future logins.')

    def save(self):
        if self.busy or not self.dirty:return
        values=self.values();focus=self.focus_values();config=deepcopy(self.config)
        changes={key:value for key,value in values.items() if self.baseline[key]!=value}
        # Coordination changes colors/emphasis, not the chosen geometry. Keep
        # these values even when coordination is subsequently switched off.
        for key in ('general:border_size','decoration:shadow:range','decoration:shadow:enabled'):
            changes[key]=values[key]
        config['appearance'].update(changes);config['focus']=focus
        try:validate_values(values);model.validate(config)
        except ValueError as error:self.status.setText(str(error));return
        def work():
            actual=settings.read_options(changes)
            if any(actual[key]!=self.baseline[key] for key in changes):raise ValueError('Appearance changed elsewhere. Reload before applying.')
            controller.save(config,self.token)
            return settings.read_options(self.fields),model.load()
        self.busy=True;self.edited();self.status.setText('Saving window appearance…')
        self.async_run(work,self.saved,self.failed)

    def saved(self,result):self.loaded(result);self.status.setText('Saved. Your appearance and focus preferences are kept when you apply a theme.')
    def failed(self,message):self.busy=False;self.edited();self.status.setText(str(message))
