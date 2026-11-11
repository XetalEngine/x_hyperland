#pragma once
#include "engine.h"
#include <QFrame>
#include <QLabel>
#include <QPushButton>
#include <QSet>
#include <QTimer>
#include <QWidget>

namespace FusionRdp {
class DesktopView : public QWidget {
    Q_OBJECT
public:
    explicit DesktopView(QWidget *parent = nullptr);
    void attach(Engine *engine);
    void releaseInput();
    QRect imageRect() const;
    QPoint remotePoint(QPointF point) const;
    void setFrame(const QImage &frame);
signals:
    void pointerMoved(const QPoint &point);
    void fullscreenRequested();
    void controlBarRequested();
    void sizeChanged(const QSize &size);
protected:
    void paintEvent(QPaintEvent *) override;
    void resizeEvent(QResizeEvent *) override;
    void mouseMoveEvent(QMouseEvent *) override;
    void mousePressEvent(QMouseEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;
    void mouseDoubleClickEvent(QMouseEvent *) override;
    void wheelEvent(QWheelEvent *) override;
    void keyPressEvent(QKeyEvent *) override;
    void keyReleaseEvent(QKeyEvent *) override;
    void focusOutEvent(QFocusEvent *) override;
    void inputMethodEvent(QInputMethodEvent *) override;
    bool event(QEvent *) override;
private:
    Engine *engine = nullptr;
    QImage frame;
    QSet<quint32> heldKeys;
    Qt::MouseButtons heldButtons;
    QPoint lastPoint;
    void button(QMouseEvent *event, bool down);
};

class SessionWindow : public QWidget {
    Q_OBJECT
public:
    SessionWindow(const Profile &profile, const QString &password, QWidget *parent = nullptr,
                  bool startConnection = true);
    ~SessionWindow() override;
    void showSession();
signals:
    void sessionEnded(const QString &error);
private slots:
    void connectionReady();
protected:
    void closeEvent(QCloseEvent *) override;
    void resizeEvent(QResizeEvent *) override;
    bool event(QEvent *) override;
    bool eventFilter(QObject *, QEvent *) override;
private:
    Profile profile;
    DesktopView *view = nullptr;
    Engine *engine = nullptr;
    QFrame *bar = nullptr, *reveal = nullptr;
    QLabel *status = nullptr, *message = nullptr;
    QPushButton *fullscreen, *disconnectButton, *windowed;
    QTimer hideTimer, resizeTimer;
    bool closing = false, connected = false, remoteClipboard = false;
    void layoutBar();
    void showBar();
    void toggleFullscreen();
    void publishClipboard();
};
}
