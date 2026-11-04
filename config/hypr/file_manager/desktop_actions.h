#pragma once
#include <QDBusAbstractAdaptor>
#include <QUrl>
class KJob;

// The desktop surface uses the same transfer/conflict and application handlers
// as Files. This interface belongs only to the current Hyprland login.
class DesktopActions : public QDBusAbstractAdaptor {
  Q_OBJECT
  Q_CLASSINFO("D-Bus Interface", "org.xetal.FusionFiles.Desktop1")
public:
  explicit DesktopActions(QObject *parent);
  static QString serviceName();
public slots:
  bool Transfer(const QStringList &sources, const QString &destination, bool copy);
  bool Open(const QStringList &sources, bool chooseApplication);
  bool Trash(const QStringList &sources);
  bool RefreshTrash();
  bool Rename(const QString &source);
  bool RenameTo(const QString &source, const QString &name);
  bool NewFolder(const QString &directory);
  bool Properties(const QStringList &sources);
signals:
  void TrashFinished(const QStringList &requested, const QStringList &removed, bool animate);
  void TrashStateChanged(bool full);
  void TransferFinished(const QStringList &sources, const QString &destination, bool copy, bool success);
  void RenameFinished(const QString &source, const QString &destination, bool success, const QString &message);
private:
  bool trashStatPending = false;
  static QList<QUrl> urls(const QStringList &values);
  void track(KJob *job);
  void error(const QString &message);
};
