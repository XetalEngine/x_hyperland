#include "desktop_actions.h"
#include "applications.h"
#include "core.h"
#include "context_actions.h"
#include <QtWidgets>
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
  return transfer(sources, destination, copy ? Fusion::TransferOperation::Copy : Fusion::TransferOperation::Move, request);
}
bool DesktopActions::LinkWithPlacement(const QStringList &sources, const QString &destination, const QString &request) {
  return transfer(sources, destination, Fusion::TransferOperation::Link, request);
}
bool DesktopActions::transfer(const QStringList &sources, const QString &destination, Fusion::TransferOperation operation, const QString &request) {
  const auto from = urls(sources), to = urls({destination});
  if (request.size() > 128 || from.isEmpty() || to.size() != 1 || !Fusion::fileDropDestination(to.first()) ||
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
  const bool copy = operation != Fusion::TransferOperation::Move;
  auto *job = Fusion::transferFiles(from, to.first(), operation, nullptr, placement);
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

bool DesktopActions::EmptyTrash() {
  QTimer::singleShot(0, this, [this] { Fusion::emptyTrash(nullptr, [this] { RefreshTrash(); }); });
  return true;
}
bool DesktopActions::ConfigureMenu() {
  if (configuring) return true;
  configuring = true;
  QTimer::singleShot(0, this, [this] {
    Fusion::Preferences preferences;
    Fusion::customizeMenu(preferences, nullptr, "desktopMenu");
    configuring = false;
  });
  return true;
}
bool DesktopActions::MenuAction(const QString &identity) {
  const auto action = menuActions.value(identity);
  if (!action || !action->isEnabled()) return false;
  QTimer::singleShot(0, this, [action] { if (action) action->trigger(); });
  return true;
}
QString DesktopActions::Menu(const QStringList &sources) {
  const auto files = urls(sources);
  if (files.isEmpty()) return "[]";
  if (fileMenu) delete fileMenu;
  fileMenu = new QMenu;
  menuActions.clear();
  Fusion::Preferences preferences;
  const auto entries = preferences.menu("desktopMenu");
  KFileItemList items;
  for (const auto &file : files) items << KFileItem(file);
  const bool trash = files.contains(QUrl("trash:/"));
  const bool directories = std::all_of(items.begin(), items.end(), [](const KFileItem &item) { return item.isDir(); });
  auto directory = QUrl::fromLocalFile(QStandardPaths::writableLocation(QStandardPaths::DesktopLocation));
  bool compress = false, extract = false, addedArk = false;
  for (const auto &entry : entries) {
    if (entry["id"] == "compress") compress = entry.value("enabled", true).toBool();
    if (entry["id"] == "extract") extract = entry.value("enabled", true).toBool();
  }
  for (const auto &entry : entries) {
    if (!entry.value("enabled", true).toBool()) continue;
    const auto id = entry["id"].toString();
    if (trash && id != "open" && id != "properties") continue;
    if (id == "execute" && (files.size() != 1 || Fusion::executionCommand(files.first()).isEmpty())) continue;
    if ((id == "openTab" || id == "pin") && !directories) continue;
    if (id == "openWith" && directories) continue;
    if (id == "compress" || id == "extract") {
      if (!addedArk) Fusion::addArkActions(fileMenu, items, compress, extract, this, arkPlugins, directory,
                                         [this](const QString &text) { error(text); });
      addedArk = true; continue;
    }
    auto *action = fileMenu->addAction(Fusion::icon(entry["icon"].toString()),
        id == "openTab" ? "Open in floating window" : entry["name"].toString());
    action->setProperty("desktopAction", id);
    action->setProperty("iconName", entry["icon"]);
    if (id == "rename") action->setEnabled(files.size() == 1);
    connect(action, &QAction::triggered, this, [this, id, sources, files, directory, entry] {
      if (id == "open" || id == "openTab" || id == "openWith") { Open(sources, id == "openWith"); return; }
      if (id == "properties") { Properties(sources); return; }
      if (id == "pin") {
        Fusion::Preferences preferences; auto places = preferences.places();
        for (const auto &url : files) {
          if (std::none_of(places.begin(), places.end(), [&](const auto &p) { return QUrl(p["url"].toString()) == url; }))
            places << QVariantMap{{"name", Fusion::title(url)}, {"url", url.toString()}, {"icon", "folder"}};
        }
        preferences.setPlaces(places); return;
      }
      if (id == "delete") {
        auto *dialog = new QMessageBox(QMessageBox::Warning, "Delete permanently",
            QString("Permanently delete %1 selected item(s)? This cannot be undone.").arg(files.size()), QMessageBox::Cancel);
        dialog->setAttribute(Qt::WA_DeleteOnClose);
        auto *remove = dialog->addButton("Delete permanently", QMessageBox::DestructiveRole);
        dialog->setDefaultButton(QMessageBox::Cancel);
        connect(dialog, &QDialog::finished, this, [this, dialog, remove, files] {
          if (dialog->clickedButton() == remove) track(new Fusion::RemovalJob(files, true, nullptr));
        });
        dialog->open(); return;
      }
      QStringList command;
      QString working = directory.toLocalFile();
      if (id == "terminal") {
        if (files.size() == 1 && QFileInfo(files.first().toLocalFile()).isDir()) working = files.first().toLocalFile();
        command = {"kitty", "--directory", working};
      } else if (id == "execute") command = Fusion::executionCommand(files.first());
      else if (id.startsWith("custom:")) command = Fusion::expandCommand(entry["command"].toString(), files);
      else return; // Clipboard, inline rename and placement belong to the focused desktop surface.
      if (command.isEmpty()) { error("This action needs local files, or has an invalid command."); return; }
      const auto program = command.takeFirst();
      if (!QProcess::startDetached(program, command, working)) error("The file action could not be started.");
    });
  }
  const auto prefix = QUuid::createUuid().toString(QUuid::WithoutBraces);
  std::function<QJsonArray(QMenu *)> serialize = [&](QMenu *menu) {
    QJsonArray result;
    for (auto *action : menu->actions()) {
      if (!action->isVisible()) continue;
      QJsonObject row{{"name", action->text().replace("&&", "\x01").remove('&').replace("\x01", "&")},
        {"enabled", action->isEnabled()}, {"separator", action->isSeparator()},
        {"local", action->property("desktopAction").toString()}, {"icon", action->property("iconName").toString()}};
      if (action->menu()) row["children"] = serialize(action->menu());
      else {
        const auto key = prefix + ":" + QString::number(menuActions.size());
        menuActions[key] = action; row["action"] = key;
      }
      result.append(row);
    }
    return result;
  };
  return QString::fromUtf8(QJsonDocument(serialize(fileMenu)).toJson(QJsonDocument::Compact));
}
