#include "desktop_actions.h"
#include "applications.h"
#include "core.h"
#include "removal.h"
#include "transfers.h"
#include <KApplicationTrader>
#include <KIO/MkdirJob>
#include <KIO/RenameFileDialog>
#include <KPropertiesDialog>
#include <QCryptographicHash>

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
  const auto from = urls(sources), to = urls({destination});
  if (from.isEmpty() || to.size() != 1) return false;
  track(Fusion::transferFiles(from, to.first(), copy ? Fusion::TransferOperation::Copy
                                                   : Fusion::TransferOperation::Move, nullptr));
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
      if (item.isDir()) {
        if (!QProcess::startDetached(Fusion::root()+"/scripts/files.sh",
                {"--external", "--new-window", url.toString(QUrl::FullyEncoded)}))
          error("Could not open the folder in Fusion Files.");
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
  if (files.isEmpty()) return false;
  track(new Fusion::RemovalJob(files, false, nullptr));
  return true;
}
bool DesktopActions::Rename(const QString &source) {
  const auto files = urls({source});
  if (files.size() != 1) return false;
  auto *dialog = new KIO::RenameFileDialog({KFileItem(files.first())}, nullptr);
  dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->show();
  return true;
}
bool DesktopActions::NewFolder(const QString &directory) {
  const auto paths = urls({directory});
  if (paths.size() != 1) return false;
  auto *dialog = new QInputDialog;
  dialog->setWindowTitle("New folder"); dialog->setLabelText("Folder name:");
  dialog->setTextValue("New folder"); dialog->setAttribute(Qt::WA_DeleteOnClose);
  connect(dialog, &QInputDialog::textValueSelected, this, [this, location = paths.first()](const QString &name) {
    if (!Fusion::validName(name)) { error("Choose a name without /, and different from . or .."); return; }
    auto destination = location;
    destination.setPath(location.path() + (location.path().endsWith('/') ? "" : "/") + name);
    track(KIO::mkdir(destination));
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
