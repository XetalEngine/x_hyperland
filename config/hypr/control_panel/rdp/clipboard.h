#pragma once
#include <QByteArray>
#include <QImage>
#include <QObject>
#include <QMutex>
#include <QString>
#include <freerdp/client/cliprdr.h>

namespace FusionRdp {
QByteArray imageDib(const QByteArray &png);
QImage clipboardImage(const QByteArray &data, bool dib = false);

class ClipboardBridge : public QObject {
    Q_OBJECT
public:
    explicit ClipboardBridge(QObject *parent = nullptr);
    void attach(CliprdrClientContext *channel);
    void detach();
    void localChanged(const QString &text, const QByteArray &png);
signals:
    void received(const QString &text, const QByteArray &png);
private:
    // Static clipboard channels may deliver callbacks from a FreeRDP thread,
    // while local changes arrive on Engine's worker.
    QMutex mutex;
    enum Kind { None, Text, Png, Dib };
    CliprdrClientContext *channel = nullptr;
    QString text;
    QByteArray png, dib;
    bool ready = false;
    quint64 revision = 0, pendingRevision = 0;
    Kind pendingKind = None, nextKind = None;
    quint32 nextFormat = 0;
    static constexpr quint32 PngFormat = 0xc001;
    UINT announce();
    UINT requestNext();
    static ClipboardBridge *self(CliprdrClientContext *channel);
    static UINT monitorReady(CliprdrClientContext *, const CLIPRDR_MONITOR_READY *);
    static UINT serverFormats(CliprdrClientContext *, const CLIPRDR_FORMAT_LIST *);
    static UINT dataRequest(CliprdrClientContext *, const CLIPRDR_FORMAT_DATA_REQUEST *);
    static UINT dataResponse(CliprdrClientContext *, const CLIPRDR_FORMAT_DATA_RESPONSE *);
};
}
