#pragma once
#include "profile.h"
#include <QImage>
#include <QMutex>
#include <QPoint>
#include <QThread>
#include <atomic>
#include <functional>
#include <memory>
#include <freerdp/freerdp.h>

namespace FusionRdp {
// Kept separate from the window so protocol settings and input conversion can
// be checked without a server or a display connection.
bool configure(rdpSettings *settings, const Profile &profile, const QString &password, QSize size);
quint32 scanCode(quint32 nativeScanCode, int qtKey);
QSize desktopSize(QSize requested);

class Engine : public QThread {
    Q_OBJECT
public:
    Engine(Profile profile, QString password, QSize size, QObject *parent = nullptr);
    ~Engine() override;
    void stop();
    void key(quint32 scan, bool down, bool repeat = false);
    void text(const QString &text);
    void mouse(quint16 flags, QPoint position, bool extended = false);
    void resizeDesktop(QSize size);
    void setClipboard(const QString &text, const QByteArray &png);
    QImage takeFrame();
signals:
    void statusChanged(const QString &message);
    void connected();
    void ended(const QString &error);
    void frameAvailable();
    void cursorChanged(const QImage &image, const QPoint &hotspot, bool hidden);
    void clipboardReceived(const QString &text, const QByteArray &png);
protected:
    void run() override;
private:
    struct State;
    std::unique_ptr<State> state;
    void enqueue(std::function<void(rdpContext *)> command);
    void drain(rdpContext *context);
    friend struct State;
};
}
