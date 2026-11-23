#include "vnc.h"
#include <QApplication>
#include <QFileInfo>
#include <QMessageBox>
#include <QProcess>
#include <QStandardPaths>

namespace FusionRdp {
QString vncExecutable(const QString &root) {
    for (const auto &name : {"vncviewer", "xtigervncviewer"}) {
        const auto path = QStandardPaths::findExecutable(name);
        if (!path.isEmpty()) return path;
    }
    const auto cached = root + "/control_panel/.build/tigervnc/usr/bin/vncviewer";
    return QFileInfo(cached).isExecutable() ? cached : QString();
}
QStringList vncArguments(const Profile &p) {
    auto host = p.host;
    if (host.contains(':') && !host.startsWith('[')) host = '[' + host + ']';
    QStringList args;
    auto flag = [&](const char *name, bool enabled) { args << QString("-%1=%2").arg(name).arg(enabled ? 1 : 0); };
    flag("FullScreen", p.fullscreen); flag("ViewOnly", p.vncViewOnly); flag("Shared", p.vncShared);
    flag("AcceptClipboard", p.clipboard); flag("SendClipboard", p.clipboard && !p.vncViewOnly);
    flag("SendPrimary", false); flag("SetPrimary", false);
    flag("RemoteResize", p.dynamicResolution && !p.vncViewOnly); flag("ReconnectOnError", p.reconnect);
    // Never apply RDP's certificate-acceptance preference to VNC. TigerVNC
    // asks before trusting an unknown/changed certificate and remembers trust.
    QString security = "X509Plain,X509Vnc,X509None,TLSPlain,TLSVnc,TLSNone,RA2_256,RA2";
    if (p.vncSecurity == "legacy") security += ",VncAuth,None";
    args << "-SecurityTypes=" + security << "-FullScreenMode=current" << "-AlertOnFatalError=1";
    args << host + "::" + QString::number(p.port);
    return args;
}
QProcessEnvironment vncEnvironment(const Profile &p, const QString &password) {
    auto env = QProcessEnvironment::systemEnvironment();
    env.remove("VNC_PASSWORD"); env.remove("VNC_USERNAME");
    // TigerVNC's supported credential interface avoids argv, temporary
    // password files, and truncating TLS passwords to classic VNC's 8 bytes.
    if (!password.isEmpty()) env.insert("VNC_PASSWORD", password);
    if (!p.username.isEmpty()) env.insert("VNC_USERNAME", p.username);
    return env;
}
void openVncSession(const QString &root, const Profile &p, const QString &password, QWidget *parent) {
    const auto program = vncExecutable(root);
    if (program.isEmpty()) {
        QMessageBox::information(parent, "VNC viewer", "Install TigerVNC to connect to VNC desktops (tigervnc on Arch/Fedora, tigervnc-viewer on Debian/Ubuntu). Your connection is saved.");
        return;
    }
    auto *process = new QProcess(qApp);
    process->setObjectName("fusionVncClient");
    auto env = vncEnvironment(p, password);
    if (program.startsWith(root + "/control_panel/.build/tigervnc/"))
        env.insert("LD_LIBRARY_PATH", root + "/control_panel/.build/tigervnc/usr/lib");
    process->setProcessEnvironment(env);
    process->setStandardOutputFile(QProcess::nullDevice()); process->setStandardErrorFile(QProcess::nullDevice());
    QObject::connect(process, &QProcess::started, process, [process] { process->setProcessEnvironment(QProcessEnvironment()); });
    QObject::connect(process, &QProcess::errorOccurred, parent, [parent](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) QMessageBox::warning(parent, "VNC viewer", "TigerVNC could not start. Check that the viewer and its libraries are installed.");
    });
    QObject::connect(process, &QProcess::errorOccurred, process, [process](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) process->deleteLater();
    });
    QObject::connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), process, &QObject::deleteLater);
    process->start(program, vncArguments(p)); process->closeWriteChannel();
}
}
