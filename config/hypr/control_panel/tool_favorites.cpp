#include "tool_favorites.h"
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

ToolFavorites::ToolFavorites(const QString &profile, QObject *parent)
    : QObject(parent), root(profile) {
  debounce.setSingleShot(true);
  debounce.setInterval(100);
  deadline.setSingleShot(true);
  deadline.setInterval(15000);
  connect(&debounce, &QTimer::timeout, this, [this] { refreshWanted = true; pump(); });
  connect(&watcher, &QFileSystemWatcher::directoryChanged, this, [this] { refresh(); });
  connect(&watcher, &QFileSystemWatcher::fileChanged, this, [this] { refresh(); });
  connect(&worker, &QProcess::started, this, [this] {
    QJsonObject input;
    if (!current.id.isEmpty()) input = {{"id", current.id}, {"enabled", current.enabled}};
    worker.write(QJsonDocument(input).toJson(QJsonDocument::Compact));
    worker.closeWriteChannel();
  });
  connect(&worker, qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
          this, [this] { finish(); });
  connect(&worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) finish("Could not start the Favorites helper.");
  });
  connect(&deadline, &QTimer::timeout, this, [this] { timedOut = true; worker.kill(); });
  refresh();
}

void ToolFavorites::refresh() { debounce.start(); }

void ToolFavorites::setFavorite(const QString &id, bool enabled) {
  if (!loaded || pendingIds.contains(id)) return;
  pendingIds.insert(id);
  requests.enqueue({id, enabled});
  emit changed();
  pump();
}

void ToolFavorites::watch() {
  QStringList paths{root + "/launcher", root + "/launcher/favorites.json"};
  QDir applications(QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/applications");
  for (const auto &name : applications.entryList({"xetal-control-panel-*.desktop"}, QDir::Files))
    paths << applications.filePath(name);
  QString directory = applications.absolutePath();
  while (!QFileInfo::exists(directory) && QFileInfo(directory).absolutePath() != directory)
    directory = QFileInfo(directory).absolutePath();
  paths << directory;
  const auto existing = watcher.directories() + watcher.files();
  for (const auto &path : paths)
    if (QFileInfo::exists(path) && !existing.contains(path)) watcher.addPath(path);
}

void ToolFavorites::pump() {
  if (running) return;
  if (!requests.isEmpty()) current = requests.dequeue();
  else if (refreshWanted) { current = {}; refreshWanted = false; }
  else return;
  watch();
  running = true;
  timedOut = false;
  worker.start("python3", {root + "/control_panel/bridge.py",
                         current.id.isEmpty() ? "tool-favorites" : "tool-favorite"});
  deadline.start();
}

void ToolFavorites::finish(const QString &failure) {
  if (!running) return;
  deadline.stop();
  const auto reply = QJsonDocument::fromJson(worker.readAllStandardOutput()).object();
  QString message = timedOut ? "Favorites did not respond. Please try again." : failure;
  if (message.isEmpty()) message = reply["error"].toString();
  if (message.isEmpty() && (worker.exitStatus() != QProcess::NormalExit || worker.exitCode() != 0
                           || !reply["favorites"].isArray()))
    message = "Could not read or save Favorites. Please try again.";
  worker.readAllStandardError();
  if (message.isEmpty()) {
    favorites.clear();
    for (const auto &value : reply["favorites"].toArray()) favorites.insert(value.toString());
    loaded = true;
    readError.clear();
  } else if (current.id.isEmpty()) readError = message;
  const bool edited = !current.id.isEmpty();
  pendingIds.remove(current.id);
  running = false;
  emit changed();
  if (!message.isEmpty() && edited) {
    refreshWanted = true;
    emit failed(message);
  }
  QTimer::singleShot(0, this, [this] { pump(); });
}
