"""Consistent close controls for our floating tools and their Qt dialogs."""
from PyQt6.QtCore import Qt,QEvent,QObject
from PyQt6.QtWidgets import QDialog,QHBoxLayout,QLabel,QToolButton,QWidget


def style_close(button,design=None):
    import runtime
    if design in ('breakpoint','binaryknife'):
        p=runtime.colors(style=design)
        hover=f"background:{p['Highlight']}; color:{p['Text']}; border-color:{p['Accent']};"
        pressed=f"background:{p['Mid']};"
    else:
        hover='background:#663544; color:#fff1f3; border-color:#b3687f;'
        pressed='background:#8a4052;'
    button.setStyleSheet('QToolButton {color:palette(window-text); background:transparent; border:1px solid transparent; '
                        'border-radius:'+('4' if design=='binaryknife' else '6')+'px; padding:0; font-size:23px;} '
                        'QToolButton:hover {'+hover+'} QToolButton:pressed {'+pressed+'} '
                        'QToolButton:focus {border-color:palette(highlight);}')


def close_button(window,callback=None,title=None):
    button=QToolButton(window);button.setObjectName('windowClose');button.setText('×');button.setFixedSize(32,32)
    caption=title or ('Close '+window.windowTitle()).strip()
    button.setToolTip(caption);button.setAccessibleName(caption);button.setCursor(Qt.CursorShape.PointingHandCursor)
    import runtime
    from PyQt6.QtWidgets import QApplication
    selected=QApplication.instance().property('xetalThemeDesign') or runtime.design()
    style_close(button,selected)
    button.clicked.connect(callback or window.close)
    window.setProperty('xetalCloseButton',True)
    return button


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
