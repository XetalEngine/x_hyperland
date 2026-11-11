#include "view.h"
#include "clipboard.h"
#include <QApplication>
#include <QBuffer>
#include <QClipboard>
#include <QCloseEvent>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QScreen>
#include <QVBoxLayout>
#include <freerdp/input.h>

namespace FusionRdp {
DesktopView::DesktopView(QWidget *parent) : QWidget(parent) {
    setObjectName("rdpDesktop"); setFocusPolicy(Qt::StrongFocus); setMouseTracking(true);
    setAttribute(Qt::WA_InputMethodEnabled); setMinimumSize(320, 200);
}
void DesktopView::attach(Engine *value) { engine = value; }
void DesktopView::setFrame(const QImage &value) { frame = value; update(); }
QRect DesktopView::imageRect() const {
    if (frame.isNull()) return rect();
    auto size = frame.size(); size.scale(this->size(), Qt::KeepAspectRatio);
    return QRect(QPoint((width()-size.width())/2, (height()-size.height())/2), size);
}
QPoint DesktopView::remotePoint(QPointF point) const {
    const auto area = imageRect();
    if (frame.isNull() || area.isEmpty()) return {};
    return {qBound(0, int((point.x()-area.x())*frame.width()/area.width()), frame.width()-1),
            qBound(0, int((point.y()-area.y())*frame.height()/area.height()), frame.height()-1)};
}
void DesktopView::paintEvent(QPaintEvent *) {
    QPainter painter(this); painter.fillRect(rect(), QColor("#080c10"));
    if (!frame.isNull()) {
        painter.setRenderHint(QPainter::SmoothPixmapTransform, imageRect().size() != frame.size());
        painter.drawImage(imageRect(), frame);
    }
}
void DesktopView::resizeEvent(QResizeEvent *) { emit sizeChanged(size()); }
void DesktopView::mouseMoveEvent(QMouseEvent *event) {
    emit pointerMoved(event->position().toPoint());
    if (!engine || frame.isNull()) return;
    lastPoint = remotePoint(event->position()); engine->mouse(PTR_FLAGS_MOVE, lastPoint);
}
void DesktopView::button(QMouseEvent *event, bool down) {
    if (!engine || frame.isNull()) return;
    setFocus(Qt::MouseFocusReason); lastPoint = remotePoint(event->position());
    const auto button = event->button();
    if (down) heldButtons |= button; else heldButtons &= ~Qt::MouseButtons(button);
    quint16 flags = down ? PTR_FLAGS_DOWN : 0;
    if (button == Qt::LeftButton) flags |= PTR_FLAGS_BUTTON1;
    else if (button == Qt::RightButton) flags |= PTR_FLAGS_BUTTON2;
    else if (button == Qt::MiddleButton) flags |= PTR_FLAGS_BUTTON3;
    else if (button == Qt::BackButton || button == Qt::ForwardButton) {
        engine->mouse((down ? PTR_XFLAGS_DOWN : 0) | (button == Qt::BackButton ? PTR_XFLAGS_BUTTON1 : PTR_XFLAGS_BUTTON2), lastPoint, true);
        return;
    } else return;
    engine->mouse(flags, lastPoint); event->accept();
}
void DesktopView::mousePressEvent(QMouseEvent *event) { button(event, true); }
void DesktopView::mouseDoubleClickEvent(QMouseEvent *event) { button(event, true); }
void DesktopView::mouseReleaseEvent(QMouseEvent *event) { button(event, false); }
void DesktopView::wheelEvent(QWheelEvent *event) {
    if (!engine || frame.isNull()) return;
    const auto point = remotePoint(event->position());
    auto delta = event->angleDelta(); if (delta.isNull()) delta = event->pixelDelta();
    for (bool horizontal : {false, true}) {
        auto amount = horizontal ? delta.x() : delta.y();
        while (amount) {
            const int step = qBound(-255, amount, 255); amount -= step;
            engine->mouse((horizontal ? PTR_FLAGS_HWHEEL : PTR_FLAGS_WHEEL) |
                          (step < 0 ? PTR_FLAGS_WHEEL_NEGATIVE : 0) | (step & 0xff), point);
        }
    }
    event->accept();
}
void DesktopView::keyPressEvent(QKeyEvent *event) {
    const bool local = (event->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::ShiftModifier)) ==
                       (Qt::ControlModifier | Qt::AltModifier | Qt::ShiftModifier);
    if (local && (event->key() == Qt::Key_F || event->key() == Qt::Key_Home)) {
        releaseInput();
        if (event->key() == Qt::Key_F) emit fullscreenRequested(); else emit controlBarRequested();
        event->accept(); return;
    }
    if (!engine || frame.isNull()) return;
    const auto scan = scanCode(event->nativeScanCode(), event->key());
    if (scan) { heldKeys.insert(scan); engine->key(scan, true, event->isAutoRepeat()); }
    else if (!event->text().isEmpty()) engine->text(event->text());
    event->accept();
}
void DesktopView::keyReleaseEvent(QKeyEvent *event) {
    if (!engine || event->isAutoRepeat()) return;
    const auto scan = scanCode(event->nativeScanCode(), event->key());
    if (heldKeys.remove(scan)) engine->key(scan, false);
    event->accept();
}
void DesktopView::releaseInput() {
    if (engine) {
        for (auto scan : heldKeys) engine->key(scan, false);
        if (heldButtons & Qt::LeftButton) engine->mouse(PTR_FLAGS_BUTTON1, lastPoint);
        if (heldButtons & Qt::RightButton) engine->mouse(PTR_FLAGS_BUTTON2, lastPoint);
        if (heldButtons & Qt::MiddleButton) engine->mouse(PTR_FLAGS_BUTTON3, lastPoint);
        if (heldButtons & Qt::BackButton) engine->mouse(PTR_XFLAGS_BUTTON1, lastPoint, true);
        if (heldButtons & Qt::ForwardButton) engine->mouse(PTR_XFLAGS_BUTTON2, lastPoint, true);
    }
    heldKeys.clear(); heldButtons = {};
}
void DesktopView::focusOutEvent(QFocusEvent *event) { releaseInput(); QWidget::focusOutEvent(event); }
void DesktopView::inputMethodEvent(QInputMethodEvent *event) {
    if (engine && !frame.isNull() && !event->commitString().isEmpty()) engine->text(event->commitString());
    event->accept();
}
bool DesktopView::event(QEvent *event) {
    if (event->type() == QEvent::ShortcutOverride) { event->accept(); return true; }
    // Tab belongs to the remote desktop, not Qt's focus traversal.
    if (event->type() == QEvent::KeyPress) { keyPressEvent(static_cast<QKeyEvent *>(event)); return true; }
    if (event->type() == QEvent::KeyRelease) { keyReleaseEvent(static_cast<QKeyEvent *>(event)); return true; }
    return QWidget::event(event);
}

SessionWindow::SessionWindow(const Profile &p, const QString &password, QWidget *parent, bool startConnection)
    : QWidget(parent, Qt::Window), profile(p) {
    setObjectName("fusionRdpSession"); setWindowTitle(p.name + " — Fusion RDP");
    setWindowIcon(QIcon::fromTheme("preferences-desktop-remote-desktop")); setAttribute(Qt::WA_DeleteOnClose);
    resize(1280, 800); setMinimumSize(640, 400);
    if (auto *screen = QGuiApplication::primaryScreen()) resize(size().boundedTo(screen->availableGeometry().size()-QSize(32, 64)));
    auto *layout = new QVBoxLayout(this); layout->setContentsMargins(0,0,0,0); layout->setSpacing(0);
    view = new DesktopView(this); layout->addWidget(view);
    message = new QLabel("Connecting to " + p.host + "…", view); message->setObjectName("rdpSessionMessage");
    message->setTextFormat(Qt::PlainText);
    message->setWordWrap(true); message->setAlignment(Qt::AlignCenter);
    message->setStyleSheet("QLabel { color: #e6edf3; background: #101c24; border-radius: 10px; padding: 24px; }");
    bar = new QFrame(this); bar->setObjectName("rdpSessionBar");
    bar->setStyleSheet("QFrame#rdpSessionBar { background: palette(window); border: 1px solid palette(mid); border-radius: 9px; }");
    auto *controls = new QHBoxLayout(bar); controls->setContentsMargins(12, 6, 12, 6);
    status = new QLabel(p.name, bar); status->setMinimumWidth(90); status->setMaximumWidth(240);
    status->setTextFormat(Qt::PlainText); controls->addWidget(status);
    windowed = new QPushButton("Window mode", bar); windowed->setObjectName("rdpWindowMode");
    fullscreen = new QPushButton("Full screen", bar); fullscreen->setObjectName("rdpFullscreen");
    auto *secure = new QPushButton("Ctrl+Alt+Del", bar); secure->setObjectName("rdpSecureAttention");
    disconnectButton = new QPushButton("Disconnect", bar); disconnectButton->setObjectName("rdpDisconnect");
    for (auto *button : {windowed, fullscreen, secure, disconnectButton}) {
        button->setFocusPolicy(Qt::NoFocus); controls->addWidget(button);
    }
    fullscreen->setToolTip("Ctrl+Alt+Shift+F · show controls with Ctrl+Alt+Shift+Home");
    reveal = new QFrame(this); reveal->setObjectName("rdpBarReveal"); reveal->setFixedSize(120, 5);
    reveal->setStyleSheet("background: palette(highlight); border-radius: 2px;");
    reveal->setMouseTracking(true); reveal->installEventFilter(this); bar->installEventFilter(this);
    hideTimer.setSingleShot(true); hideTimer.setInterval(1800);
    connect(&hideTimer, &QTimer::timeout, this, [this] {
        if (connected && !bar->underMouse()) { bar->hide(); reveal->show(); reveal->raise(); }
    });
    resizeTimer.setSingleShot(true); resizeTimer.setInterval(250);
    connect(&resizeTimer, &QTimer::timeout, this, [this] { if (engine && connected) engine->resizeDesktop(view->size()); });
    connect(view, &DesktopView::sizeChanged, this, [this] { layoutBar(); resizeTimer.start(); });
    connect(view, &DesktopView::pointerMoved, this, [this](QPoint point) { if (point.y() <= 8) showBar(); });
    connect(view, &DesktopView::fullscreenRequested, this, &SessionWindow::toggleFullscreen);
    connect(view, &DesktopView::controlBarRequested, this, &SessionWindow::showBar);
    connect(fullscreen, &QPushButton::clicked, this, &SessionWindow::toggleFullscreen);
    connect(windowed, &QPushButton::clicked, this, [this] { showNormal(); fullscreen->setText("Full screen"); layoutBar(); showBar(); view->setFocus(); });
    connect(disconnectButton, &QPushButton::clicked, this, &QWidget::close);
    connect(secure, &QPushButton::clicked, this, [this] {
        if (!engine || !connected) return;
        view->releaseInput();
        const auto ctrl = scanCode(0, Qt::Key_Control), alt = scanCode(0, Qt::Key_Alt), del = scanCode(0, Qt::Key_Delete);
        engine->key(ctrl, true); engine->key(alt, true); engine->key(del, true);
        engine->key(del, false); engine->key(alt, false); engine->key(ctrl, false); view->setFocus();
    });
    if (startConnection) {
        engine = new Engine(p, password, size(), this); view->attach(engine);
        connect(engine, &Engine::frameAvailable, this, [this] { view->setFrame(engine->takeFrame()); message->hide(); });
        connect(engine, &Engine::cursorChanged, this, [this](const QImage &image, QPoint hotspot, bool hidden) {
            if (hidden) view->setCursor(Qt::BlankCursor);
            else if (image.isNull()) view->unsetCursor();
            else view->setCursor(QCursor(QPixmap::fromImage(image), hotspot.x(), hotspot.y()));
        });
        connect(engine, &Engine::statusChanged, this, [this](const QString &text) {
            status->setToolTip(text); if (!connected) message->setText(text);
            if (text.startsWith("Connection interrupted")) { message->setText(text); message->show(); showBar(); }
            else if (text == "Connected") message->hide();
        });
        connect(engine, &Engine::connected, this, &SessionWindow::connectionReady);
        connect(engine, &Engine::clipboardReceived, this, [this](const QString &text, const QByteArray &png) {
            if (!connected || !profile.clipboard || !isActiveWindow()) return;
            remoteClipboard = true;
            if (png.isEmpty()) QApplication::clipboard()->setText(text);
            else {
                const auto image = clipboardImage(png);
                if (!image.isNull()) QApplication::clipboard()->setImage(image);
            }
            remoteClipboard = false;
        });
        connect(QApplication::clipboard(), &QClipboard::dataChanged, this, &SessionWindow::publishClipboard);
        connect(engine, &Engine::ended, this, [this](const QString &error) {
            connected = false; view->releaseInput(); message->setText(error.isEmpty() ? "Disconnected" : error);
            message->setTextFormat(Qt::PlainText); message->show(); showBar();
            disconnectButton->setText("Close"); emit sessionEnded(error);
        });
        connect(engine, &QThread::finished, this, [this] { if (closing) close(); });
        connect(qApp, &QCoreApplication::aboutToQuit, engine, [this] { engine->stop(); engine->wait(); });
        engine->start();
    }
    layoutBar(); showBar();
}
SessionWindow::~SessionWindow() { if (engine) { engine->stop(); engine->wait(); } }
void SessionWindow::showSession() { if (profile.fullscreen) showFullScreen(); else show(); view->setFocus(); }
void SessionWindow::layoutBar() {
    if (!bar) return;
    windowed->setVisible(isFullScreen()); fullscreen->setVisible(!isFullScreen());
    status->setMaximumWidth(qBound(90, width()/4, 240));
    status->setText(status->fontMetrics().elidedText(profile.name, Qt::ElideRight, status->maximumWidth()));
    bar->adjustSize(); bar->move(qMax(0,(width()-bar->width())/2), 3);
    reveal->move((width()-reveal->width())/2, 0);
    message->setGeometry(qMax(12, (view->width()-620)/2), qMax(65, (view->height()-180)/2), qMin(620, view->width()-24), 180);
    bar->raise(); reveal->raise();
}
void SessionWindow::connectionReady() {
    connected = true; status->setText(profile.name); publishClipboard(); hideTimer.start(); resizeTimer.start();
}
void SessionWindow::showBar() { reveal->hide(); bar->show(); bar->raise(); if (connected) hideTimer.start(); }
void SessionWindow::toggleFullscreen() {
    view->releaseInput(); if (isFullScreen()) showNormal(); else showFullScreen();
    fullscreen->setText(isFullScreen() ? "Exit full screen" : "Full screen");
    layoutBar(); showBar(); view->setFocus();
}
void SessionWindow::publishClipboard() {
    if (!engine || !connected || remoteClipboard || !profile.clipboard || !isActiveWindow()) return;
    auto *data = QApplication::clipboard()->mimeData(); if (!data) return;
    QByteArray png;
    if (data->hasImage()) { auto image = qvariant_cast<QImage>(data->imageData()); QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG"); }
    engine->setClipboard(data->text(), png);
}
void SessionWindow::closeEvent(QCloseEvent *event) {
    if (engine && engine->isRunning()) {
        closing = true; view->releaseInput(); engine->stop(); message->setText("Disconnecting…"); message->show();
        disconnectButton->setEnabled(false); showBar(); event->ignore(); return;
    }
    event->accept();
}
void SessionWindow::resizeEvent(QResizeEvent *event) { QWidget::resizeEvent(event); layoutBar(); }
bool SessionWindow::event(QEvent *event) {
    // Copies made in another application must be announced when returning to
    // this session, even though this window missed the clipboard's change.
    if (event->type() == QEvent::WindowActivate)
        QTimer::singleShot(0, this, &SessionWindow::publishClipboard);
    if (event->type() == QEvent::WindowDeactivate && view) view->releaseInput();
    return QWidget::event(event);
}
bool SessionWindow::eventFilter(QObject *object, QEvent *event) {
    if (object == reveal && (event->type() == QEvent::Enter || event->type() == QEvent::MouseButtonPress)) showBar();
    if (object == bar && event->type() == QEvent::Leave && connected) hideTimer.start();
    if (object == bar && event->type() == QEvent::Enter) hideTimer.stop();
    return QWidget::eventFilter(object, event);
}
}
