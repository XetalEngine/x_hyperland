#include "credentials.h"
#include <QStandardPaths>

namespace FusionRdp {
CredentialJob::CredentialJob(QObject *parent, QString command)
    : QObject(parent), program(command.isEmpty() ? QStandardPaths::findExecutable("secret-tool") : std::move(command)) {
    deadline.setSingleShot(true); deadline.setInterval(30000);
    connect(&deadline, &QTimer::timeout, this, [this] {
        process.kill(); finish(false, {}, "The password wallet did not respond. Unlock it and try again.");
    });
    connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) finish(false, {}, "The system password wallet helper could not start.");
    });
    connect(&process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
        [this](int code, QProcess::ExitStatus status) {
            // Never put helper stdout/stderr into logs or error messages: lookup returns a secret.
            auto output = process.readAllStandardOutput();
            const auto diagnostic = process.readAllStandardError();
            const bool missing = operation != Store && code == 1 && diagnostic.trimmed().isEmpty();
            if (status != QProcess::NormalExit || (code != 0 && !missing)) {
                output.fill('\0'); finish(false, {}, "The password wallet is unavailable or locked. You can connect without saving the password."); return;
            }
            if (operation == Lookup && output.endsWith('\n')) output.chop(1);
            const auto secret = operation == Lookup ? QString::fromUtf8(output) : QString();
            output.fill('\0'); finish(true, secret, {});
        });
}
CredentialJob::~CredentialJob() {
    if (process.state() != QProcess::NotRunning) { process.kill(); process.waitForFinished(1000); }
}
void CredentialJob::finish(bool success, const QString &password, const QString &error) {
    if (done) return;
    done = true; deadline.stop(); emit completed(success, password, error);
}
void CredentialJob::start(Operation action, const Profile &profile, const QString &password) {
    operation = action;
    if (program.isEmpty()) { finish(false, {}, "Install the system password wallet helper (secret-tool) to remember passwords."); return; }
    QStringList args;
    if (action == Store) args << "store" << "--label=Hyper Fusion RDP — " + profile.name;
    else args << (action == Lookup ? "lookup" : "clear");
    args << "application" << "hyperfusion-rdp" << "connection" << profile.credentialKey();
    process.start(program, args);
    if (action == Store) {
        auto bytes = password.toUtf8(); process.write(bytes); bytes.fill('\0');
    }
    process.closeWriteChannel(); deadline.start();
}
}
