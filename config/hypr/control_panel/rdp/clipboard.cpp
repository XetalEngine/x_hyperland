#include "clipboard.h"
#include <QBuffer>
#include <QImageReader>
#include <QMutexLocker>
#include <QtEndian>
#include <cstring>
#include <winpr/clipboard.h>

namespace FusionRdp {
QImage clipboardImage(const QByteArray &data, bool dib) {
    constexpr qsizetype maxBytes = 32*1024*1024;
    if (data.isEmpty() || data.size() > maxBytes) return {};
    QByteArray encoded = data;
    if (dib) {
        if (data.size() < 40) return {};
        const auto header = qFromLittleEndian<quint32>(data.constData());
        const auto bits = qFromLittleEndian<quint16>(data.constData()+14);
        const auto compression = qFromLittleEndian<quint32>(data.constData()+16);
        auto colors = qFromLittleEndian<quint32>(data.constData()+32);
        if ((header != 40 && header != 108 && header != 124) ||
            (compression != 0 && compression != 3) || bits == 0 || bits > 32) return {};
        if (!colors && bits <= 8) colors = 1U << bits;
        const quint64 offset = 14ULL + header + (header == 40 && compression == 3 ? 12 : 0) + quint64(colors)*4;
        if (offset > quint64(data.size()+14)) return {};
        QByteArray bmp(14, 0); bmp[0] = 'B'; bmp[1] = 'M';
        qToLittleEndian<quint32>(quint32(data.size()+14), bmp.data()+2);
        qToLittleEndian<quint32>(quint32(offset), bmp.data()+10);
        encoded = bmp + data;
    }
    QBuffer buffer(&encoded); buffer.open(QIODevice::ReadOnly);
    QImageReader reader(&buffer, dib ? "BMP" : "PNG");
    const auto size = reader.size();
    if (size.isEmpty() || quint64(size.width())*size.height() > 16*1024*1024) return {};
    return reader.read();
}
QByteArray imageDib(const QByteArray &png) {
    auto image = clipboardImage(png); if (image.isNull()) return {};
    QByteArray bmp; QBuffer buffer(&bmp); buffer.open(QIODevice::WriteOnly);
    if (!image.convertToFormat(QImage::Format_RGB32).save(&buffer, "BMP") || bmp.size() < 54) return {};
    return bmp.mid(14);
}
ClipboardBridge::ClipboardBridge(QObject *parent) : QObject(parent) {}
ClipboardBridge *ClipboardBridge::self(CliprdrClientContext *channel) { return static_cast<ClipboardBridge *>(channel->custom); }
void ClipboardBridge::attach(CliprdrClientContext *value) {
    QMutexLocker lock(&mutex);
    channel = value; channel->custom = this; ready = false;
    pendingKind = nextKind = None; ++revision;
    channel->MonitorReady = monitorReady; channel->ServerFormatList = serverFormats;
    channel->ServerFormatDataRequest = dataRequest; channel->ServerFormatDataResponse = dataResponse;
    channel->ServerCapabilities = [](CliprdrClientContext *, const CLIPRDR_CAPABILITIES *) -> UINT { return CHANNEL_RC_OK; };
    channel->ServerFormatListResponse = [](CliprdrClientContext *, const CLIPRDR_FORMAT_LIST_RESPONSE *) -> UINT { return CHANNEL_RC_OK; };
}
void ClipboardBridge::detach() { QMutexLocker lock(&mutex); channel = nullptr; ready = false; pendingKind = nextKind = None; ++revision; }
void ClipboardBridge::localChanged(const QString &value, const QByteArray &image) {
    QMutexLocker lock(&mutex);
    text = value; png = image; dib = imageDib(png); ++revision; nextKind = None;
    (void)announce();
}
UINT ClipboardBridge::announce() {
    if (!channel || !ready) return CHANNEL_RC_OK;
    CLIPRDR_FORMAT formats[3]{}; UINT32 count = 0;
    if (!text.isEmpty()) formats[count++].formatId = CF_UNICODETEXT;
    if (!png.isEmpty() && !dib.isEmpty()) {
        formats[count].formatId = PngFormat; formats[count++].formatName = const_cast<char *>("PNG");
        formats[count++].formatId = CF_DIB;
    }
    CLIPRDR_FORMAT_LIST list{}; list.common.msgType = CB_FORMAT_LIST;
    list.numFormats = count; list.formats = formats;
    return channel->ClientFormatList(channel, &list);
}
UINT ClipboardBridge::monitorReady(CliprdrClientContext *channel, const CLIPRDR_MONITOR_READY *) {
    auto *bridge = self(channel);
    QMutexLocker lock(&bridge->mutex);
    CLIPRDR_GENERAL_CAPABILITY_SET general{};
    general.capabilitySetType = CB_CAPSTYPE_GENERAL; general.capabilitySetLength = CB_CAPSTYPE_GENERAL_LEN;
    general.version = CB_CAPS_VERSION_2; general.generalFlags = CB_USE_LONG_FORMAT_NAMES;
    CLIPRDR_CAPABILITIES caps{}; caps.common.msgType = CB_CLIP_CAPS;
    caps.cCapabilitiesSets = 1; caps.capabilitySets = reinterpret_cast<CLIPRDR_CAPABILITY_SET *>(&general);
    auto rc = channel->ClientCapabilities(channel, &caps); if (rc != CHANNEL_RC_OK) return rc;
    bridge->ready = true; return bridge->announce();
}
UINT ClipboardBridge::requestNext() {
    if (!channel || nextKind == None || pendingKind != None) return CHANNEL_RC_OK;
    pendingKind = nextKind; pendingRevision = revision; nextKind = None;
    CLIPRDR_FORMAT_DATA_REQUEST request{}; request.common.msgType = CB_FORMAT_DATA_REQUEST;
    request.requestedFormatId = nextFormat;
    return channel->ClientFormatDataRequest(channel, &request);
}
UINT ClipboardBridge::serverFormats(CliprdrClientContext *channel, const CLIPRDR_FORMAT_LIST *formats) {
    auto *bridge = self(channel); QMutexLocker lock(&bridge->mutex);
    ++bridge->revision; bridge->nextKind = None;
    quint32 text = 0, png = 0, dib = 0;
    for (UINT32 i = 0; i < formats->numFormats; ++i) {
        const auto &format = formats->formats[i];
        if (format.formatId == CF_UNICODETEXT) text = format.formatId;
        if (format.formatId == CF_DIB || format.formatId == CF_DIBV5) dib = format.formatId;
        if (format.formatName && !std::strcmp(format.formatName, "PNG")) png = format.formatId;
    }
    if (png) { bridge->nextKind = Png; bridge->nextFormat = png; }
    else if (dib) { bridge->nextKind = Dib; bridge->nextFormat = dib; }
    else if (text) { bridge->nextKind = Text; bridge->nextFormat = text; }
    CLIPRDR_FORMAT_LIST_RESPONSE reply{}; reply.common.msgType = CB_FORMAT_LIST_RESPONSE; reply.common.msgFlags = CB_RESPONSE_OK;
    auto rc = channel->ClientFormatListResponse(channel, &reply); if (rc != CHANNEL_RC_OK) return rc;
    // Only one outstanding request: a newer announcement invalidates the old
    // response instead of interpreting its bytes using the newer format.
    return bridge->requestNext();
}
UINT ClipboardBridge::dataRequest(CliprdrClientContext *channel, const CLIPRDR_FORMAT_DATA_REQUEST *request) {
    auto *bridge = self(channel); QMutexLocker lock(&bridge->mutex); QByteArray data;
    if (request->requestedFormatId == CF_UNICODETEXT) {
        auto text = bridge->text; text.replace("\r\n", "\n"); text.replace('\n', "\r\n");
        data.resize((text.size()+1)*2);
        for (qsizetype i = 0; i < text.size(); ++i) qToLittleEndian<quint16>(text[i].unicode(), data.data()+i*2);
        data[data.size()-1] = data[data.size()-2] = 0;
    } else if (request->requestedFormatId == PngFormat) data = bridge->png;
    else if (request->requestedFormatId == CF_DIB) data = bridge->dib;
    CLIPRDR_FORMAT_DATA_RESPONSE reply{}; reply.common.msgType = CB_FORMAT_DATA_RESPONSE;
    reply.common.msgFlags = data.isEmpty() ? CB_RESPONSE_FAIL : CB_RESPONSE_OK;
    reply.common.dataLen = UINT32(data.size()); reply.requestedFormatData = reinterpret_cast<const BYTE *>(data.constData());
    return channel->ClientFormatDataResponse(channel, &reply);
}
UINT ClipboardBridge::dataResponse(CliprdrClientContext *channel, const CLIPRDR_FORMAT_DATA_RESPONSE *response) {
    auto *bridge = self(channel); QMutexLocker lock(&bridge->mutex); const auto kind = bridge->pendingKind;
    bridge->pendingKind = None;
    const bool valid = kind != None && bridge->pendingRevision == bridge->revision &&
        (response->common.msgFlags & CB_RESPONSE_OK) && response->requestedFormatData && response->common.dataLen <= 32*1024*1024;
    if (valid && kind == Text && response->common.dataLen % 2 == 0) {
        QString text;
        for (UINT32 i = 0; i < response->common.dataLen; i += 2) {
            const auto ch = qFromLittleEndian<quint16>(response->requestedFormatData+i);
            if (!ch) break; text.append(QChar(ch));
        }
        text.replace("\r\n", "\n"); emit bridge->received(text, {});
    } else if (valid && (kind == Png || kind == Dib)) {
        const QByteArray data(reinterpret_cast<const char *>(response->requestedFormatData), response->common.dataLen);
        const auto image = clipboardImage(data, kind == Dib);
        if (!image.isNull()) {
            QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly);
            if (image.save(&buffer, "PNG")) emit bridge->received({}, png);
        }
    }
    return bridge->requestNext();
}
}
