#pragma once
#include <QFileSystemWatcher>
#include <QObject>
#include <QProcess>
#include <QQueue>
#include <QSet>
#include <QTimer>

// One asynchronous helper at a time: page navigation never waits on disk I/O.
class ToolFavorites final : public QObject {
  Q_OBJECT
public:
  explicit ToolFavorites(const QString &root, QObject *parent = nullptr);
  void setFavorite(const QString &id, bool enabled);
  void refresh();
  bool contains(const QString &id) const { return favorites.contains(id); }
  bool pending(const QString &id) const { return pendingIds.contains(id); }
  bool available() const { return loaded; }
  QString error() const { return readError; }

signals:
  void changed();
  void failed(const QString &message);

private:
  struct Request { QString id; bool enabled = false; };
  QString root;
  QProcess worker;
  QFileSystemWatcher watcher;
  QTimer debounce, deadline;
  QQueue<Request> requests;
  QSet<QString> favorites, pendingIds;
  Request current;
  QString readError;
  bool loaded = false, running = false, refreshWanted = true, timedOut = false;
  void watch();
  void pump();
  void finish(const QString &error = {});
};
