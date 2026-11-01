#pragma once
#include "core.h"
#include "drives.h"
#include "pathbar.h"
#include <KDirModel>
#include <KDirSortFilterProxyModel>
#include <KFileItem>
#include <QtWidgets>
class KJob;
class KFilePreviewGenerator;

class Browser : public QWidget {
  Q_OBJECT
public:
  Browser(Fusion::Preferences *preferences, Drives *drives,
          QWidget *parent = nullptr);
  ~Browser() override;
  PathBar *navigator;
  KDirModel *model;
  KDirSortFilterProxyModel *proxy;
  QListView *icons;
  QTreeView *details;
  QListWidget *cards;
  QLineEdit *filter;
  QLabel *notice;
  QStackedWidget *stack;
  int viewMode = 2;
  QUrl location() const;
  void navigate(const QUrl &url);
  void refresh();
  void setView(int mode);
  void setHidden(bool hidden);
  void selectUrl(const QUrl &url);
  void saveView();
  void editAddress();
  KFileItemList selectedItems() const;
  QList<QUrl> selectedUrls() const;
  QAbstractItemView *view() const;
  void selectAll();
signals:
  void locationChanged(const QUrl &url);
  void selectionChanged();
  void openRequested(const KFileItem &item, bool newTab);
  void contextRequested(const QPoint &position);
  void jobStarted(KJob *job);
  void statusChanged(const QString &text);

protected:
  bool eventFilter(QObject *watched, QEvent *event) override;

private:
  Fusion::Preferences *preferences;
  Drives *drives;
  QWidget *computer;
  KFilePreviewGenerator *previews;
  QUrl pendingSelection;
  void load(const QUrl &url);
  void updateCards();
  void updateStatus();
  void columnMenu(const QPoint &position);
  KFileItem itemAt(QAbstractItemView *view, const QPoint &position) const;
};
