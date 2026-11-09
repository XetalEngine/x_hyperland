#include "native_transfer.h"
#include "core.h"
#include <KIO/Global>
#include <KIO/FileUndoManager>
#include <QCoreApplication>
#include <QDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QStandardPaths>
#include <QUuid>
#include <sys/stat.h>

Fusion::NativeTransfer::NativeTransfer(QJsonObject data) : request(std::move(data)) {
  setCapabilities(Killable | Suspendable);
  connect(&process, &QProcess::readyReadStandardOutput, this, &NativeTransfer::receive);
  connect(&process, &QProcess::started, this, [this] {
    command(request);
    if (paused) command({{"command", "pause"}});
  });
  connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) complete(KIO::ERR_WORKER_DEFINED, process.errorString());
  });
  connect(&process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
    receive();
    if (outcome.value("cancelled").toBool()) complete(KIO::ERR_USER_CANCELED, {});
    else if (status == QProcess::NormalExit && !code && outcome.value("ok").toBool()) complete(0, {});
    else complete(KIO::ERR_WORKER_DEFINED, outcome.value("error").toString(
        "The transfer worker stopped before reporting completion. Original files that were not successfully moved remain in place.\n" +
        QString::fromUtf8(process.readAllStandardError())));
  });
  connect(&authority, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) command({{"command", "auth_failed"}, {"token", authorizationToken}, {"error", authority.errorString()}});
  });
  connect(&authority, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
    if (!finished && process.state() == QProcess::Running && (code || status != QProcess::NormalExit))
      command({{"command", "auth_failed"}, {"token", authorizationToken}, {"error", "Administrator authorization was cancelled or file access failed.\n" +
               QString::fromUtf8(authority.readAllStandardError())}});
  });
}

Fusion::NativeTransfer::~NativeTransfer() {
  if (process.state() != QProcess::NotRunning) {
    command({{"command", "cancel"}}); process.closeWriteChannel();
    if (!process.waitForFinished(1000)) { process.kill(); process.waitForFinished(1000); }
  }
  // The authenticated helper exits on socket EOF, even when Files crashes.
  if (authority.state() != QProcess::NotRunning) authority.waitForFinished(1000);
}

void Fusion::NativeTransfer::start() {
  if (started || finished) return;
  started = true;
  const auto directory = QStandardPaths::writableLocation(QStandardPaths::StateLocation) + "/fusion-files/transfers";
  if (!QDir().mkpath(directory)) { complete(KIO::ERR_CANNOT_MKDIR, directory); return; }
  ::chmod(QFile::encodeName(directory), 0700);
  journalPath = directory + "/" + QUuid::createUuid().toString(QUuid::WithoutBraces) + ".sqlite";
  request["journal"] = journalPath;
  process.start("/usr/bin/python3", {"-I", Fusion::root() + "/file_manager/transfer_worker.py"});
}

void Fusion::NativeTransfer::command(const QJsonObject &message) {
  if (process.state() != QProcess::NotRunning)
    process.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
}
void Fusion::NativeTransfer::answer(const QString &choice) { command({{"command", "answer"}, {"choice", choice}}); }
void Fusion::NativeTransfer::resolve(const QVariantMap &decision) {
  auto message = QJsonObject::fromVariantMap(decision); message["command"] = "issue_answer"; command(message);
}
bool Fusion::NativeTransfer::doKill() {
  if (!started) { finished = true; return true; }
  command({{"command", "cancel"}});
  return false; // Acknowledge completion only after the worker has stopped writing.
}
bool Fusion::NativeTransfer::doSuspend() { paused = true; command({{"command", "pause"}}); return !finished; }
bool Fusion::NativeTransfer::doResume() { paused = false; command({{"command", "resume"}}); return !finished; }

void Fusion::NativeTransfer::receive() {
  buffer += process.readAllStandardOutput();
  qsizetype end;
  while ((end = buffer.indexOf('\n')) >= 0) {
    const auto line = buffer.left(end); buffer.remove(0, end+1);
    const auto message = QJsonDocument::fromJson(line).object();
    const auto event = message.value("event").toString();
    if (event == "progress") {
      // Qt JSON stores exact 64-bit integers; QVariant conversion preserves
      // them for JobView rather than narrowing byte totals to 32 bits.
      setTotalAmount(Bytes, message.value("totalBytes").toInteger());
      setProcessedAmount(Bytes, message.value("processedBytes").toInteger());
      setTotalAmount(Files, message.value("totalFiles").toInteger());
      setProcessedAmount(Files, message.value("processedFiles").toInteger());
      setPercent(message.value("percent").toInt());
      emitSpeed(message.value("speed").toInteger());
      emit progress(message.toVariantMap());
    } else if (event == "issue") emit issue(message.toVariantMap());
    else if (event == "question") {
      emit question(QUrl::fromLocalFile(message.value("source").toString()),
                    QUrl::fromLocalFile(message.value("destination").toString()), message.value("replace_allowed").toBool());
    } else if (event == "authenticate") authenticate(message);
    else if (event == "target") emit destinationReady(QUrl::fromLocalFile(message.value("destination").toString()));
    else if (event == "moved") emit moved(QUrl::fromLocalFile(message.value("source").toString()),
                                          QUrl::fromLocalFile(message.value("destination").toString()));
    else if (event == "result") {
      outcome = message;
      QStringList warnings;
      for (const auto &value : message.value("warnings").toArray()) warnings << value.toString();
      if (!warnings.isEmpty()) emit progress({{"warningMessage", warnings.join('\n')}});
    }
  }
}

void Fusion::NativeTransfer::authenticate(QJsonObject scope) {
  const auto token = scope.value("token").toString();
  if (authority.state() != QProcess::NotRunning) {
    command({{"command", "auth_failed"}, {"token", token}, {"error", "An administrator request is still open. Close that prompt, then retry."}}); return;
  }
  authorizationToken = token;
  const auto pkexec = QStandardPaths::findExecutable("pkexec");
  if (pkexec.isEmpty()) {
    command({{"command", "auth_failed"}, {"token", token}, {"error", "The PolicyKit authentication helper (pkexec) is unavailable."}}); return;
  }
  emit infoMessage(this, "Authorize access to protected items. Other files keep copying; authorization ends with this transfer.");
  if (!scope.value("background").toBool()) emit progress({{"phase", "Waiting for administrator authorization"}});
  authority.start(pkexec, {"/usr/bin/python3", "-I", Fusion::root() + "/file_manager/transfer_authority.py"});
  authority.write(QJsonDocument(scope).toJson(QJsonDocument::Compact));
  authority.closeWriteChannel();
}

void Fusion::NativeTransfer::complete(int code, const QString &message) {
  if (finished) return;
  finished = true; setError(code); setErrorText(message); emitResult();
}

Fusion::TransferHistory::TransferHistory() : QObject(QCoreApplication::instance()) {
  auto *kio = KIO::FileUndoManager::self();
  connect(kio, &KIO::FileUndoManager::undoAvailable, this, &TransferHistory::changed);
  connect(kio, &KIO::FileUndoManager::undoTextChanged, this, &TransferHistory::changed);
}
Fusion::TransferHistory *Fusion::TransferHistory::self() { static auto *history = new TransferHistory; return history; }
void Fusion::TransferHistory::record(const QString &journal, bool moving) {
  entries.append({KIO::FileUndoManager::self()->newCommandSerialNumber(), journal, moving}); emit changed();
}
QString Fusion::TransferHistory::pending() const {
  if (entries.isEmpty()) return {};
  auto *kio = KIO::FileUndoManager::self();
  return !kio->isUndoAvailable() || entries.last().serial > kio->currentCommandSerialNumber() ? entries.last().journal : QString();
}
bool Fusion::TransferHistory::available() const { return !entries.isEmpty() || KIO::FileUndoManager::self()->isUndoAvailable(); }
QString Fusion::TransferHistory::text() const { return pending().isEmpty() ? KIO::FileUndoManager::self()->undoText() : entries.last().moving ? "Undo Move" : "Undo Copy"; }
void Fusion::TransferHistory::consumed(const QString &journal) {
  for (qsizetype i = entries.size(); i > 0; --i)
    if (entries[i-1].journal == journal) { entries.removeAt(i-1); break; }
  emit changed();
}
