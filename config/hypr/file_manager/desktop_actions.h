#pragma once
#include <QDBusAbstractAdaptor>
#include <QUrl>
#include <QPointer>
#include <QHash>
#include "transfer_access.h"
class KJob;
class QMenu;
class QAction;

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
  bool TransferWithPlacement(const QStringList &sources, const QString &destination, bool copy, const QString &request);
  bool LinkWithPlacement(const QStringList &sources, const QString &destination, const QString &request);
  bool Open(const QStringList &sources, bool chooseApplication);
  bool Trash(const QStringList &sources);
  bool RefreshTrash();
  bool Rename(const QString &source);
  bool RenameTo(const QString &source, const QString &name);
  bool NewFolder(const QString &directory);
  bool NewFolderWithPlacement(const QString &directory, const QString &request);
  QString NewEntries();
  bool CreateNewWithPlacement(const QString &directory, const QString &id, const QString &request);
  bool ConfigureTemplates();
  bool Properties(const QStringList &sources);
  QString Menu(const QStringList &sources);
  bool MenuAction(const QString &identity);
  bool ConfigureMenu();
  bool EmptyTrash();
signals:
  void TrashFinished(const QStringList &requested, const QStringList &removed, bool animate);
  void TrashStateChanged(bool full);
  void TransferFinished(const QStringList &sources, const QString &destination, bool copy, bool success);
  void RenameFinished(const QString &source, const QString &destination, bool success, const QString &message);
  void PlacementTarget(const QString &request, const QString &destination);
  void PlacementFinished(const QString &request);
private:
  QPointer<QMenu> fileMenu;
  QHash<QString, QPointer<QAction>> menuActions;
  bool configuring = false;
  bool configuringTemplates = false;
  bool trashStatPending = false;
  bool transfer(const QStringList &sources, const QString &destination, Fusion::TransferOperation operation, const QString &request);
  static QList<QUrl> urls(const QStringList &values);
  void track(KJob *job);
  void error(const QString &message);
};
