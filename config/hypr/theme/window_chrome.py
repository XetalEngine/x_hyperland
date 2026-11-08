"""Native Qt window actions, drawn consistently in Fusion's own headers."""
from PyQt6.QtCore import Qt,QEvent,QObject,QRectF,QPointF
from PyQt6.QtGui import QColor,QPainter,QPen,QPolygonF
from PyQt6.QtWidgets import QDialog,QHBoxLayout,QLabel,QToolButton,QWidget,QSizePolicy,QStyle,QStyleOptionToolButton
import weakref


class ControlButton(QToolButton):
    def __init__(self,symbol,parent):
        super().__init__(parent);self.symbol=symbol
        self.setProperty('xetalWindowControl',True)

    def paintEvent(self,event):
        super().paintEvent(event)
        option=QStyleOptionToolButton();self.initStyleOption(option)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width()/2,self.height()/2)
        ink=option.palette.buttonText().color()
        hover_ink=self.property('xetalChromeHoverInk')
        if hover_ink and self.isEnabled() and option.state&QStyle.StateFlag.State_MouseOver and not self.isDown():
            ink=QColor(hover_ink)
        painter.setPen(QPen(ink,1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.SquareCap))
        if self.symbol=='minimize':painter.drawLine(QPointF(-5,3),QPointF(5,3))
        elif self.symbol=='maximize':painter.drawRect(QRectF(-5,-5,10,10))
        elif self.symbol=='restore':
            painter.drawPolyline(QPolygonF([QPointF(-2,-4),QPointF(-2,-6),QPointF(6,-6),QPointF(6,2),QPointF(4,2)]))
            painter.drawRect(QRectF(-5,-2,8,8))
        else:
            painter.drawLine(QPointF(-4.5,-4.5),QPointF(4.5,4.5))
            painter.drawLine(QPointF(-4.5,4.5),QPointF(4.5,-4.5))


def style_close(button,design=None):
    import runtime
    button.setProperty('xetalChromeHoverInk',None)
    if design=='platform95':
        from platform95 import chrome_style
        colors=runtime.colors(style=design)
        button.setProperty('xetalChromeHoverInk','#fff8e9' if getattr(button,'symbol','close')=='close' else colors['HighlightedText'])
        button.setStyleSheet(chrome_style(colors))
        return
    if design=='mycelium':
        from mycelium import velvet
        p=runtime.colors(style=design);close=getattr(button,'symbol','close')=='close'
        button.setStyleSheet(f'''QToolButton {{background:{velvet(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:9px;padding:0;}}
            QToolButton:hover {{background:{'#814359' if close else p['Highlight']};color:{'#fff2ef' if close else p['HighlightedText']};border-color:{p['Accent']};}}
            QToolButton:pressed {{background:{p['Base']};color:{p['Text']};}}
            QToolButton:focus {{border-color:{p['Accent']};}}
            QToolButton:disabled {{color:{p['Disabled']};border-color:{p['Mid']};}}''')
        return
    if design=='atomicafterglow':
        from atomicafterglow import metal,phosphor
        p=runtime.colors(style=design);close=getattr(button,'symbol','close')=='close'
        button.setStyleSheet(f"QToolButton {{background:{phosphor(p) if close else metal(p)};color:{p['HighlightedText'] if close else p['Text']};border:1px solid {p['Light']};border-radius:3px;padding:0;}} QToolButton:hover {{background:{'#8f3428' if close else p['Highlight']};color:{'#fff2d1' if close else p['HighlightedText']};}}")
        return
    if design=='blackwood':
        from blackwood import wood
        p=runtime.colors(style=design);close=getattr(button,'symbol','close')=='close'
        button.setStyleSheet(f'''QToolButton {{background:{wood(p)};color:{p['Text']};border:1px solid {p['Midlight']};
            border-top-color:{p['Light']};border-radius:3px;padding:0;}}
            QToolButton:hover {{background:{'#743e2c' if close else p['Highlight']};color:{'#fff4db' if close else p['HighlightedText']};border-color:{p['Light']};}}
            QToolButton:pressed {{background:{p['Base']};color:{p['Text']};}}
            QToolButton:focus {{border-color:{p['Accent']};}}''')
        return
    if design=='midnighttransit':
        from midnighttransit import enamel,amber
        p=runtime.colors(style=design)
        close=getattr(button,'symbol','close')=='close'
        button.setStyleSheet(f'''QToolButton {{background:{amber(p) if close else enamel(p)};
            color:{p['HighlightedText'] if close else p['Text']};border:1px solid {p['Light']};border-radius:4px;padding:0;}}
            QToolButton:hover {{background:{'#a54922' if close else amber(p)};color:{'#fff6e7' if close else p['HighlightedText']};}}
            QToolButton:pressed {{background:{p['Base']};color:{p['Text']};}}
            QToolButton:focus {{border-color:{p['Accent']};}}''')
        return
    if design=='hyperfusionblue':
        from hyperfusionblue import steel,blue
        p=runtime.colors(style=design)
        close=getattr(button,'symbol','close')=='close'
        background=('qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #b86358,stop:.48 #81352f,stop:.52 #5b211f,stop:1 #843c32)'
                    if close else steel(p))
        button.setStyleSheet(f'''QToolButton {{background:{background};color:{'#ffffff' if close else p['Text']};
            border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:6px;padding:0;}}
            QToolButton:hover {{background:{'#b94b40' if close else blue(p)};color:#ffffff;border-color:{p['Accent']};}}
            QToolButton:pressed {{background:{'#6e211e' if close else p['Highlight']};}}
            QToolButton:focus {{border-color:{p['Accent']};}}''')
        return
    if design in ('breakpoint','binaryknife','tidalglass','porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow'):
        p=runtime.colors(style=design)
        hover=f"background:{p['Highlight']}; color:{p['Text']}; border-color:{p['Accent']};"
        pressed=f"background:{p['Mid']};"
    else:
        hover='background:#663544; color:#fff1f3; border-color:#b3687f;'
        pressed='background:#8a4052;'
    button.setStyleSheet('QToolButton {color:palette(window-text); background:transparent; border:1px solid transparent; '
                        'border-radius:'+('2' if design=='shadowedge' else '16' if design=='candycloud' else '3' if design=='obsidianforge' else '2' if design=='porcelainink' else '4' if design=='binaryknife' else '6')+'px; padding:0; font-size:23px;} '
                        'QToolButton:hover {'+hover+'} QToolButton:pressed {'+pressed+'} '
                        'QToolButton:focus {border-color:palette(highlight);}')


def close_button(window,callback=None,title=None):
    button=ControlButton('close',window);button.setObjectName('windowClose');button.setFixedSize(32,32)
    caption=title or ('Close '+window.windowTitle()).strip()
    button.setToolTip(caption);button.setAccessibleName(caption);button.setCursor(Qt.CursorShape.PointingHandCursor)
    import runtime
    from PyQt6.QtWidgets import QApplication
    selected=QApplication.instance().property('xetalThemeDesign') or runtime.design()
    style_close(button,selected)
    button.clicked.connect(callback or window.close)
    window.setProperty('xetalCloseButton',True)
    return button


def toggle_maximized(window):
    # Native Qt state requests go through Wayland/X11 and the compositor. The
    # current state is authoritative after external shortcuts or restore too.
    window.showNormal() if window.isMaximized() or window.isFullScreen() else window.showMaximized()


class WindowControls(QWidget):
    def __init__(self,window,callback=None,title=None):
        super().__init__(window);self.owner=weakref.ref(window)
        self.setObjectName('windowControls');self.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.setStyleSheet('QWidget#windowControls {background:transparent;}')
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        self.minimize=ControlButton('minimize',self);self.maximize=ControlButton('maximize',self)
        import runtime
        from PyQt6.QtWidgets import QApplication
        selected=QApplication.instance().property('xetalThemeDesign') or runtime.design()
        for button,name,caption in ((self.minimize,'windowMinimize','Minimize'),(self.maximize,'windowMaximize','Maximize')):
            button.setObjectName(name);button.setFixedSize(32,32);button.setToolTip(caption);button.setAccessibleName(caption)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor);style_close(button,selected);layout.addWidget(button)
        self.close=close_button(window,callback,title);self.close.setFocusPolicy(Qt.FocusPolicy.NoFocus);layout.addWidget(self.close)
        self.minimize.clicked.connect(window.showMinimized)
        self.maximize.clicked.connect(self.toggle)
        window.installEventFilter(self);self.sync()

    def sync(self):
        owner=self.owner()
        if owner is None:return
        restore=owner.isMaximized() or owner.isFullScreen()
        self.maximize.symbol='restore' if restore else 'maximize'
        caption='Restore' if restore else 'Maximize'
        self.maximize.setToolTip(caption);self.maximize.setAccessibleName(caption);self.maximize.update()

    def toggle(self):
        if (owner:=self.owner()) is not None:toggle_maximized(owner)

    def eventFilter(self,window,event):
        if event.type() in (QEvent.Type.WindowStateChange,QEvent.Type.Show):self.sync()
        return False


def window_controls(window,callback=None,title=None):
    if not hasattr(window,'xetal_window_controls'):
        window.xetal_window_controls=WindowControls(window,callback,title)
    return window.xetal_window_controls


class DialogHeaders(QObject):
    def eventFilter(self,window,event):
        if not isinstance(window,QDialog) or not window.isWindow() or window.property('xetalOverlay'):return False
        if event.type()==QEvent.Type.Show and not window.property('xetalCloseButton'):
            margins=window.contentsMargins()
            window.setContentsMargins(margins.left(),margins.top()+38,margins.right(),margins.bottom())
            header=QWidget(window);header.setObjectName('xetalDialogHeader')
            layout=QHBoxLayout(header);layout.setContentsMargins(8,0,0,0);layout.setSpacing(12)
            label=QLabel(window.windowTitle());label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet('background:transparent; font-weight:600;');layout.addWidget(label,1)
            layout.addWidget(close_button(window));window.xetal_header=header;window.xetal_header_title=label
            window.resize(window.width(),window.height()+38)
            header.setGeometry(8,3,max(40,window.width()-16),32);header.show();header.raise_()
        elif event.type()==QEvent.Type.Resize and hasattr(window,'xetal_header'):
            window.xetal_header.setGeometry(8,3,max(40,window.width()-16),32)
        elif event.type()==QEvent.Type.WindowTitleChange and hasattr(window,'xetal_header_title'):
            window.xetal_header_title.setText(window.windowTitle())
        return False


def install(app):
    if not hasattr(app,'window_chrome'):
        app.window_chrome=DialogHeaders(app);app.installEventFilter(app.window_chrome)
