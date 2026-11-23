#include "profile.h"
#include "credentials.h"
#include "engine.h"
#include "clipboard.h"
#include "page.h"
#include "hosting_page.h"
#include "vnc.h"
#include "view.h"
#include <QtTest>
#include <QtWidgets>
#include <freerdp/client.h>
#include <freerdp/codec/color.h>
#include <freerdp/settings.h>
#include <winpr/input.h>
#include <winpr/clipboard.h>
#include <memory>
#include <thread>

using namespace FusionRdp;
namespace {
Profile profile() {
    Profile p; p.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    p.name = "Office PC"; p.host = "office.example.test"; p.username = "tester"; return p;
}
QByteArray pngImage() {
    QImage image(13, 9, QImage::Format_RGB32); image.fill(QColor(220, 30, 70));
    QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG"); return png;
}
bool hostingFixture(const QString &root) {
    QDir().mkpath(root + "/desktop_services");
    QFile helper(root + "/desktop_services/remote_cli.py");
    if (!helper.open(QIODevice::WriteOnly)) return false;
    helper.write(R"PY(import json,sys,time
from pathlib import Path
p=Path(__file__).resolve().parents[1]
action=sys.argv[1];request=json.load(sys.stdin)
with (p/'requests').open('a') as f:f.write(json.dumps(dict(action=action,argv=sys.argv,request=request))+'\n')
if action=='status' and (p/'slow').exists():time.sleep(.25)
if action=='start' and (p/'fail-start').exists():
 print(json.dumps(dict(ok=False,error='Fixture listener could not bind',has_password=True,status=dict(running=False,log=''),components=dict(vnc=True,rdp=True))));sys.exit(1)
prefs=dict(version=1,protocol='vnc',address='127.0.0.1',port=5900,output='',fps=30,username='fixture',control=False,autostart=False)
if (p/'settings').exists():prefs=json.loads((p/'settings').read_text())
if action in ('save','start'):
 prefs=request['values'];(p/'settings').write_text(json.dumps(prefs))
if action=='start':(p/'running').touch()
if action=='stop':(p/'running').unlink(missing_ok=True)
running=(p/'running').exists()
status=dict(running=running,listening=running,connections=int((p/'clients').read_text()) if (p/'clients').exists() else 0,log='',process=dict(protocol=prefs['protocol'],output='DP-1',address=prefs['address'],port=prefs['port'],control=prefs['control'],fingerprint='SHA256:00:11:22') if running else None)
if request.get('password'):(p/'missing-password').unlink(missing_ok=True)
result=dict(ok=True,has_password=not (p/'missing-password').exists(),status=status,components=dict(vnc=True,rdp=True))
if action=='refresh':result.update(preferences=prefs,monitors=[dict(name='DP-1',description='Fixture display')],addresses=['127.0.0.1','192.0.2.10'])
print(json.dumps(result))
)PY");
    return true;
}
struct ClipPeer {
    ClipboardBridge bridge;
    CliprdrClientContext channel{};
    QList<quint32> announced, requests;
    QByteArray response;
    quint16 responseFlags = 0;
    ClipPeer() {
        channel.handle = this;
        channel.ClientCapabilities = [](CliprdrClientContext *, const CLIPRDR_CAPABILITIES *) -> UINT { return CHANNEL_RC_OK; };
        channel.ClientFormatList = [](CliprdrClientContext *c, const CLIPRDR_FORMAT_LIST *list) -> UINT {
            auto *p = static_cast<ClipPeer *>(c->handle); p->announced.clear();
            for (UINT32 i=0; i<list->numFormats; ++i) p->announced.append(list->formats[i].formatId);
            return CHANNEL_RC_OK;
        };
        channel.ClientFormatListResponse = [](CliprdrClientContext *, const CLIPRDR_FORMAT_LIST_RESPONSE *) -> UINT { return CHANNEL_RC_OK; };
        channel.ClientFormatDataRequest = [](CliprdrClientContext *c, const CLIPRDR_FORMAT_DATA_REQUEST *request) -> UINT {
            static_cast<ClipPeer *>(c->handle)->requests.append(request->requestedFormatId); return CHANNEL_RC_OK;
        };
        channel.ClientFormatDataResponse = [](CliprdrClientContext *c, const CLIPRDR_FORMAT_DATA_RESPONSE *reply) -> UINT {
            auto *p = static_cast<ClipPeer *>(c->handle); p->responseFlags = reply->common.msgFlags;
            p->response = QByteArray(reinterpret_cast<const char *>(reply->requestedFormatData), reply->common.dataLen); return CHANNEL_RC_OK;
        };
        bridge.attach(&channel); CLIPRDR_MONITOR_READY ready{}; channel.MonitorReady(&channel, &ready);
    }
    void offer(quint32 id, const char *name = nullptr) {
        CLIPRDR_FORMAT format{id, const_cast<char *>(name)}; CLIPRDR_FORMAT_LIST list{}; list.numFormats=1; list.formats=&format;
        QCOMPARE(channel.ServerFormatList(&channel,&list), UINT(CHANNEL_RC_OK));
    }
    void reply(const QByteArray &data, quint16 flags = CB_RESPONSE_OK) {
        CLIPRDR_FORMAT_DATA_RESPONSE response{}; response.common.msgFlags=flags; response.common.dataLen=data.size();
        response.requestedFormatData=reinterpret_cast<const BYTE *>(data.constData());
        QCOMPARE(channel.ServerFormatDataResponse(&channel,&response), UINT(CHANNEL_RC_OK));
    }
    void request(quint32 id) { CLIPRDR_FORMAT_DATA_REQUEST request{}; request.requestedFormatId=id; channel.ServerFormatDataRequest(&channel,&request); }
};
}

class RdpTests : public QObject {
    Q_OBJECT
private slots:
    void initTestCase() {
        qApp->setQuitOnLastWindowClosed(false); qApp->setStyle("Fusion");
        const auto path = qEnvironmentVariable("RDP_TEST_THEME");
        if (!path.isEmpty()) {
            QFile file(path); QVERIFY(file.open(QIODevice::ReadOnly));
            const auto theme = QJsonDocument::fromJson(file.readAll()).object();
            const auto colors = theme["colors"].toObject(); QPalette palette;
            const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
            for (auto it=colors.begin(); it!=colors.end(); ++it) {
                int role = roles.keyToValue(it.key().toUtf8()); if (role>=0) palette.setColor(QPalette::All,QPalette::ColorRole(role),QColor(it.value().toString()));
            }
            qApp->setPalette(palette); qApp->setFont(QFont(theme["font"].toString("Noto Sans"),10));
            qApp->setStyleSheet(theme["stylesheet"].toString());
        }
    }
    void profilesRoundTripWithoutPasswords() {
        QTemporaryDir temp; ProfileStore store(temp.path()+"/private/connections.json"); auto p=profile();
        p.gateway="gateway.example.test:443"; p.domain="WORK"; QString error;
        QVERIFY2(store.save(p,&error),qPrintable(error)); auto entries=store.load(&error); QVERIFY(error.isEmpty()); QCOMPARE(entries.size(),1);
        QCOMPARE(entries[0].json(),p.json()); QFile file(temp.path()+"/private/connections.json"); QVERIFY(file.open(QIODevice::ReadOnly));
        const auto raw=file.readAll(); QVERIFY(!raw.contains("password\""));
        QCOMPARE(file.permissions() & (QFile::ReadOther|QFile::WriteOther|QFile::ReadGroup|QFile::WriteGroup), QFile::Permissions{});
        p.name="Changed"; QVERIFY(store.save(p,&error)); QCOMPARE(store.load().size(),1); QCOMPARE(store.load()[0].name,p.name);
        auto other=profile(); QVERIFY(store.save(other,&error)); QVERIFY(store.remove(p.id,&error)); QCOMPARE(store.load()[0].id,other.id);
    }
    void corruptedProfilesAreNotOverwritten() {
        QTemporaryDir temp; const auto path=temp.path()+"/connections.json"; QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("broken!"); file.close();
        ProfileStore store(path); QString error; QVERIFY(!store.save(profile(),&error)); QVERIFY(!error.isEmpty());
        QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(),QByteArray("broken!"));
    }
    void credentialsAreBoundToThePcAndAccount() {
        auto p=profile(); auto edited=p; edited.host="different.example.test"; QVERIFY(p.credentialKey()!=edited.credentialKey());
        edited=p; edited.username="someoneelse"; QVERIFY(p.credentialKey()!=edited.credentialKey());
        edited=p; edited.gateway="gateway.test"; QVERIFY(p.credentialKey()!=edited.credentialKey());
        edited=p; edited.name="New label"; QCOMPARE(p.credentialKey(),edited.credentialKey());
        edited=p; edited.protocol="vnc"; QVERIFY(p.credentialKey()!=edited.credentialKey());
    }
    void vncProfilesKeepLegacyRdpWalletKeysAndDoNotUseRdpOptions() {
        auto p=profile(); auto old=p.json(); old.remove("protocol"); old.remove("vncSecurity");
        const auto legacy=Profile::fromJson(old); QCOMPARE(legacy.protocol,QString("rdp")); QCOMPARE(legacy.port,3389);
        const auto identity=QJsonArray{p.id,p.host.toLower(),p.port,p.username,p.domain,p.gateway.toLower()};
        QCOMPARE(legacy.credentialKey(),QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(identity).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex()));
        p.protocol="vnc";p.port=5901;p.vncViewOnly=true;p.vncSecurity="legacy";p.sharedFolder="/missing/rdp/folder";
        QVERIFY(p.validate().isEmpty()); QTemporaryDir temp;ProfileStore store(temp.filePath("connections.json"));QString error;
        QVERIFY(store.save(p,&error));QCOMPARE(store.load().at(0).json(),p.json());
        p.host="-SecurityTypes=None";QVERIFY(!p.validate().isEmpty());
    }
    void vncLaunchUsesLiteralArgumentsAndPrivateEnvironment() {
        auto p=profile();p.protocol="vnc";p.port=5901;p.host="::1";p.vncViewOnly=true;p.autoAcceptCertificate=true;
        auto args=vncArguments(p);QCOMPARE(args.last(),QString("[::1]::5901"));
        QVERIFY(args.contains("-ViewOnly=1"));QVERIFY(args.contains("-SendClipboard=0"));QVERIFY(args.contains("-RemoteResize=0"));
        const auto security=args.filter("-SecurityTypes=").at(0);QVERIFY(!security.contains(",VncAuth"));QVERIFY(!security.endsWith(",None"));
        p.vncSecurity="legacy";QVERIFY(vncArguments(p).filter("-SecurityTypes=").at(0).contains(",VncAuth,None"));
        const QString secret="private long password ' $(literal)";const auto env=vncEnvironment(p,secret);
        QCOMPARE(env.value("VNC_PASSWORD"),secret);QCOMPARE(env.value("VNC_USERNAME"),p.username);
        QVERIFY(!args.join(' ').contains(secret));QVERIFY(!p.json().contains("password"));
        QVERIFY(!vncEnvironment(p,{}).contains("VNC_PASSWORD"));
        if(qEnvironmentVariableIsSet("FUSION_VNC_TEST_PORT")) {
            p.host="127.0.0.1";p.port=qEnvironmentVariableIntValue("FUSION_VNC_TEST_PORT");p.vncSecurity="encrypted";p.vncViewOnly=false;p.dynamicResolution=false;
            QWidget owner;openVncSession(qEnvironmentVariable("FUSION_VNC_TEST_ROOT"),p,"fixture8",&owner);
            QPointer<QProcess> viewer=qApp->findChild<QProcess *>("fusionVncClient");QVERIFY(viewer);
            QTRY_COMPARE(viewer->state(),QProcess::Running);
            const auto cleanup=qScopeGuard([&]{if(viewer){viewer->kill();viewer->waitForFinished(1000);}});
            const QDir sync(qEnvironmentVariable("FUSION_VNC_TEST_SYNC"));
            QFile started(sync.filePath("started"));QVERIFY(started.open(QIODevice::WriteOnly));started.close();
            QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(sync.filePath("verified")),15000);
            QVERIFY(viewer && viewer->state()==QProcess::Running);
        }
    }
    void outgoingProtocolDefaultsToRdpAndSavesVncWithoutChangingOtherPcs() {
        QTemporaryDir temp;auto old=profile();old.rememberPassword=false;ProfileStore store(temp.filePath("control_panel/state/rdp/connections.json"));QString error;QVERIFY(store.save(old,&error));
        QFile helper(temp.filePath("secret-tool"));QVERIFY(helper.open(QIODevice::WriteOnly));helper.write("#!/bin/sh\nexit 0\n");helper.close();QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto path=qgetenv("PATH");const auto restore=qScopeGuard([&]{qputenv("PATH",path);});qputenv("PATH",temp.path().toUtf8()+":"+path);
        Profile opened;QString openedSecret;Page page(temp.path(),nullptr,[&](const Profile &p,const QString &s){opened=p;openedSecret=s;});page.resize(1220,900);page.show();
        auto *protocol=page.findChild<QComboBox *>("rdpProtocol");auto *port=page.findChild<QSpinBox *>("rdpPort");auto *password=page.findChild<QLineEdit *>("rdpPassword");
        QCOMPARE(page.draft().protocol,QString("rdp"));QCOMPARE(port->value(),3389);
        password->setText("rdp-secret-must-not-follow");protocol->setCurrentIndex(1);QCOMPARE(port->value(),5900);QVERIFY(password->text().isEmpty());
        QVERIFY(page.findChild<QGroupBox *>("vncOptions")->isVisible());QVERIFY(!page.findChild<QLineEdit *>("rdpDomain")->isVisible());QVERIFY(!page.findChild<QCheckBox *>("rdpShareFolder")->isVisible());
        port->setValue(5995);protocol->setCurrentIndex(0);QCOMPARE(port->value(),5995);protocol->setCurrentIndex(1);QCOMPARE(port->value(),5995);
        page.findChild<QLineEdit *>("rdpName")->setText("Linux VNC");page.findChild<QLineEdit *>("rdpHost")->setText("vnc.example.test");password->setText("vnc-test-secret-1234");
        page.findChild<QPushButton *>("rdpConnect")->click();QTRY_COMPARE(opened.protocol,QString("vnc"));QCOMPARE(openedSecret,QString("vnc-test-secret-1234"));QCOMPARE(opened.port,5995);
        const auto saved=store.load();QCOMPARE(saved.size(),2);QCOMPARE(saved[0].json(),old.json());QCOMPARE(saved[1].protocol,QString("vnc"));
        if(qEnvironmentVariableIsSet("RDP_TEST_SCREENSHOTS"))QVERIFY(page.grab().save(qEnvironmentVariable("RDP_TEST_SCREENSHOTS")+"/vnc-outgoing.png"));
        page.findChild<QPushButton *>("rdpNew")->click();QCOMPARE(page.draft().protocol,QString("rdp"));QCOMPARE(port->value(),3389);
    }
    void connectionValidationAndLiteralSharedPaths() {
        auto p=profile(); QVERIFY(p.validate().isEmpty()); p.host="rdp://bad/path"; QVERIFY(!p.validate().isEmpty());
        p.host="[::1]"; QVERIFY(p.validate().isEmpty()); p.port=0; QVERIFY(!p.validate().isEmpty());
        p.port=3389; p.sharedFolder="/path/that/does/not/exist"; QVERIFY(!p.validate().isEmpty());
        p.shareFolder=false; QVERIFY(p.validate().isEmpty());
    }
    void nativeSettingsEnableRequestedDefaultsAndKeepSecretsOutOfArguments() {
        std::unique_ptr<rdpSettings,decltype(&freerdp_settings_free)> settings(freerdp_settings_new(0),freerdp_settings_free);
        QVERIFY(settings); auto p=profile(); p.username="WORK\\tester";
        QTemporaryDir temp; p.sharedFolder=temp.path()+"/a, b ' $(literal)"; QVERIFY(QDir().mkpath(p.sharedFolder));
        QVERIFY(configure(settings.get(),p,"test-password",QSize(1365,768)));
        QCOMPARE(QString::fromUtf8(freerdp_settings_get_string(settings.get(),FreeRDP_Username)),QString("tester"));
        QCOMPARE(QString::fromUtf8(freerdp_settings_get_string(settings.get(),FreeRDP_Domain)),QString("WORK"));
        QCOMPARE(QString::fromUtf8(freerdp_settings_get_string(settings.get(),FreeRDP_Password)),QString("test-password"));
        QCOMPARE(freerdp_settings_get_uint32(settings.get(),FreeRDP_DesktopWidth),UINT32(1364));
        for (const auto flag : {FreeRDP_NlaSecurity,FreeRDP_TlsSecurity,FreeRDP_Authentication,FreeRDP_IgnoreCertificate,
             FreeRDP_RedirectClipboard,FreeRDP_AudioPlayback,FreeRDP_AudioCapture,FreeRDP_RedirectPrinters,
             FreeRDP_SupportGraphicsPipeline,FreeRDP_SupportDisplayControl,FreeRDP_AutoReconnectionEnabled,
             FreeRDP_SynchronousDynamicChannels})
            QVERIFY(freerdp_settings_get_bool(settings.get(),flag));
        auto *drive=reinterpret_cast<RDPDR_DRIVE *>(freerdp_device_collection_find(settings.get(),"Home")); QVERIFY(drive);
        QCOMPARE(QString::fromUtf8(drive->Path),p.sharedFolder);
        QVERIFY(!freerdp_settings_get_bool(settings.get(),FreeRDP_RedirectDrives));
    }
    void optionsCanDisableSharingAndRequireTrustedCertificates() {
        std::unique_ptr<rdpSettings,decltype(&freerdp_settings_free)> settings(freerdp_settings_new(0),freerdp_settings_free);
        auto p=profile(); p.shareFolder=p.clipboard=p.sound=p.microphone=p.printers=p.autoAcceptCertificate=p.dynamicResolution=false;
        QVERIFY(configure(settings.get(),p,"",QSize(1920,1080)));
        for (const auto flag : {FreeRDP_IgnoreCertificate,FreeRDP_RedirectClipboard,FreeRDP_AudioPlayback,FreeRDP_AudioCapture,
                              FreeRDP_RedirectPrinters,FreeRDP_SupportDisplayControl,FreeRDP_DeviceRedirection})
            QVERIFY(!freerdp_settings_get_bool(settings.get(),flag));
        QVERIFY(!freerdp_device_collection_find(settings.get(),"Home"));
        QVERIFY(freerdp_settings_get_bool(settings.get(),FreeRDP_NlaSecurity));
    }
    void keyboardMappingPreservesPhysicalAndExtendedKeys() {
        QCOMPARE(scanCode(38,Qt::Key_A),quint32(0x1e)); QCOMPARE(scanCode(9,Qt::Key_Escape),quint32(1));
        QCOMPARE(scanCode(36,Qt::Key_Return),quint32(0x1c));
        QVERIFY(scanCode(105,Qt::Key_Control) != scanCode(37,Qt::Key_Control));
        QCOMPARE(scanCode(0,Qt::Key_A),quint32(0x1e));
        QVERIFY(scanCode(0,Qt::Key_Delete) & 0x100);
    }
    void displaySizeAndColorsMatchQt() {
        QCOMPARE(desktopSize({1,1}),QSize(200,200)); QCOMPARE(desktopSize({99999,99999}),QSize(8192,8192));
        BYTE pixel[4]{}; QVERIFY(FreeRDPWriteColor(pixel,PIXEL_FORMAT_BGRX32,FreeRDPGetColor(PIXEL_FORMAT_BGRX32,220,30,70,255)));
        QImage frame(pixel,1,1,4,QImage::Format_RGB32); QCOMPARE(frame.pixelColor(0,0),QColor(220,30,70));
    }
    void clipboardTextUsesUnicodeAndWindowsNewlines() {
        ClipPeer peer; peer.bridge.localChanged(QString::fromUtf8("Olá\n世界"),{}); QVERIFY(peer.announced.contains(CF_UNICODETEXT));
        peer.request(CF_UNICODETEXT); QCOMPARE(peer.responseFlags,quint16(CB_RESPONSE_OK));
        QSignalSpy copied(&peer.bridge,&ClipboardBridge::received); peer.offer(CF_UNICODETEXT); peer.reply(peer.response);
        QCOMPARE(copied.size(),1); QCOMPARE(copied[0][0].toString(),QString::fromUtf8("Olá\n世界"));
        peer.request(987654); QCOMPARE(peer.responseFlags,quint16(CB_RESPONSE_FAIL));
    }
    void clipboardImagesRoundTripInWindowsBitmapFormat() {
        const auto png=pngImage(); const auto dib=imageDib(png); QVERIFY(!dib.isEmpty());
        QCOMPARE(clipboardImage(dib,true),clipboardImage(png));
        ClipPeer peer; peer.bridge.localChanged({},png); QVERIFY(peer.announced.contains(CF_DIB));
        peer.request(CF_DIB); QCOMPARE(peer.response,dib);
        QSignalSpy copied(&peer.bridge,&ClipboardBridge::received); peer.offer(CF_DIB); peer.reply(dib);
        QCOMPARE(copied.size(),1); QCOMPARE(clipboardImage(copied[0][1].toByteArray()),clipboardImage(png));
        QVERIFY(clipboardImage(QByteArray(40, char(0xff)),true).isNull());
    }
    void clipboardDiscardsStaleRepliesAndSerializesRequests() {
        ClipPeer peer; peer.bridge.localChanged("old",{}); peer.request(CF_UNICODETEXT); const auto text=peer.response;
        QSignalSpy copied(&peer.bridge,&ClipboardBridge::received);
        peer.offer(CF_UNICODETEXT); peer.offer(0xc020,"PNG"); QCOMPARE(peer.requests.size(),1);
        peer.reply(text); QCOMPARE(copied.size(),0); QCOMPARE(peer.requests.size(),2); QCOMPARE(peer.requests.last(),quint32(0xc020));
        peer.reply(pngImage()); QCOMPARE(copied.size(),1);
        peer.offer(CF_UNICODETEXT); peer.bridge.localChanged("new local copy",{}); peer.reply(text); QCOMPARE(copied.size(),1);
    }
    void clipboardHandlesChannelRequestsDuringLocalCopies() {
        ClipPeer peer; peer.bridge.localChanged("copy 0",{}); std::atomic_bool valid{true};
        std::thread channel([&] {
            for (int i=0; i<1000; ++i) {
                peer.request(CF_UNICODETEXT);
                if (peer.responseFlags != CB_RESPONSE_OK || peer.response.size()<4 || peer.response.size()%2 ||
                    !peer.response.endsWith(QByteArray(2,0))) valid=false;
            }
        });
        for (int i=0; i<1000; ++i) peer.bridge.localChanged("copy "+QString::number(i),{});
        channel.join(); QVERIFY(valid.load());
    }
    void walletUsesStandardInputNotCommandLineOrProfileFiles() {
        QTemporaryDir temp; const auto script=temp.path()+"/wallet";
        QFile helper(script); QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/usr/bin/python3\nimport sys,json,pathlib\np=pathlib.Path(__file__).parent\n(p/'argv.json').write_text(json.dumps(sys.argv[1:]))\nif sys.argv[1]=='store': (p/'stdin').write_bytes(sys.stdin.buffer.read())\nelif sys.argv[1]=='lookup': print('fixture-secret')\n"); helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        CredentialJob job(nullptr,script); QSignalSpy done(&job,&CredentialJob::completed); auto p=profile();
        job.start(CredentialJob::Store,p,"fixture-secret"); QTRY_COMPARE(done.size(),1); QVERIFY(done[0][0].toBool());
        QFile args(temp.path()+"/argv.json"); QVERIFY(args.open(QIODevice::ReadOnly)); QVERIFY(!args.readAll().contains("fixture-secret"));
        QFile input(temp.path()+"/stdin"); QVERIFY(input.open(QIODevice::ReadOnly)); QCOMPARE(input.readAll(),QByteArray("fixture-secret"));
        CredentialJob lookup(nullptr,script); QSignalSpy found(&lookup,&CredentialJob::completed); lookup.start(CredentialJob::Lookup,p);
        QTRY_COMPARE(found.size(),1); QCOMPARE(found[0][1].toString(),QString("fixture-secret"));
    }
    void walletFailureNeverReportsItsOutputAsAnError() {
        QTemporaryDir temp; const auto script=temp.path()+"/wallet"; QFile helper(script); QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/bin/sh\nprintf 'private-secret'\nprintf 'private-secret' >&2\nexit 1\n"); helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        CredentialJob job(nullptr,script); QSignalSpy done(&job,&CredentialJob::completed); job.start(CredentialJob::Lookup,profile());
        QTRY_COMPARE(done.size(),1); QVERIFY(!done[0][0].toBool()); QVERIFY(done[0][1].toString().isEmpty()); QVERIFY(!done[0][2].toString().contains("private-secret"));
    }
    void pageDefaultsAndValidationAreVisible() {
        QTemporaryDir temp; int opened=0; Page page(temp.path(),nullptr,[&](const Profile &,const QString &) { ++opened; });
        page.resize(1220,930); page.show(); QTest::qWait(30);
        const auto p=page.draft(); QCOMPARE(p.sharedFolder,QDir::homePath()); QVERIFY(p.autoAcceptCertificate && p.shareFolder && p.clipboard && p.sound && p.microphone);
        page.findChild<QPushButton *>("rdpConnect")->click(); QCOMPARE(opened,0);
        QVERIFY(!page.findChild<QLabel *>("rdpStatus")->text().isEmpty());
        if (qEnvironmentVariableIsSet("RDP_TEST_SCREENSHOTS")) {
            auto *name=page.findChild<QLineEdit *>("rdpName"); name->setText("Office PC");
            page.findChild<QLineEdit *>("rdpHost")->setText("192.168.1.20"); page.findChild<QLineEdit *>("rdpUsername")->setText("xetal");
            page.findChild<QLabel *>("rdpStatus")->clear();
            QVERIFY(page.grab().save(qEnvironmentVariable("RDP_TEST_SCREENSHOTS")+"/rdp-page.png"));
        }
    }
    void hostingTabsPreserveOutgoingDraftAndSavedPcs() {
        QTemporaryDir temp; QVERIFY(hostingFixture(temp.path()));
        auto pc = profile(); QString error;
        ProfileStore store(temp.path()+"/control_panel/state/rdp/connections.json"); QVERIFY(store.save(pc, &error));
        Page page(temp.path(), nullptr, [](const Profile &, const QString &) {});
        page.resize(1220,930); page.show(); QTest::qWait(30);
        auto *tabs = page.findChild<QTabWidget *>("rdpModes"); QVERIFY(tabs); QCOMPARE(tabs->count(), 2); QCOMPARE(tabs->currentIndex(), 0);
        QVERIFY(!QFile::exists(temp.path()+"/requests")); // Reading saved PCs never invokes the hosting helper.
        page.findChild<QLineEdit *>("rdpHost")->setText("draft.example.test");
        page.findChild<QLineEdit *>("rdpUsername")->setText("my-draft-login");
        page.showHosting();
        QTRY_VERIFY(page.findChild<QPushButton *>("rdpHostStart")->isEnabled());
        QCOMPARE(page.findChild<QLabel *>("rdpHostState")->text(), QString("Sharing is off"));
        QVERIFY(!QFile::exists(temp.path()+"/running")); QVERIFY(!QFile::exists(temp.path()+"/settings"));
        if (qEnvironmentVariableIsSet("RDP_TEST_SCREENSHOTS"))
            QVERIFY(page.grab().save(qEnvironmentVariable("RDP_TEST_SCREENSHOTS")+"/rdp-hosting-page.png"));
        tabs->setCurrentIndex(0);
        QCOMPARE(page.draft().host, QString("draft.example.test")); QCOMPARE(page.draft().username, QString("my-draft-login"));
        QCOMPARE(page.findChild<QListWidget *>("rdpConnections")->count(), 1);
        QCOMPARE(store.load(&error).at(0).host, pc.host);
        QVERIFY(!page.findChild<QTimer *>("rdpHostPoll")->isActive());
    }
    void hostingRefreshPreservesEditsAndCredentialsTravelOnStdin() {
        QTemporaryDir temp; QVERIFY(hostingFixture(temp.path()));
        HostingPage page(temp.path()); page.resize(1100,760); page.show();
        auto *save = page.findChild<QPushButton *>("rdpHostSave"); QTRY_VERIFY(save->isEnabled());
        auto *timer = page.findChild<QTimer *>("rdpHostPoll"); timer->stop();
        auto *protocol = page.findChild<QComboBox *>("rdpHostProtocol");
        auto *port = page.findChild<QSpinBox *>("rdpHostPort");
        auto *control = page.findChild<QCheckBox *>("rdpHostControl");
        auto *secret = page.findChild<QLineEdit *>("rdpHostPassword");
        auto *username = page.findChild<QLineEdit *>("rdpHostUsername");
        auto *refresh = page.findChild<QPushButton *>("rdpHostRefresh");
        QCOMPARE(protocol->currentData().toString(), QString("vnc")); QVERIFY(!control->isChecked());
        protocol->setCurrentIndex(protocol->findData("rdp")); QCOMPARE(port->value(),3389); QVERIFY(control->isChecked()); QVERIFY(!control->isEnabled());
        port->setValue(3395); username->setText("new-sharing-user"); secret->setText("fixture-private-password");
        refresh->click(); QTRY_VERIFY(save->isEnabled());
        QCOMPARE(port->value(),3395); QCOMPARE(username->text(),QString("new-sharing-user")); QCOMPARE(secret->text(),QString("fixture-private-password"));
        QFile slow(temp.path()+"/slow"); QVERIFY(slow.open(QIODevice::WriteOnly)); slow.close();
        QVERIFY(QMetaObject::invokeMethod(timer,"timeout"));
        QVERIFY(username->isEnabled()); QVERIFY(secret->isEnabled()); // Polling must not interrupt typing.
        QVERIFY(save->isEnabled()); QVERIFY(refresh->isEnabled()); QVERIFY(page.findChild<QPushButton *>("rdpHostStart")->isEnabled());
        QTRY_VERIFY(save->isEnabled());
        auto *start = page.findChild<QPushButton *>("rdpHostStart"); start->click();
        auto *stop = page.findChild<QPushButton *>("rdpHostStop"); QTRY_VERIFY(stop->isEnabled());
        QVERIFY(secret->text().isEmpty()); QVERIFY(!start->isEnabled());
        QVERIFY(page.findChild<QLabel *>("rdpHostState")->text().contains("Listening · waiting for a connection"));
        QFile requests(temp.path()+"/requests"); QVERIFY(requests.open(QIODevice::ReadOnly));
        bool sawStart = false;
        for (const auto &line : requests.readAll().split('\n')) {
            if (line.isEmpty()) continue;
            const auto request = QJsonDocument::fromJson(line).object();
            QVERIFY(!QJsonDocument(request["argv"].toArray()).toJson().contains("fixture-private-password"));
            if (request["action"].toString() == "start") {
                sawStart = true; QCOMPARE(request["request"].toObject()["password"].toString(),QString("fixture-private-password"));
                QCOMPARE(request["request"].toObject()["values"].toObject()["port"].toInt(),3395);
            }
        }
        QVERIFY(sawStart); stop->click(); QTRY_VERIFY(start->isEnabled()); QVERIFY(!stop->isEnabled());
        QCOMPARE(page.findChild<QLabel *>("rdpHostState")->text(),QString("Sharing is off"));
        page.hide(); QVERIFY(!timer->isActive());
    }
    void hostingPasswordRequirementAndFailuresStayVisibleAcrossPolling() {
        QTemporaryDir temp;QVERIFY(hostingFixture(temp.path()));
        QFile missing(temp.filePath("missing-password"));QVERIFY(missing.open(QIODevice::WriteOnly));missing.close();
        HostingPage page(temp.path());page.show();
        auto *save=page.findChild<QPushButton *>("rdpHostSave");QTRY_VERIFY(save->isEnabled());
        auto *timer=page.findChild<QTimer *>("rdpHostPoll");timer->stop();
        auto *process=page.findChild<QProcess *>("rdpHostProcess");auto *start=page.findChild<QPushButton *>("rdpHostStart");auto *password=page.findChild<QLineEdit *>("rdpHostPassword");
        QVERIFY(!start->isEnabled());QVERIFY(page.findChild<QLabel *>("rdpHostMessage")->text().contains("password"));
        password->setText("short");QVERIFY(!start->isEnabled());password->setText("test-sharing-secret");QVERIFY(start->isEnabled());
        QFile failure(temp.filePath("fail-start"));QVERIFY(failure.open(QIODevice::WriteOnly));failure.close();start->click();
        auto *message=page.findChild<QLabel *>("rdpHostMessage");QTRY_COMPARE(message->text(),QString("Fixture listener could not bind"));
        QVERIFY(!page.findChild<QPushButton *>("rdpHostStop")->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(timer,"timeout"));QVERIFY(start->isEnabled());QVERIFY(save->isEnabled());
        QTRY_COMPARE(process->state(),QProcess::NotRunning);QCOMPARE(message->text(),QString("Fixture listener could not bind"));
        QVERIFY(QFile::remove(failure.fileName()));start->click();QTRY_VERIFY(page.findChild<QPushButton *>("rdpHostStop")->isEnabled());
        auto *state=page.findChild<QLabel *>("rdpHostState");QVERIFY(state->text().contains("Listening"));
        QFile clients(temp.filePath("clients"));QVERIFY(clients.open(QIODevice::WriteOnly));clients.write("1");clients.close();
        QVERIFY(QMetaObject::invokeMethod(timer,"timeout"));QVERIFY(page.findChild<QPushButton *>("rdpHostStop")->isEnabled());QTRY_VERIFY(state->text().contains("1 remote connection"));
        // Editing a draft does not change the connection address of the active server.
        const auto active=page.findChild<QLabel *>("rdpHostConnection")->text();page.findChild<QSpinBox *>("rdpHostPort")->setValue(5998);QCOMPARE(page.findChild<QLabel *>("rdpHostConnection")->text(),active);
        QFile slow(temp.filePath("slow"));QVERIFY(slow.open(QIODevice::WriteOnly));slow.close();
        QVERIFY(QMetaObject::invokeMethod(timer,"timeout"));page.findChild<QPushButton *>("rdpHostStop")->click();
        QTRY_VERIFY(!QFile::exists(temp.filePath("running")));QTRY_VERIFY(start->isEnabled());QVERIFY(!page.findChild<QPushButton *>("rdpHostStop")->isEnabled());
    }
    void hostingMissingHelperKeepsControlsSafeAndReportsAnError() {
        QTemporaryDir temp; HostingPage page(temp.path()); page.show();
        auto *message = page.findChild<QLabel *>("rdpHostMessage"); QTRY_VERIFY(!message->text().isEmpty());
        QVERIFY(!page.findChild<QPushButton *>("rdpHostStart")->isEnabled());
        QVERIFY(page.findChild<QPushButton *>("rdpHostRefresh")->isEnabled());
    }
    void savedPasswordsCannotFollowAnEditedPcOrOverwriteTyping() {
        QTemporaryDir temp; auto p = profile(); QString error;
        ProfileStore store(temp.path()+"/control_panel/state/rdp/connections.json");
        QVERIFY2(store.save(p,&error),qPrintable(error));
        QFile helper(temp.path()+"/secret-tool"); QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("#!/usr/bin/python3\nimport sys,time\nif sys.argv[1]=='lookup':\n time.sleep(.15)\n print('saved-fixture-password')\n"); helper.close();
        QVERIFY(helper.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        const auto path = qgetenv("PATH"); const auto restore = qScopeGuard([&] { qputenv("PATH",path); });
        qputenv("PATH",temp.path().toUtf8()+":"+path);
        QString openedHost, openedPassword;
        Page page(temp.path(),nullptr,[&](const Profile &pc,const QString &secret) { openedHost=pc.host; openedPassword=secret; });
        auto *list=page.findChild<QListWidget *>("rdpConnections");
        auto *password=page.findChild<QLineEdit *>("rdpPassword");
        auto *host=page.findChild<QLineEdit *>("rdpHost");
        auto *connect=page.findChild<QPushButton *>("rdpConnect");
        QCOMPARE(list->count(),1); list->setCurrentRow(0); QVERIFY(!connect->isEnabled());
        QTRY_COMPARE(password->text(),QString("saved-fixture-password")); QVERIFY(connect->isEnabled());
        host->setText("different.example.test"); QVERIFY(password->text().isEmpty());
        QTest::keyClicks(password,"new-password"); connect->click();
        QTRY_COMPARE(openedHost,QString("different.example.test")); QCOMPARE(openedPassword,QString("new-password"));
        // Reopen a saved connection; a slow wallet reply must respect typing.
        page.findChild<QPushButton *>("rdpNew")->click(); list->setCurrentRow(0);
        QVERIFY(!connect->isEnabled()); QTest::keyClicks(password,"typed-during-lookup"); QVERIFY(connect->isEnabled());
        QTest::qWait(250); QCOMPARE(password->text(),QString("typed-during-lookup"));
        Page other(temp.path(),nullptr,[](const Profile &,const QString &) {});
        other.findChild<QListWidget *>("rdpConnections")->setCurrentRow(0);
        other.findChild<QLineEdit *>("rdpHost")->setText("third.example.test");
        QTest::qWait(250); QVERIFY(other.findChild<QLineEdit *>("rdpPassword")->text().isEmpty());
    }
    void sessionToolbarHidesAndReturnsAtTheBrim() {
        auto p=profile(); p.name=QString(80,'W'); SessionWindow window(p,"",nullptr,false); window.setAttribute(Qt::WA_DeleteOnClose,false);
        window.resize(800,600); window.showSession(); QTest::qWait(40);
        auto *bar=window.findChild<QFrame *>("rdpSessionBar"); auto *view=window.findChild<DesktopView *>(); QVERIFY(bar); QVERIFY(view);
        QVERIFY(window.rect().contains(bar->geometry()));
        QVERIFY(QMetaObject::invokeMethod(&window,"connectionReady")); QTest::mouseMove(view,QPoint(100,250));
        QTRY_VERIFY_WITH_TIMEOUT(!bar->isVisible(),2400);
        QTest::mouseMove(view,QPoint(view->width()/2,0)); QTRY_VERIFY(bar->isVisible());
        window.findChild<QPushButton *>("rdpFullscreen")->click(); QTRY_VERIFY(window.isFullScreen());
        window.findChild<QPushButton *>("rdpWindowMode")->click(); QTRY_VERIFY(!window.isFullScreen());
        window.close();
    }
    void viewCoordinatesFollowScaledDesktop() {
        DesktopView view; view.resize(1000,1000); QImage image(1920,1080,QImage::Format_RGB32); image.fill(Qt::black); view.setFrame(image);
        QCOMPARE(view.imageRect().width(),1000); QCOMPARE(view.remotePoint(QRectF(view.imageRect()).center()),QPoint(960,540));
        QCOMPARE(view.remotePoint(QPointF(-100,-100)),QPoint(0,0)); QCOMPARE(view.remotePoint(QPointF(2000,2000)),QPoint(1919,1079));
    }
    void cancelledBeforeStartDoesNotAttemptAConnection() {
        Engine engine(profile(),"fixture-secret",QSize(1280,720)); QSignalSpy ended(&engine,&Engine::ended);
        engine.stop(); engine.start(); QTRY_COMPARE(ended.size(),1); QVERIFY(engine.wait(1000)); QVERIFY(ended[0][0].toString().isEmpty());
    }
};
QTEST_MAIN(RdpTests)
#include "tests.moc"
