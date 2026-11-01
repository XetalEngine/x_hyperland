#include "removal.h"
#include "core.h"
#include <KIO/CopyJob>
#include <KIO/DeleteJob>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegateFactory>
#include <KIO/RestoreJob>
#include <KJobWidgets>
#include <QWidget>
#include <sys/stat.h>

Fusion::RemovalJob::RemovalJob(const QList<QUrl> &items, bool permanent, QWidget *window)
    : RemovalJob([&] { KFileItemList files; for (const auto &url : items) files << KFileItem(url); return files; }(), permanent ? "delete" : "trash", window) {}
Fusion::RemovalJob::RemovalJob(const KFileItemList &items, const QString &operation, QWidget *window)
    : operation(operation), window(window) {
  setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window));
  for (const auto &item : items) {
    const auto url = item.url(); urls << url;
    const auto path = item.localPath();
    if (path.isEmpty() || (!url.isLocalFile() && url.scheme() != "trash")) continue;
    struct stat info;
    if (::lstat(QFile::encodeName(path).constData(), &info)) continue;
    snapshots.append(QJsonObject{{"path", path}, {"url", url.toString()}, {"fromTrash", url.scheme() == "trash"},
      {"restoreTo", item.entry().stringValue(KIO::UDSEntry::UDS_EXTRA)}, {"dev", QString::number(info.st_dev)}, {"ino", QString::number(info.st_ino)}});
  }
  connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) complete(KIO::ERR_WORKER_DEFINED, process.errorString());
  });
  connect(&process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus exit) {
    const auto result = QJsonDocument::fromJson(process.readAllStandardOutput()).object();
    if (exit == QProcess::NormalExit && code == 0 && result.value("ok").toBool()) complete(0, {});
    else if ((code == 126 || code == 127) && result.isEmpty()) complete(KIO::ERR_USER_CANCELED, {});
    else complete(KIO::ERR_WORKER_DEFINED, result.value("error").toString("Administrator action failed or authentication was cancelled."));
  });
  QTimer::singleShot(0, this, [this] { start(); });
}
void Fusion::RemovalJob::start() {
  KIO::Job *job;
  if (operation == "delete") job = KIO::del(urls);
  else if (operation == "restore") job = KIO::restoreFromTrash(urls);
  else {
    auto *trash = KIO::trash(urls);
    KIO::FileUndoManager::self()->recordCopyJob(trash);
    job = trash;
  }
  job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window));
  KJobWidgets::setWindow(job, window);
  connect(job, &KJob::result, this, [this](KJob *result) {
    const int error = result->error();
    if (error == KIO::ERR_ACCESS_DENIED || error == KIO::ERR_WRITE_ACCESS_DENIED ||
        error == KIO::ERR_CANNOT_DELETE || error == KIO::ERR_CANNOT_RENAME ||
        error == KIO::ERR_CANNOT_ENTER_DIRECTORY)
      authenticate(error, result->errorString());
    else complete(error, result->errorString());
  });
}
void Fusion::RemovalJob::authenticate(int error, const QString &message) {
  if (snapshots.size() != urls.size()) { complete(error, message); return; }
  QJsonArray remaining;
  for (const auto &value : snapshots) {
    const auto item = value.toObject();
    struct stat info;
    if (!::lstat(QFile::encodeName(item.value("path").toString()).constData(), &info)) remaining.append(item);
  }
  if (remaining.isEmpty()) { complete(0, {}); return; }
  const auto pkexec = QStandardPaths::findExecutable("pkexec");
  if (pkexec.isEmpty()) { complete(error, message + "\nThe PolicyKit authentication helper (pkexec) is unavailable."); return; }
  emit infoMessage(this, operation == "delete" ? "Authenticate to delete the selected protected items." : operation == "restore" ? "Authenticate to restore the selected protected items." : "Authenticate to move the selected protected items to Trash.");
  process.start(pkexec, {"/usr/bin/python3", "-I", Fusion::root() + "/file_manager/privileged.py"});
  process.write(QJsonDocument(QJsonObject{{"operation", operation},
      {"dataHome", QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)}, {"items", remaining}}).toJson(QJsonDocument::Compact));
  process.closeWriteChannel();
}
void Fusion::RemovalJob::complete(int error, const QString &message) {
  if (finished) return;
  finished = true;
  QList<QUrl> removedUrls;
  for (const auto &url : urls) {
    struct stat info;
    QString path;
    for (const auto &snapshot : snapshots) if (QUrl(snapshot.toObject().value("url").toString()) == url) path = snapshot.toObject().value("path").toString();
    if (!path.isEmpty() && ::lstat(QFile::encodeName(path).constData(), &info) && errno == ENOENT) removedUrls << url;
    else if (path.isEmpty() && !error) removedUrls << url;
  }
  if (!removedUrls.isEmpty()) emit removed(removedUrls);
  setError(error); setErrorText(message);
  emitResult();
}
