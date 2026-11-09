#pragma once
#include "core.h"
#include "drives.h"
#include "pathbar.h"
#include "search.h"
#include <KDirModel>
#include <KDirSortFilterProxyModel>
#include <KFileItem>
#include <QtWidgets>
class KJob;
class KFilePreviewGenerator;
namespace KIO { class Job; }

class Browser : public QWidget {
  Q_OBJECT
public:
  Browser(Fusion::Preferences *preferences, Drives *drives,
          QWidget *parent = nullptr);
  ~Browser() override;
  PathBar *navigator;
  KDirModel *model;
  KDirSortFilterProxyModel *proxy;
  QListView *icons = nullptr;
  QTreeView *details = nullptr;
  QLineEdit *filter;
  SearchPane *search = nullptr;
  QLabel *notice;
  QStackedWidget *stack;
  int viewMode = 2;
  QUrl location() const;
  void navigate(const QUrl &url);
  void refresh();
  void refreshIcons();
  void setView(int mode);
  void setHidden(bool hidden);
  void setThumbnails(bool enabled);
  void setPickerFilter(const QJsonArray &patterns, bool directoriesOnly);
  void selectUrl(const QUrl &url);
  void saveView();
  void editAddress();
  void beginSearch();
  void closeSearch();
  bool searchActive() const;
  KFileItemList selectedItems() const;
  QList<QUrl> selectedUrls() const;
  Volume selectedVolume() const;
  QAbstractItemView *view() const;
  void selectAll();
  void renameSelected();
signals:
  void locationChanged(const QUrl &url);
  void selectionChanged();
  void openRequested(const KFileItem &item, bool newTab);
  void contextRequested(const QPoint &position);
  void computerContextRequested(const QPoint &position);
  void jobStarted(KJob *job);
  void statusChanged(const QString &text);
  void hiddenFilesRequested();

protected:
  bool eventFilter(QObject *watched, QEvent *event) override;

private:
  Fusion::Preferences *preferences;
  Drives *drives;
  QWidget *computer;
  QLabel *emptyDrives;
  QSplitter *driveSplitter;
  struct DriveSection {
    QScrollArea *scroll = nullptr;
    QVBoxLayout *layout = nullptr;
    QMap<QString, QGroupBox *> groups;
  };
  DriveSection mountedSection, usbSection, unmountedSection;
  QList<QListWidget *> driveLists;
  bool driveLayoutQueued = false, fitSectionContents = false;
  KFilePreviewGenerator *previews;
  QUrl pendingSelection;
  QWidget *folderMessage;
  QFrame *administratorBar;
  QLabel *folderHeading, *folderExplanation, *folderSymbol;
  QPushButton *folderAction;
  bool listingBusy = false, listingFailed = false, privateFolder = false;
  quint64 accessGeneration = 0;
  QString listingError;
  enum class FolderAction { None, ShowHidden, Unlock, Retry };
  FolderAction currentFolderAction = FolderAction::None;
  void updateFolderMessage();
  void handleListingError(KIO::Job *job);
  void load(const QUrl &url);
  void updateCards();
  void queueDriveLayout(bool fitContents = false);
  void fitDriveSections();
  void configureCards(QListWidget *list);
  void updateStatus();
  void columnMenu(const QPoint &position);
  KFileItem itemAt(QAbstractItemView *view, const QPoint &position) const;
  void renameItem(const QModelIndex &index, const QString &name);
};
