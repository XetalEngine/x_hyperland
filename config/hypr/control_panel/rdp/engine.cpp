#include "engine.h"
#include "clipboard.h"
#include <QBuffer>
#include <QMutexLocker>
#include <QSet>
#include <QUrl>
#include <QtEndian>
#include <deque>
#include <cstring>
#include <freerdp/client.h>
#include <freerdp/client/channels.h>
#include <freerdp/client/cliprdr.h>
#include <freerdp/client/disp.h>
#include <freerdp/codec/color.h>
#include <freerdp/gdi/gdi.h>
#include <freerdp/graphics.h>
#include <freerdp/input.h>
#include <freerdp/settings.h>
#include <freerdp/constants.h>
#include <winpr/input.h>
#include <winpr/synch.h>
#include <winpr/wlog.h>

namespace FusionRdp {
QSize desktopSize(QSize size) {
    // RDP display-control widths must be even, with a protocol limit of 8192.
    return {qBound(200, size.width(), 8192) & ~1, qBound(200, size.height(), 8192)};
}
quint32 scanCode(quint32 native, int key) {
    if (native) {
        const auto vk = GetVirtualKeyCodeFromKeycode(native, WINPR_KEYCODE_TYPE_XKB);
        if (vk && vk != 0xff) return GetVirtualScanCodeFromVirtualKeyCode(vk, WINPR_KBD_TYPE_IBM_ENHANCED);
    }
    // Synthetic events / platform plugins without native XKB keycodes.
    DWORD vk = 0;
    if (key >= Qt::Key_A && key <= Qt::Key_Z) vk = DWORD('A' + key - Qt::Key_A);
    else if (key >= Qt::Key_0 && key <= Qt::Key_9) vk = DWORD('0' + key - Qt::Key_0);
    else if (key >= Qt::Key_F1 && key <= Qt::Key_F24) vk = VK_F1 + key - Qt::Key_F1;
    else switch (key) {
        case Qt::Key_Escape: vk = VK_ESCAPE; break; case Qt::Key_Tab: vk = VK_TAB; break;
        case Qt::Key_Return: case Qt::Key_Enter: vk = VK_RETURN; break;
        case Qt::Key_Backspace: vk = VK_BACK; break; case Qt::Key_Space: vk = VK_SPACE; break;
        case Qt::Key_Control: vk = VK_LCONTROL; break; case Qt::Key_Shift: vk = VK_LSHIFT; break;
        case Qt::Key_Alt: vk = VK_LMENU; break; case Qt::Key_Meta: vk = VK_LWIN; break;
        case Qt::Key_Left: vk = VK_LEFT | KBDEXT; break; case Qt::Key_Right: vk = VK_RIGHT | KBDEXT; break;
        case Qt::Key_Up: vk = VK_UP | KBDEXT; break; case Qt::Key_Down: vk = VK_DOWN | KBDEXT; break;
        case Qt::Key_Home: vk = VK_HOME | KBDEXT; break; case Qt::Key_End: vk = VK_END | KBDEXT; break;
        case Qt::Key_PageUp: vk = VK_PRIOR | KBDEXT; break; case Qt::Key_PageDown: vk = VK_NEXT | KBDEXT; break;
        case Qt::Key_Delete: vk = VK_DELETE | KBDEXT; break; case Qt::Key_Insert: vk = VK_INSERT | KBDEXT; break;
        default: break;
    }
    return vk ? GetVirtualScanCodeFromVirtualKeyCode(vk, WINPR_KBD_TYPE_IBM_ENHANCED) : 0;
}

bool configure(rdpSettings *s, const Profile &p, const QString &password, QSize size) {
    bool ok = true;
    const auto boolean = [&](FreeRDP_Settings_Keys_Bool key, bool value) { ok = freerdp_settings_set_bool(s, key, value) && ok; };
    const auto number = [&](FreeRDP_Settings_Keys_UInt32 key, quint32 value) { ok = freerdp_settings_set_uint32(s, key, value) && ok; };
    const auto string = [&](FreeRDP_Settings_Keys_String key, const QString &value) {
        auto bytes = value.toUtf8(); ok = freerdp_settings_set_string(s, key, bytes.constData()) && ok; bytes.fill('\0');
    };
    auto host = p.host;
    if (host.startsWith('[') && host.endsWith(']')) host = host.mid(1, host.size()-2);
    string(FreeRDP_ServerHostname, host); number(FreeRDP_ServerPort, quint32(p.port));
    auto user = p.username; auto domain = p.domain;
    if (domain.isEmpty() && user.contains('\\')) { domain = user.section('\\', 0, 0); user = user.section('\\', 1); }
    string(FreeRDP_Username, user); string(FreeRDP_Domain, domain); string(FreeRDP_Password, password);
    string(FreeRDP_ClientHostname, "HyperFusion");
    size = desktopSize(size);
    number(FreeRDP_DesktopWidth, size.width()); number(FreeRDP_DesktopHeight, size.height());
    number(FreeRDP_ColorDepth, 32); number(FreeRDP_KeyboardLayout, p.keyboardLayout);
    number(FreeRDP_KeyboardType, WINPR_KBD_TYPE_IBM_ENHANCED);
    number(FreeRDP_TcpConnectTimeout, 10000); number(FreeRDP_AutoReconnectMaxRetries, 3);
    boolean(FreeRDP_SoftwareGdi, true); boolean(FreeRDP_SupportGraphicsPipeline, true);
    // This engine already has its own worker. Keep graphics/display channel
    // callbacks there so they cannot race the GDI buffer or resize commands.
    boolean(FreeRDP_SynchronousDynamicChannels, true);
    boolean(FreeRDP_GfxH264, true); boolean(FreeRDP_GfxAVC444, true);
    boolean(FreeRDP_SupportDisplayControl, p.dynamicResolution);
    boolean(FreeRDP_DynamicResolutionUpdate, p.dynamicResolution);
    boolean(FreeRDP_AutoReconnectionEnabled, p.reconnect);
    boolean(FreeRDP_RedirectClipboard, p.clipboard); boolean(FreeRDP_AudioPlayback, p.sound);
    boolean(FreeRDP_AudioCapture, p.microphone); boolean(FreeRDP_RedirectPrinters, p.printers);
    boolean(FreeRDP_DeviceRedirection, p.shareFolder || p.printers);
    boolean(FreeRDP_IgnoreCertificate, p.autoAcceptCertificate);
    boolean(FreeRDP_AutoAcceptCertificate, p.autoAcceptCertificate);
    boolean(FreeRDP_AutoDenyCertificate, !p.autoAcceptCertificate);
    boolean(FreeRDP_RedirectHomeDrive, false); boolean(FreeRDP_RedirectDrives, false);
    boolean(FreeRDP_AutoLogonEnabled, true); boolean(FreeRDP_ConsoleSession, p.adminSession);
    boolean(FreeRDP_UseCommonStdioCallbacks, false);
    boolean(FreeRDP_AllowFontSmoothing, true); boolean(FreeRDP_AllowDesktopComposition, true);
    ok = freerdp_set_connection_type(s, CONNECTION_TYPE_AUTODETECT) && ok;
    if (p.shareFolder) {
        const auto path = p.sharedFolder.toUtf8();
        const char *args[] = {"drive", "Home", path.constData()};
        ok = freerdp_client_add_device_channel(s, 3, args) && ok;
    }
    if (p.sound) { const char *args[] = {"rdpsnd"}; ok = freerdp_client_add_static_channel(s, 1, args) && ok; }
    if (p.microphone) { const char *args[] = {"audin"}; ok = freerdp_client_add_dynamic_channel(s, 1, args) && ok; }
    if (!p.gateway.isEmpty()) {
        const auto url = QUrl("https://" + p.gateway);
        if (url.host().isEmpty() || url.port(443) <= 0) return false;
        boolean(FreeRDP_GatewayEnabled, true); boolean(FreeRDP_GatewayUseSameCredentials, true);
        string(FreeRDP_GatewayHostname, url.host()); number(FreeRDP_GatewayPort, url.port(443));
        string(FreeRDP_GatewayUsername, user); string(FreeRDP_GatewayDomain, domain);
        string(FreeRDP_GatewayPassword, password);
    }
    return ok;
}

struct Engine::State {
    struct Context { rdpClientContext common; State *state; };
    Engine *owner;
    Profile profile;
    QString password;
    QString authenticationError;
    QSize size;
    std::atomic_bool stopping{false};
    QMutex contextMutex, commandsMutex, frameMutex;
    rdpContext *context = nullptr;
    std::deque<std::function<void(rdpContext *)>> commands;
    HANDLE wake = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    QImage frame;
    bool framePosted = false;
    std::unique_ptr<ClipboardBridge> clipboard;
    DispClientContext *display = nullptr;
    bool displayReady = false;

    State(Engine *owner, Profile p, QString password, QSize size)
        : owner(owner), profile(std::move(p)), password(std::move(password)), size(desktopSize(size)) {}
    ~State() { if (wake) CloseHandle(wake); password.fill(QChar::Null); }
    static State *get(rdpContext *context) { return reinterpret_cast<Context *>(context)->state; }

    static BOOL beforeConnect(freerdp *instance) {
        auto *context = instance->context;
        return PubSub_SubscribeChannelConnected(context->pubSub, channelConnected) >= 0 &&
               PubSub_SubscribeChannelDisconnected(context->pubSub, channelDisconnected) >= 0;
    }
    static BOOL beginPaint(rdpContext *context) {
        if (context->gdi && context->gdi->primary)
            context->gdi->primary->hdc->hwnd->invalid->null = TRUE;
        return TRUE;
    }
    static BOOL endPaint(rdpContext *context) {
        auto *s = get(context); auto *gdi = context->gdi;
        if (!gdi || !gdi->primary_buffer || gdi->primary->hdc->hwnd->invalid->null) return TRUE;
        bool notify = false;
        {
            QMutexLocker lock(&s->frameMutex);
            s->frame = QImage(gdi->primary_buffer, gdi->width, gdi->height, gdi->stride, QImage::Format_RGB32).copy();
            notify = !s->framePosted; s->framePosted = true;
        }
        if (notify) emit s->owner->frameAvailable();
        return TRUE;
    }
    static BOOL resized(rdpContext *context) {
        const auto width = freerdp_settings_get_uint32(context->settings, FreeRDP_DesktopWidth);
        const auto height = freerdp_settings_get_uint32(context->settings, FreeRDP_DesktopHeight);
        if (width > 8192 || height > 8192 || !width || !height) return FALSE;
        return gdi_resize(context->gdi, width, height);
    }
    static BOOL cursorNew(rdpContext *, rdpPointer *) { return TRUE; }
    static void cursorFree(rdpContext *, rdpPointer *) {}
    static BOOL cursorSet(rdpContext *context, rdpPointer *pointer) {
        if (pointer->width > 512 || pointer->height > 512) return FALSE;
        QImage image(pointer->width, pointer->height, QImage::Format_ARGB32);
        if (image.isNull()) return FALSE;
        if (!freerdp_image_copy_from_pointer_data(image.bits(), PIXEL_FORMAT_BGRA32, image.bytesPerLine(), 0, 0,
            pointer->width, pointer->height, pointer->xorMaskData, pointer->lengthXorMask,
            pointer->andMaskData, pointer->lengthAndMask, pointer->xorBpp, &context->gdi->palette)) return FALSE;
        emit get(context)->owner->cursorChanged(image, QPoint(pointer->xPos, pointer->yPos), false);
        return TRUE;
    }
    static BOOL cursorNull(rdpContext *context) { emit get(context)->owner->cursorChanged({}, {}, true); return TRUE; }
    static BOOL cursorDefault(rdpContext *context) { emit get(context)->owner->cursorChanged({}, {}, false); return TRUE; }
    static BOOL cursorPosition(rdpContext *, UINT32, UINT32) { return TRUE; }
    static BOOL afterConnect(freerdp *instance) {
        auto *context = instance->context;
        if (!gdi_init(instance, PIXEL_FORMAT_BGRX32)) return FALSE;
        context->update->BeginPaint = beginPaint; context->update->EndPaint = endPaint;
        context->update->DesktopResize = resized;
        rdpPointer pointer{}; pointer.size = sizeof(rdpPointer);
        pointer.New = cursorNew; pointer.Free = cursorFree; pointer.Set = cursorSet;
        pointer.SetNull = cursorNull; pointer.SetDefault = cursorDefault; pointer.SetPosition = cursorPosition;
        graphics_register_pointer(context->graphics, &pointer);
        emit get(context)->owner->connected();
        return TRUE;
    }
    static void afterDisconnect(freerdp *instance) {
        auto *context = instance->context; auto *s = get(context);
        PubSub_UnsubscribeChannelConnected(context->pubSub, channelConnected);
        PubSub_UnsubscribeChannelDisconnected(context->pubSub, channelDisconnected);
        if (s->clipboard) s->clipboard->detach();
        s->display = nullptr; s->displayReady = false;
        gdi_free(instance);
    }
    static BOOL clientNew(freerdp *instance, rdpContext *) {
        instance->PreConnect = beforeConnect; instance->PostConnect = afterConnect;
        instance->PostDisconnect = afterDisconnect;
        // GUI clients must never fall back to a blocking stdin password prompt.
        instance->AuthenticateEx = [](freerdp *instance, char **, char **, char **, rdp_auth_reason) -> BOOL {
            get(instance->context)->authenticationError = "The server needs valid credentials. Check the username, domain and password, then connect again.";
            return FALSE;
        };
        instance->VerifyCertificateEx = [](freerdp *, const char *, UINT16, const char *, const char *, const char *, const char *, DWORD) -> DWORD { return 0; };
        instance->VerifyChangedCertificateEx = [](freerdp *, const char *, UINT16, const char *, const char *, const char *, const char *, const char *, const char *, const char *, DWORD) -> DWORD { return 0; };
        instance->GetAccessToken = nullptr;
        instance->PresentGatewayMessage = nullptr;
        instance->RetryDialog = nullptr;
        return TRUE;
    }
    void resize() {
        if (!display || !displayReady || !profile.dynamicResolution) return;
        DISPLAY_CONTROL_MONITOR_LAYOUT layout{};
        layout.Flags = DISPLAY_CONTROL_MONITOR_PRIMARY;
        layout.Width = size.width(); layout.Height = size.height();
        layout.PhysicalWidth = qMax(10, qRound(size.width()*25.4/96));
        layout.PhysicalHeight = qMax(10, qRound(size.height()*25.4/96));
        layout.DesktopScaleFactor = 100; layout.DeviceScaleFactor = 100;
        if (display->SendMonitorLayout(display, 1, &layout) != CHANNEL_RC_OK)
            emit owner->statusChanged("The server could not resize its desktop; the view will scale to fit.");
    }
    static UINT displayCaps(DispClientContext *display, UINT32, UINT32, UINT32) {
        auto *s = static_cast<State *>(display->custom); s->displayReady = true; s->resize(); return CHANNEL_RC_OK;
    }
    static void channelConnected(void *context, const ChannelConnectedEventArgs *event) {
        auto *s = get(static_cast<rdpContext *>(context));
        if (!std::strcmp(event->name, CLIPRDR_SVC_CHANNEL_NAME)) {
            s->clipboard->attach(static_cast<CliprdrClientContext *>(event->pInterface));
        } else if (!std::strcmp(event->name, DISP_DVC_CHANNEL_NAME)) {
            s->display = static_cast<DispClientContext *>(event->pInterface);
            s->display->custom = s; s->display->DisplayControlCaps = displayCaps;
        } else freerdp_client_OnChannelConnectedEventHandler(context, event);
    }
    static void channelDisconnected(void *context, const ChannelDisconnectedEventArgs *event) {
        auto *s = get(static_cast<rdpContext *>(context));
        if (!std::strcmp(event->name, CLIPRDR_SVC_CHANNEL_NAME)) { if (s->clipboard) s->clipboard->detach(); }
        else if (!std::strcmp(event->name, DISP_DVC_CHANNEL_NAME)) { s->display = nullptr; s->displayReady = false; }
        else freerdp_client_OnChannelDisconnectedEventHandler(context, event);
    }

};

Engine::Engine(Profile profile, QString password, QSize size, QObject *parent)
    : QThread(parent), state(std::make_unique<State>(this, std::move(profile), std::move(password), size)) {}
Engine::~Engine() { stop(); wait(); }
void Engine::stop() {
    state->stopping = true;
    QMutexLocker lock(&state->contextMutex);
    if (state->context) freerdp_abort_connect_context(state->context);
    if (state->wake) SetEvent(state->wake);
}
void Engine::enqueue(std::function<void(rdpContext *)> command) {
    if (state->stopping || !isRunning()) return;
    QMutexLocker lock(&state->commandsMutex);
    state->commands.emplace_back(std::move(command));
    if (state->wake) SetEvent(state->wake);
}
void Engine::drain(rdpContext *context) {
    std::deque<std::function<void(rdpContext *)>> commands;
    { QMutexLocker lock(&state->commandsMutex); commands.swap(state->commands); if (state->wake) ResetEvent(state->wake); }
    for (const auto &command : commands) { if (state->stopping) break; command(context); }
}
void Engine::key(quint32 scan, bool down, bool repeat) {
    if (!scan) return;
    enqueue([=](rdpContext *c) { (void)freerdp_input_send_keyboard_event_ex(c->input, down, repeat, scan); });
}
void Engine::text(const QString &text) {
    enqueue([text](rdpContext *c) {
        for (const auto ch : text) {
            (void)freerdp_input_send_unicode_keyboard_event(c->input, 0, ch.unicode());
            (void)freerdp_input_send_unicode_keyboard_event(c->input, KBD_FLAGS_RELEASE, ch.unicode());
        }
    });
}
void Engine::mouse(quint16 flags, QPoint point, bool extended) {
    enqueue([=](rdpContext *c) {
        if (extended) (void)freerdp_input_send_extended_mouse_event(c->input, flags, point.x(), point.y());
        else (void)freerdp_input_send_mouse_event(c->input, flags, point.x(), point.y());
    });
}
void Engine::resizeDesktop(QSize size) {
    enqueue([this, size](rdpContext *) { state->size = desktopSize(size); state->resize(); });
}
void Engine::setClipboard(const QString &text, const QByteArray &png) {
    enqueue([this, text, png](rdpContext *) {
        if (state->clipboard) state->clipboard->localChanged(text, png);
    });
}
QImage Engine::takeFrame() {
    QMutexLocker lock(&state->frameMutex); state->framePosted = false; return state->frame;
}
void Engine::run() {
    if (state->stopping) { emit ended({}); return; }
    RDP_CLIENT_ENTRY_POINTS entry{}; entry.Size = sizeof(entry); entry.Version = RDP_CLIENT_INTERFACE_VERSION;
    entry.ContextSize = sizeof(State::Context); entry.ClientNew = State::clientNew;
    auto *context = freerdp_client_context_new(&entry);
    if (!context) { emit ended("Could not initialize the RDP engine."); return; }
    reinterpret_cast<State::Context *>(context)->state = state.get();
    state->clipboard = std::make_unique<ClipboardBridge>();
    QObject::connect(state->clipboard.get(), &ClipboardBridge::received, this, &Engine::clipboardReceived);
    auto *instance = context->instance;
    QString failure;
    if (!configure(context->settings, state->profile, state->password, state->size))
        failure = "Could not prepare these RDP connection options.";
    state->password.fill(QChar::Null); state->password.clear();
    { QMutexLocker lock(&state->contextMutex); state->context = context; }
    emit statusChanged("Connecting to " + state->profile.host + "…");
    if (failure.isEmpty() && !state->stopping && freerdp_connect(instance)) {
        while (!state->stopping && !freerdp_shall_disconnect_context(context)) {
            drain(context);
            HANDLE handles[MAXIMUM_WAIT_OBJECTS]{};
            auto count = freerdp_get_event_handles(context, handles, MAXIMUM_WAIT_OBJECTS-1);
            if (!count) { failure = "The RDP connection stopped responding."; break; }
            if (state->wake) handles[count++] = state->wake;
            const auto result = WaitForMultipleObjects(count, handles, FALSE, 100);
            if (result == WAIT_FAILED) { failure = "Could not wait for the RDP connection."; break; }
            if (result == WAIT_TIMEOUT) continue;
            if (!freerdp_check_event_handles(context)) {
                if (!state->stopping && state->profile.reconnect) {
                    emit statusChanged("Connection interrupted. Reconnecting…");
                    if (client_auto_reconnect(instance)) { emit statusChanged("Connected"); continue; }
                }
                break;
            }
        }
    }
    const auto code = freerdp_get_last_error(context);
    if (failure.isEmpty() && !state->authenticationError.isEmpty()) failure = state->authenticationError;
    if (failure.isEmpty() && code != FREERDP_ERROR_SUCCESS && !state->stopping)
        failure = QString::fromUtf8(freerdp_get_last_error_string(code)) + " (" + QString::fromUtf8(freerdp_get_last_error_name(code)) + ")";
    freerdp_disconnect(instance);
    { QMutexLocker lock(&state->contextMutex); state->context = nullptr; }
    state->clipboard.reset();
    freerdp_client_context_free(context);
    emit ended(state->stopping ? QString() : failure);
}
}
