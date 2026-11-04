#include "desktop_actions.h"
#include "applications.h"
#include "core.h"
#include "removal.h"
#include "transfers.h"
#include <KApplicationTrader>
#include <KIO/MkdirJob>
#include <KIO/CopyJob>
#include <KIO/FileUndoManager>
#include <KIO/OpenUrlJob>
#include <KIO/JobUiDelegateFactory>
#include <KIO/RenameFileDialog>
#include <KIO/StatJob>
#include <KPropertiesDialog>
#include <QCryptographicHash>
#include <algorithm>
#include <memory>

DesktopActions::DesktopActions(QObject *parent) : QDBusAbstractAdaptor(parent) {}
QString DesktopActions::serviceName() {
  return "org.xetal.FusionFiles.Desktop.s" + QString::fromLatin1(QCryptographicHash::hash(
      qgetenv("HYPRLAND_INSTANCE_SIGNATURE"), QCryptographicHash::Sha256).toHex().left(24));
}
QList<QUrl> DesktopActions::urls(const QStringList &values) {
  QList<QUrl> result;
  if (values.isEmpty() || values.size() > 10000) return result;
  for (const auto &value : values) {
    const QUrl url(value, QUrl::StrictMode);
    if (!url.isValid() || url.scheme().isEmpty() || value.contains(QChar::Null) ||
        (url.isLocalFile() && !QDir::isAbsolutePath(url.toLocalFile()))) return {};
    if (!result.contains(url)) result << url;
  }
  return result;
}
void DesktopActions::error(const QString &message) {
  auto *dialog = new QMessageBox(QMessageBox::Warning, "Fusion Files", message, QMessageBox::Ok);
  dialog->setTextFormat(Qt::PlainText);
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->show();
}
void DesktopActions::track(KJob *job) {
  if (!job) return;
  job->setParent(this);
  connect(job, &KJob::result, this, [this](KJob *result) {
    if (result->error() && result->error() != KIO::ERR_USER_CANCELED) error(result->errorString());
  });
}
bool DesktopActions::Transfer(const QStringList &sources, const QString &destination, bool copy) {
  return TransferWithPlacement(sources, destination, copy, {});
}
bool DesktopActions::TransferWithPlacement(const QStringList &sources, const QString &destination, bool copy, const QString &request) {
  const auto from = urls(sources), to = urls({destination});
  if (request.size() > 128 || from.isEmpty() || to.size() != 1 || to.first().scheme() == "trash" ||
      from.contains(QUrl("trash:/"))) return false;
  std::function<void(const QUrl &)> placement;
  if (!request.isEmpty()) {
    placement = [this, request, directory = to.first()](const QUrl &url) {
      const auto item = url.adjusted(QUrl::StripTrailingSlash);
      if (item.adjusted(QUrl::RemoveFilename).matches(directory, QUrl::StripTrailingSlash))
        emit PlacementTarget(request, item.toString(QUrl::FullyEncoded));
    };
    // Announce ordinary targets before filesystem notifications arrive. KIO
    // reports actual renamed/numbered targets through the same callback.
    for (const auto &source : from) {
      auto target = to.first();
      target.setPath(target.path() + (target.path().endsWith('/') ? "" : "/") + source.fileName());
      placement(target);
    }
  }
  auto *job = Fusion::transferFiles(from, to.first(), copy ? Fusion::TransferOperation::Copy
                                                         : Fusion::TransferOperation::Move, nullptr, placement);
  connect(job, &KJob::result, this, [this, sources, destination, copy, request](KJob *result) {
    emit TransferFinished(sources, destination, copy, !result->error());
    if (!request.isEmpty()) emit PlacementFinished(request);
  });
  track(job);
  return true;
}
bool DesktopActions::Open(const QStringList &sources, bool choose) {
  const auto files = urls(sources);
  if (files.isEmpty()) return false;
  // Reply to the desktop before any application chooser enters its event loop.
  QTimer::singleShot(0, this, [this, files, choose] {
    KFileItemList selected;
    for (const auto &url : files) {
      const KFileItem item(url);
      if (item.isDir() || url == QUrl("trash:/")) {
        if (!QProcess::startDetached(Fusion::root()+"/scripts/files.sh",
                {"--external", "--new-window", url.toString(QUrl::FullyEncoded)}))
          error("Could not open the folder in Fusion Files.");
        continue;
      }
      if (!choose && item.mimetype() == "application/x-desktop") {
        auto *job = new KIO::OpenUrlJob(url, item.mimetype());
        job->setRunExecutables(true);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, nullptr));
        track(job); job->start();
        continue;
      }
      selected << item;
    }
    auto application = [this](const KFileItemList &items) {
      Fusion::ApplicationDialog dialog(items);
      if (dialog.exec() != QDialog::Accepted) return;
      auto request = dialog.request(); QJsonArray entries;
      for (const auto &item : items) entries << item.url().toString(QUrl::FullyEncoded);
      request["urls"] = entries; track(Fusion::launchApplication(request, nullptr));
    };
    if (choose && !selected.isEmpty()) { application(selected); return; }
    for (const auto &item : selected) {
      const auto preferred = KApplicationTrader::preferredService(item.mimetype());
      if (!preferred) { application({item}); continue; }
      track(Fusion::launchApplication({{"app", preferred->storageId()}, {"mime", item.mimetype()},
          {"urls", QJsonArray{item.url().toString(QUrl::FullyEncoded)}}}, nullptr));
    }
  });
  return true;
}
bool DesktopActions::Trash(const QStringList &sources) {
  const auto files = urls(sources);
  if (files.isEmpty() || std::any_of(files.begin(), files.end(), [](const QUrl &url) {
        return url.scheme() == "trash";
      })) return false;
  auto *job = new Fusion::RemovalJob(files, false, nullptr);
  auto succeeded = std::make_shared<QStringList>();
  connect(job, &Fusion::RemovalJob::removed, this, [succeeded](const QList<QUrl> &removed) {
    for (const auto &url : removed) *succeeded << url.toString(QUrl::FullyEncoded);
  });
  connect(job, &KJob::result, this, [this, sources, succeeded] {
    Fusion::Preferences preferences;
    emit TrashFinished(sources, *succeeded, preferences.settings.value("trashAnimation", true).toBool());
    RefreshTrash();
  });
  track(job);
  return true;
}
bool DesktopActions::RefreshTrash() {
  if (trashStatPending) return true;
  trashStatPending = true;
  auto *job = KIO::stat(QUrl("trash:/"), KIO::HideProgressInfo);
  job->setParent(this); job->setUiDelegate(nullptr);
  connect(job, &KJob::result, this, [this, job] {
    trashStatPending = false;
    if (!job->error()) emit TrashStateChanged(job->statResult().stringValue(KIO::UDSEntry::UDS_ICON_NAME) == "user-trash-full");
  });
  return true;
}
bool DesktopActions::Rename(const QString &source) {
  const auto files = urls({source});
  if (files.size() != 1 || files.first() == QUrl("trash:/")) return false;
  auto *dialog = new KIO::RenameFileDialog({KFileItem(files.first())}, nullptr);
  dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->show();
  return true;
}
bool DesktopActions::RenameTo(const QString &source, const QString &name) {
  const auto files = urls({source});
  if (files.size() != 1 || !files.first().isLocalFile() || !Fusion::validName(name)) return false;
  const auto from = files.first();
  auto to = from.adjusted(QUrl::RemoveFilename);
  to.setPath(to.path() + name);
  if (from == to) return false;
  // Inline rename must never replace another file. Let the editor report the
  // failure and keep the original label and selection in place.
  auto *job = KIO::moveAs(from, to, KIO::HideProgressInfo);
  job->setParent(this); job->setUiDelegate(nullptr);
  KIO::FileUndoManager::self()->recordCopyJob(job);
  connect(job, &KJob::result, this, [this, source, to](KJob *result) {
    emit RenameFinished(source, to.toString(QUrl::FullyEncoded), !result->error(), result->errorString());
  });
  return true;
}
bool DesktopActions::NewFolder(const QString &directory) {
  return NewFolderWithPlacement(directory, {});
}
bool DesktopActions::NewFolderWithPlacement(const QString &directory, const QString &request) {
  const auto paths = urls({directory});
  if (request.size() > 128 || paths.size() != 1) return false;
  auto *dialog = new QInputDialog;
  dialog->setWindowTitle("New folder"); dialog->setLabelText("Folder name:");
  dialog->setTextValue("New folder"); dialog->setAttribute(Qt::WA_DeleteOnClose);
  connect(dialog, &QInputDialog::rejected, this, [this, request] {
    if (!request.isEmpty()) emit PlacementFinished(request);
  });
  connect(dialog, &QInputDialog::textValueSelected, this, [this, request, location = paths.first()](const QString &name) {
    if (!Fusion::validName(name)) {
      error("Choose a name without /, and different from . or ..");
      if (!request.isEmpty()) emit PlacementFinished(request);
      return;
    }
    auto destination = location;
    destination.setPath(location.path() + (location.path().endsWith('/') ? "" : "/") + name);
    if (!request.isEmpty()) emit PlacementTarget(request, destination.toString(QUrl::FullyEncoded));
    auto *job = KIO::mkdir(destination);
    connect(job, &KJob::result, this, [this, request] {
      if (!request.isEmpty()) emit PlacementFinished(request);
    });
    track(job);
  });
  dialog->open();
  return true;
}
bool DesktopActions::Properties(const QStringList &sources) {
  const auto files = urls(sources);
  if (files.isEmpty()) return false;
  KFileItemList items; for (const auto &url : files) items << KFileItem(url);
  auto *dialog = new KPropertiesDialog(items);
  dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->show();
  return true;
}
