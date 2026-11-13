#pragma once
#include "browser.h"
namespace XetalPreview {
class Pane;
}
class KJob;

class FilesWindow : public QMainWindow {
  Q_OBJECT
public:
  explicit FilesWindow(const QUrl &initial = Fusion::computerUrl(),
                       bool scanDrives = true,
                       const QString &settingsPath = {},
                       const QString &geometryKey = {});
  ~FilesWindow() override;
  Browser *browser() const;
  void openLocation(const QUrl &url, bool newTab = false);
  void reveal(const QUrl &url);
  void runAction(const QString &id);
  Fusion::Preferences preferences;
  Drives *drives;
signals:
  void operationFinished(int error);

protected:
  void showEvent(QShowEvent *) override;
  void resizeEvent(QResizeEvent *) override;
  void closeEvent(QCloseEvent *) override;
  virtual void openItem(const KFileItem &item, bool newTab = false);
  void preparePicker();

private:
  QString geometryKey, splitterKey;
  QTabWidget *tabs;
  QStackedWidget *addressHost;
  QList<QVariantMap> closedTabs;
  QAction *reopenTabAction;
  QTreeWidget *places;
  QTreeWidgetItem *quickRoot;
  QSplitter *splitter;
  XetalPreview::Pane *preview;
  QLabel *remotePreview;
  QStackedWidget *previewStack;
  QToolButton *views;
  QActionGroup *viewActions;
  QAction *backAction, *forwardAction, *upAction, *previewAction, *hiddenAction,
      *undoAction, *emptyTrashAction;
  QProcess theme;
  QTimer themeDebounce;
  QHash<QString, QAction *> shortcuts;
  void addTab(const QUrl &url);
  void rebuildPlaces();
  void pin(const QUrl &url);
  void placeMenu(const QPoint &point);
  void fileMenu(const QPoint &point);
  void computerMenu(const QPoint &point);
  void addVolumeActions(QMenu *menu, const Volume &volume);
  void volumeAction(const Volume &volume, const QString &id);
  void addArchiveActions(QMenu *menu, const KFileItemList &items, bool compress,
                     bool extract, const std::function<bool()> &guard = {});
  void configure();
  void updateCurrent();
  void updatePreview();
  void ensurePreviewWidth();
  void openAssociated(const KFileItemList &items);
  void chooseApplication(const KFileItemList &items);
  void execute(const QUrl &url);
  void track(KJob *job);
  void reloadTheme();
  void archive(bool extract);
  void customAction(const QVariantMap &entry);
  void showShortcuts();
  void message(const QString &text);
  void bind(const QString &id, const QString &key);
};
