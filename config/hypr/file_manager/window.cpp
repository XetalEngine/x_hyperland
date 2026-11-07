#include "window.h"
#include "context_actions.h"
#include "transfers.h"
#include "applications.h"
#include "removal.h"
#include "trash_animation.h"
#include "../theme/file_preview.hpp"
#include "../theme/window_chrome.hpp"
#include "../theme/icon_theme.hpp"
#include <KAbstractFileItemActionPlugin>
#include <KApplicationTrader>
#include <KFileItemActions>
#include <KFileItemListProperties>
#include <KIO/ApplicationLauncherJob>
#include <KIO/CopyJob>
#include <KIO/CommandLauncherJob>
#include <KIO/DeleteJob>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegate>
#include <KIO/JobUiDelegateFactory>
#include <KIO/MkdirJob>
#include <KIO/OpenUrlJob>
#include <KIO/Paste>
#include <KIO/PasteJob>
#include <KIO/RenameFileDialog>
#include <KIO/RestoreJob>
#include <KJobWidgets>
#include <KPluginFactory>
#include <KPluginMetaData>
#include <KPropertiesDialog>
#include <KService>
#include <memory>

namespace {
enum PlaceRole { UrlRole = Qt::UserRole, PinRole, VolumeRole, SectionRole };
class PlacesTree : public QTreeWidget {
public:
  using QTreeWidget::QTreeWidget;
  std::function<void(const QUrl &)> pin;
  std::function<void(int, int)> reorder;
  std::function<void(KJob *)> transfer;

protected:
  void drawRow(QPainter *painter, const QStyleOptionViewItem &option,
               const QModelIndex &index) const override {
    // Qt paints the selected item background again in the indentation gutter.
    // Keep the themed highlight/marker inside the item, then draw the tree's
    // disclosure arrows separately over the unchanged sidebar background.
    const auto item = visualRect(index);
    painter->save();
    painter->setClipRect(item, Qt::IntersectClip);
    QTreeWidget::drawRow(painter, option, index);
    painter->restore();
    auto branches = option.rect;
    if (isRightToLeft()) branches.setLeft(item.right() + 1);
    else branches.setRight(item.left() - 1);
    if (!branches.isEmpty()) QTreeWidget::drawBranches(painter, branches, index);
  }
  void startDrag(Qt::DropActions) override {
    const auto *item = currentItem();
    if (!item || !item->data(0, PinRole).isValid())
      return;
    auto *mime = new QMimeData;
    mime->setUrls({QUrl(item->data(0, UrlRole).toString())});
    mime->setData("application/x-fusion-place",
                  QByteArray::number(item->data(0, PinRole).toInt()));
    auto *drag = new QDrag(this);
    drag->setMimeData(mime);
    drag->exec(Qt::MoveAction | Qt::CopyAction);
  }
  void dragEnterEvent(QDragEnterEvent *event) override {
    if (event->mimeData()->hasFormat("application/x-fusion-place"))
      event->acceptProposedAction();
    else if (Fusion::acceptsFileDrop(event->mimeData())) {
      const auto action=Fusion::fileDropAction(event->mimeData(),event->modifiers(),event->possibleActions());
      if (action!=Qt::IgnoreAction) { event->setDropAction(action);event->accept(); }
    }
  }
  void dragMoveEvent(QDragMoveEvent *event) override {
    if (event->mimeData()->hasFormat("application/x-fusion-place"))
      event->acceptProposedAction();
    else if (dropFolder(event->position().toPoint()).isValid()) {
      const auto action=Fusion::fileDropAction(event->mimeData(),event->modifiers(),event->possibleActions());
      if (action!=Qt::IgnoreAction) { event->setDropAction(action);event->accept(); }
      else event->ignore();
    } else if (pinArea(event->position().toPoint()) && event->mimeData()->hasUrls()) {
      event->setDropAction(Qt::CopyAction);event->accept();
    } else event->ignore();
  }
  void dropEvent(QDropEvent *event) override {
    if (event->source() == this &&
        event->mimeData()->hasFormat("application/x-fusion-place")) {
      auto *item = itemAt(event->position().toPoint());
      if (item && item->data(0, PinRole).isValid())
        reorder(event->mimeData()->data("application/x-fusion-place").toInt(),
                item->data(0, PinRole).toInt());
      event->acceptProposedAction();
      return;
    }
    const auto target=dropFolder(event->position().toPoint());
    if (target.isValid() && !event->mimeData()->hasFormat("application/x-fusion-place")) {
      const auto action=Fusion::fileDropAction(event->mimeData(),event->modifiers(),event->possibleActions());
      if (action==Qt::IgnoreAction) { event->ignore();return; }
      if (auto *job=Fusion::dropFiles(event,target,window(),viewport()->mapToGlobal(event->position().toPoint()))) {
        transfer(job);event->setDropAction(action);event->accept();
      } else event->ignore();
      return;
    }
    if (pinArea(event->position().toPoint()) || event->mimeData()->hasFormat("application/x-fusion-place")) {
      for (const auto &url : event->mimeData()->urls())
        if (url.isLocalFile() && QFileInfo(url.toLocalFile()).isDir())
          pin(url);
      event->setDropAction(Qt::CopyAction);event->accept();
    } else event->ignore();
  }
private:
  bool pinArea(const QPoint &point) const {
    const auto *item=itemAt(point);
    return !item || item->data(0,SectionRole).toString()=="quickAccess";
  }
  QUrl dropFolder(const QPoint &point) const {
    const auto *item=itemAt(point);
    if (!item) return {};
    const QUrl url(item->data(0,UrlRole).toString());
    if (url.isEmpty() || Fusion::isComputer(url) || url.scheme()=="trash" || url.scheme()=="network") return {};
    if (url.isLocalFile() && !QFileInfo(url.toLocalFile()).isDir()) return {};
    return url;
  }
};
bool isTextEditing() {
  auto *focus = QApplication::focusWidget();
  return qobject_cast<QLineEdit *>(focus) || qobject_cast<QTextEdit *>(focus) ||
         qobject_cast<QPlainTextEdit *>(focus);
}
} // namespace
FilesWindow::FilesWindow(const QUrl &initial, bool scanDrives,
                         const QString &settingsPath, const QString &geometryKey)
    : preferences(settingsPath), geometryKey(geometryKey.isEmpty()
          ? (qApp->desktopFileName() == "xetal-files-external" ? "external/geometry" : "geometry")
          : geometryKey),
      splitterKey(this->geometryKey.startsWith("picker/")
          ? this->geometryKey.section('/', 0, -2)+"/splitter" : "splitter") {
  setObjectName("fusionFiles");
  setAttribute(Qt::WA_DeleteOnClose);
  setWindowTitle("Fusion Files");
  setWindowIcon(Fusion::icon("fusion-computer"));
  resize(1180, 760);
  setMinimumSize(760, 450);
  // Ordinary launches follow tiling or the launcher's explicit Ctrl-click
  // rules. Restoring a Qt geometry blob here can request maximization before
  // those rules run. External folder requests remember only their own size;
  // placement and mode come from the compositor's first-map rule.
  if (this->geometryKey == "external/geometry") {
    const auto size = preferences.settings.value("external/size").toSize();
    if (size.isValid() && size.width() <= 32768 && size.height() <= 32768)
      resize(size.expandedTo(minimumSize()));
  } else if (this->geometryKey != "geometry" && preferences.settings.contains(this->geometryKey))
    restoreGeometry(preferences.settings.value(this->geometryKey).toByteArray());
  drives = new Drives(this, scanDrives);
  connect(drives, &Drives::populateFileMenu, this,
          &FilesWindow::addVolumeActions);
  auto *toolbar = addToolBar("Navigation");
  toolbar->setMovable(false);
  toolbar->setIconSize({20, 20});
  auto tool = [&](const QString &icon, const QString &label,
                  const std::function<void()> &call) {
    auto *a = toolbar->addAction(Fusion::icon(icon), label);
    a->setProperty("fusionIcon", icon);
    connect(a, &QAction::triggered, this, call);
    return a;
  };
  backAction =
      tool("go-previous", "Back", [this] { browser()->navigator->goBack(); });
  forwardAction =
      tool("go-next", "Forward", [this] { browser()->navigator->goForward(); });
  upAction = tool("go-up", "Up", [this] { browser()->navigator->goUp(); });
  tool("view-refresh", "Refresh", [this] { browser()->refresh(); });
  toolbar->addSeparator();
  auto *brand = new QLabel("  Fusion Files  ");
  QFont brandFont = font();
  brandFont.setPointSize(13);
  brandFont.setBold(true);
  brand->setFont(brandFont);
  toolbar->addWidget(brand);
  auto *spacer = new QWidget;
  spacer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  toolbar->addWidget(spacer);
  auto *empty = new QToolButton;
  empty->setObjectName("emptyTrashButton");
  empty->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
  empty->setText("Empty Trash"); empty->setIcon(Fusion::icon("user-trash"));
  connect(empty, &QToolButton::clicked, this, [this] { Fusion::emptyTrash(this); });
  emptyTrashAction = toolbar->addWidget(empty);
  emptyTrashAction->setVisible(false);
  auto *folder =
      tool("folder-new", "New folder", [this] { runAction("newFolder"); });
  folder->setToolTip("New folder · Ctrl+Shift+N");
  views = new QToolButton;
  views->setObjectName("viewMode");
  views->setPopupMode(QToolButton::InstantPopup);
  views->setToolButtonStyle(Qt::ToolButtonIconOnly);
  views->setAccessibleName("Folder view");
  auto *viewMenu = new QMenu(views);viewMenu->setObjectName("folderViewMenu");views->setMenu(viewMenu);
  viewActions = new QActionGroup(this);viewActions->setExclusive(true);
  const QStringList viewNames{"Small icons", "Medium icons", "Large icons", "List", "Details"};
  for (int mode=0;mode<viewNames.size();++mode) {
    const QString icon = mode==4 ? "view-list-details" : mode==3 ? "view-list-icons" : "view-grid";
    auto *action=viewMenu->addAction(Fusion::icon(icon),viewNames[mode]);
    action->setProperty("fusionIcon",icon);action->setObjectName("folderView"+QString::number(mode));
    action->setData(mode);action->setCheckable(true);viewActions->addAction(action);
  }
  toolbar->addWidget(views);
  previewAction = tool("view-preview", "Preview pane", [this] {
    previewStack->setVisible(previewAction->isChecked());
    preferences.settings.setValue("preview", previewAction->isChecked());
    updatePreview();
  });
  previewAction->setCheckable(true);
  previewAction->setObjectName("previewPaneAction");
  previewAction->setChecked(
      preferences.settings.value("preview", true).toBool());
  auto *menuButton = new QToolButton;
  menuButton->setProperty("fusionIcon", "application-menu");
  menuButton->setIcon(Fusion::icon("application-menu"));
  menuButton->setToolTip("File manager options");
  menuButton->setObjectName("fileOptions");
  menuButton->setPopupMode(QToolButton::InstantPopup);
  auto *menu = new QMenu(menuButton);
  menuButton->setMenu(menu);
  menu->setObjectName("fileOptionsMenu");
  toolbar->addWidget(menuButton);
  toolbar->addSeparator();
  toolbar->addWidget(new FusionChrome::Controls(this));
  menu->addAction("New tab", this, [this] { runAction("newTab"); });
  menu->addAction("New window", this, [this] { runAction("newWindow"); });
  menu->addAction("Open location…", this, [this] { browser()->editAddress(); });
  menu->addAction("Connect to server…", this, [this] { runAction("connect"); });
  menu->addSeparator();
  hiddenAction = menu->addAction("Show hidden files");
  hiddenAction->setObjectName("hiddenFilesAction");
  hiddenAction->setCheckable(true);
  hiddenAction->setShortcuts({QKeySequence("Alt+."), QKeySequence("Ctrl+H")});
  addAction(hiddenAction);
  shortcuts["hidden"] = hiddenAction;
  hiddenAction->setChecked(
      preferences.settings.value("hidden", false).toBool());
  connect(hiddenAction, &QAction::toggled, this, [this](bool value) {
    preferences.settings.setValue("hidden", value);
    for (int i = 0; i < tabs->count(); ++i)
      static_cast<Browser *>(tabs->widget(i))->setHidden(value);
  });
  menu->addAction("Customize context menu…", this, &FilesWindow::customizeMenu);
  menu->addAction(Fusion::icon("configure"), "Configure Fusion Files…", this, &FilesWindow::configure)->setObjectName("configureFiles");
  undoAction = menu->addAction("Undo", this, [this] { runAction("undo"); });
  undoAction->setEnabled(false);
  menu->addSeparator();
  menu->addAction("Keyboard shortcuts", this, &FilesWindow::showShortcuts);
  auto *body = new QWidget;
  body->setObjectName("filesBody");
  auto *layout = new QVBoxLayout(body);
  layout->setContentsMargins(0, 0, 0, 0);
  setCentralWidget(body);
  splitter = new QSplitter;
  layout->addWidget(splitter);
  auto *tree = new PlacesTree;
  places = tree;
  places->setObjectName("places");
  places->setHeaderHidden(true);
  places->setIndentation(17);
  places->setIconSize({21, 21});
  places->setMinimumWidth(165);
  places->setContextMenuPolicy(Qt::CustomContextMenu);
  places->setDragEnabled(true);
  places->setAcceptDrops(true);
  places->setDropIndicatorShown(true);
  splitter->addWidget(places);
  tree->pin = [this](const QUrl &url) { pin(url); };
  tree->transfer = [this](KJob *job) { track(job); };
  tree->reorder = [this](int from, int to) {
    auto list = preferences.places();
    if (from >= 0 && to >= 0 && from < list.size() && to < list.size()) {
      list.move(from, to);
      preferences.setPlaces(list);
      rebuildPlaces();
    }
  };
  tabs = new QTabWidget;
  // The shared theme supplies the tab borders. Qt's document frame draws a
  // second baseline at a different height beneath the corner (+) button.
  tabs->setDocumentMode(false);
  tabs->tabBar()->setDrawBase(false);
  tabs->tabBar()->setExpanding(false);
  tabs->setTabsClosable(true);
  tabs->setMovable(true);
  tabs->setTabBarAutoHide(false);
  splitter->addWidget(tabs);
  auto *tabCorner = new QWidget;
  auto *cornerLayout = new QVBoxLayout(tabCorner);
  cornerLayout->setContentsMargins(0, 2, 2, 0);
  cornerLayout->setSpacing(0);
  auto *previewToggle = new QToolButton;
  previewToggle->setObjectName("previewToggle");
  previewToggle->setFixedSize(24, 20);
  previewToggle->setAutoRaise(true);
  auto updatePreviewToggle = [this, previewToggle] {
    const bool visible = previewAction->isChecked();
    previewToggle->setArrowType(visible ? Qt::RightArrow : Qt::LeftArrow);
    previewToggle->setAccessibleName(visible ? "Hide preview pane" : "Show preview pane");
    previewToggle->setToolTip(previewToggle->accessibleName() + " · Alt+P");
  };
  updatePreviewToggle();
  connect(previewAction, &QAction::toggled, previewToggle, updatePreviewToggle);
  connect(previewToggle, &QToolButton::clicked, previewAction, &QAction::trigger);
  cornerLayout->addWidget(previewToggle, 0, Qt::AlignHCenter);
  auto *newTab = new QToolButton;
  newTab->setObjectName("newTabButton");
  newTab->setText("+");
  newTab->setToolTip("New tab · Ctrl+T");
  newTab->setFixedSize(24, 20);
  cornerLayout->addWidget(newTab, 0, Qt::AlignHCenter);
  tabs->setCornerWidget(tabCorner);
  connect(newTab, &QToolButton::clicked, this,
          [this] { addTab(Fusion::computerUrl()); });
  previewStack = new QStackedWidget;
  previewStack->setMinimumWidth(240);
  previewStack->setMaximumWidth(420);
  splitter->addWidget(previewStack);
  preview = new XetalPreview::Pane(previewStack);
  preview->setObjectName("filePreview");
  preview->setMaximumWidth(QWIDGETSIZE_MAX);
  previewStack->addWidget(preview);
  remotePreview = new QLabel;
  remotePreview->setWordWrap(true);
  remotePreview->setTextFormat(Qt::PlainText);
  remotePreview->setContentsMargins(18, 18, 18, 18);
  remotePreview->setAlignment(Qt::AlignTop);
  previewStack->addWidget(remotePreview);
  previewStack->setVisible(previewAction->isChecked());
  splitter->setStretchFactor(0, 0);
  splitter->setStretchFactor(1, 1);
  splitter->setStretchFactor(2, 0);
  splitter->setSizes({210, 720, 270});
  // Pickers already remember geometry per application and operation. Keep
  // their panel widths there too, rather than inheriting a collapsed Files
  // sidebar or overwriting the main window's layout when the dialog closes.
  if (preferences.settings.contains(splitterKey))
    splitter->restoreState(
        preferences.settings.value(splitterKey).toByteArray());
  // Navigation is part of every Files window, including This PC, external
  // folder windows and pickers. Repair old collapsed layouts after restoring
  // them, and keep the divider from hiding the tree again.
  splitter->setCollapsible(0, false);
  auto sizes = splitter->sizes();
  if (sizes.first() < places->minimumWidth()) {
    sizes[0] = 210;
    splitter->setSizes(sizes);
  }
  connect(tabs, &QTabWidget::currentChanged, this, [this] { updateCurrent(); });
  connect(tabs, &QTabWidget::tabCloseRequested, this, [this](int index) {
    if (tabs->count() == 1) {
      close();
      return;
    }
    auto *tab = static_cast<Browser *>(tabs->widget(index));
    tab->saveView();
    tabs->removeTab(index);
    tab->deleteLater();
  });
  connect(viewActions, &QActionGroup::triggered, this, [this](QAction *action) {
    if (browser()) {
      browser()->setView(action->data().toInt());
      updateCurrent();
    }
  });
  connect(places, &QTreeWidget::itemClicked, this,
          [this](QTreeWidgetItem *item) {
            if (item->data(0, VolumeRole).isValid())
              drives->operate(item->data(0, VolumeRole).value<Volume>(), "open",
                              this);
            else if (!item->data(0, UrlRole).toString().isEmpty())
              openLocation(QUrl(item->data(0, UrlRole).toString()));
          });
  connect(places, &QWidget::customContextMenuRequested, this,
          &FilesWindow::placeMenu);
  auto saveExpansion = [this](QTreeWidgetItem *item) {
    const auto section = item->data(0, SectionRole).toString();
    if (!section.isEmpty()) {
      preferences.settings.setValue("sidebar/" + section, item->isExpanded());
      preferences.settings.sync();
    }
  };
  connect(places, &QTreeWidget::itemExpanded, this, saveExpansion);
  connect(places, &QTreeWidget::itemCollapsed, this, saveExpansion);
  connect(drives, &Drives::changed, this, &FilesWindow::rebuildPlaces);
  connect(drives, &Drives::message, this, &FilesWindow::message);
  connect(drives, &Drives::browse, this,
          [this](const QUrl &url) { openLocation(url); });
  auto *undo = KIO::FileUndoManager::self();
  connect(undo, &KIO::FileUndoManager::undoAvailable, undoAction,
          &QAction::setEnabled);
  connect(undo, &KIO::FileUndoManager::undoTextChanged, undoAction,
          &QAction::setText);
  for (const auto &binding :
       QList<QStringList>{{"rename", "F2"},
                          {"refresh", "F5"},
                          {"copy", "Ctrl+C"},
                          {"cut", "Ctrl+X"},
                          {"paste", "Ctrl+V"},
                          {"trash", "Delete"},
                          {"delete", "Shift+Delete"},
                          {"undo", "Ctrl+Z"},
                          {"newFolder", "Ctrl+Shift+N"},
                          {"selectAll", "Ctrl+A"},
                          {"address", "Ctrl+L"},
                          {"addressAlt", "Alt+D"},
                          {"back", "Alt+Left"},
                          {"forward", "Alt+Right"},
                          {"up", "Alt+Up"},
                          {"preview", "Alt+P"},
                          {"newTab", "Ctrl+T"},
                          {"closeTab", "Ctrl+W"},
                          {"newWindow", "Ctrl+N"},
                          {"nextTab", "Ctrl+Tab"},
                          {"previousTab", "Ctrl+Shift+Tab"},
                          {"properties", "Alt+Return"},
                          {"filter", "Ctrl+F"},
                          {"copyPath", "Ctrl+Shift+C"}})
    bind(binding[0], binding[1]);
  addTab(initial);
  rebuildPlaces();
  themeDebounce.setSingleShot(true);
  themeDebounce.setInterval(100);
  connect(&themeDebounce, &QTimer::timeout, this, &FilesWindow::reloadTheme);
  auto *watcher = new QFileSystemWatcher({Fusion::root() + "/theme"}, this);
  connect(watcher, &QFileSystemWatcher::directoryChanged, this,
          [this] { themeDebounce.start(); });
  connect(&theme, &QProcess::finished, this,
          [this](int code, QProcess::ExitStatus) {
            if (code)
              return;
            const auto value =
                QJsonDocument::fromJson(theme.readAllStandardOutput()).object();
            if (!value.contains("stylesheet"))
              return;
            QPalette palette;
            const auto colors = value["colors"].toObject();
            const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
            for (auto it = colors.begin(); it != colors.end(); ++it) {
              int role = roles.keyToValue(it.key().toUtf8());
              if (role >= 0)
                palette.setColor(QPalette::All, QPalette::ColorRole(role),
                                 QColor(it.value().toString()));
            }
            for (auto role :
                 {QPalette::Text, QPalette::WindowText, QPalette::ButtonText})
              palette.setColor(QPalette::Disabled, role,
                               QColor(colors["Disabled"].toString()));
            qApp->setPalette(palette);
            qApp->setProperty("fusionAccent",
                              QColor(colors["Accent"].toString()));
            qApp->setFont(QFont(value["font"].toString("Noto Sans"), 10));
            const auto iconTheme=value["iconTheme"].toString();
            const bool iconsChanged=property("fusionIconTheme").toString()!=iconTheme;
            setProperty("fusionIconTheme",iconTheme);
            XetalIcons::apply(Fusion::root());
            qApp->setStyleSheet(value["stylesheet"].toString());
            for (auto *action : findChildren<QAction *>())
              if (action->property("fusionIcon").isValid())
                action->setIcon(
                    Fusion::icon(action->property("fusionIcon").toString()));
            for (auto *button : findChildren<QToolButton *>())
              if (button->property("fusionIcon").isValid())
                button->setIcon(
                    Fusion::icon(button->property("fusionIcon").toString()));
            rebuildPlaces();
            if (iconsChanged)
              for (auto *page:findChildren<Browser *>()) page->refreshIcons();
            update();
          });
  reloadTheme();
}
Browser *FilesWindow::browser() const {
  return tabs ? qobject_cast<Browser *>(tabs->currentWidget()) : nullptr;
}
FilesWindow::~FilesWindow() {
  themeDebounce.stop();
  disconnect(&theme, nullptr, this, nullptr);
  for (auto *child : findChildren<QObject *>())
    disconnect(child, nullptr, this, nullptr);
  if (theme.state() != QProcess::NotRunning) {
    theme.kill();
    theme.waitForFinished(1000);
  }
  // Destroy views while their settings and drive service still exist.
  delete takeCentralWidget();
  tabs = nullptr;
  delete drives;
  drives = nullptr;
}
void FilesWindow::addTab(const QUrl &url) {
  auto *tab = new Browser(&preferences, drives, this);
  connect(tab, &Browser::locationChanged, this, [this, tab](const QUrl &url) {
    tabs->setTabText(tabs->indexOf(tab), Fusion::title(url));
    tabs->setTabToolTip(tabs->indexOf(tab), Fusion::displayPath(url));
    if (tab == browser())
      updateCurrent();
  });
  connect(tab, &Browser::selectionChanged, this, [this, tab] {
    if (tab == browser())
      updatePreview();
  });
  connect(tab, &Browser::contextRequested, this, &FilesWindow::fileMenu);
  connect(tab, &Browser::computerContextRequested, this,
          &FilesWindow::computerMenu);
  connect(tab, &Browser::openRequested, this, &FilesWindow::openItem);
  connect(tab, &Browser::jobStarted, this, &FilesWindow::track);
  connect(tab, &Browser::statusChanged, this, [this, tab](const QString &text) {
    if (tab == browser())
      statusBar()->showMessage(text);
  });
  connect(tab->navigator, &PathBar::historyChanged, this, [this, tab] {
    if (tab == browser())
      updateCurrent();
  });
  tabs->setCurrentIndex(tabs->addTab(tab, Fusion::title(url)));
  auto *close = new QToolButton;
  close->setText("×");
  close->setToolTip("Close tab");
  close->setAutoRaise(true);
  close->setFixedSize(24, 24);
  tabs->tabBar()->setTabButton(tabs->indexOf(tab), QTabBar::RightSide, close);
  connect(close, &QToolButton::clicked, this,
          [this, tab] { emit tabs->tabCloseRequested(tabs->indexOf(tab)); });
  tab->navigate(url);
  updateCurrent();
}
void FilesWindow::openLocation(const QUrl &url, bool newTab) {
  if (newTab)
    addTab(url);
  else
    browser()->navigate(url);
  show();
  raise();
  activateWindow();
}
void FilesWindow::reveal(const QUrl &url) {
  openLocation(url.adjusted(QUrl::RemoveFilename));
  browser()->selectUrl(url);
}
void FilesWindow::updateCurrent() {
  if (!browser())
    return;
  const QUrl url = browser()->location();
  emptyTrashAction->setVisible(url.scheme() == "trash");
  setWindowTitle(Fusion::title(url) + " — Fusion Files");
  views->setEnabled(!Fusion::isComputer(url));
  auto *viewAction=viewActions->actions().at(browser()->viewMode);viewAction->setChecked(true);
  views->setProperty("fusionIcon",viewAction->property("fusionIcon"));views->setIcon(viewAction->icon());
  views->setToolTip(Fusion::isComputer(url) ? "Folder view · open a folder to change its layout" : "Folder view · "+viewAction->text());
  const auto *navigator = browser()->navigator;
  backAction->setEnabled(navigator->historyIndex() + 1 <
                         navigator->historySize());
  forwardAction->setEnabled(navigator->historyIndex() > 0);
  upAction->setEnabled(!Fusion::isComputer(url));
  updatePreview();
  for (QTreeWidgetItemIterator it(places); *it; ++it)
    if ((*it)->data(0, UrlRole).toString() == url.toString()) {
      QSignalBlocker blocked(places);
      places->setCurrentItem(*it);
      break;
    }
}
void FilesWindow::updatePreview() {
  if (!browser() || !previewAction->isChecked())
    return;
  const auto items = browser()->selectedItems();
  if (items.size() == 1 && !items[0].url().isLocalFile()) {
    previewStack->setCurrentWidget(remotePreview);
    remotePreview->setText(items[0].name() + "\n\n" + items[0].mimetype() +
                           "\n" + QLocale().formattedDataSize(items[0].size()) +
                           "\n\n" + Fusion::displayPath(items[0].url()));
    preview->select({});
  } else {
    previewStack->setCurrentWidget(preview);
    preview->select(items.size() == 1 ? items[0].url().toLocalFile()
                                      : QString());
  }
}
void FilesWindow::rebuildPlaces() {
  const QUrl current = browser() ? browser()->location() : QUrl();
  QSignalBlocker blocker(places);
  const int scroll = places->verticalScrollBar()->value();
  const bool expanded =
      preferences.settings.value("sidebar/computer", true).toBool();
  const bool quickExpanded =
      preferences.settings.value("sidebar/quickAccess", true).toBool();
  const bool unmountedExpanded =
      preferences.settings.value("sidebar/unmounted", true).toBool();
  const QString selectedDrive =
      places->currentItem()
          ? places->currentItem()->data(0, VolumeRole).value<Volume>().device
          : QString();
  places->clear();
  auto add = [&](QTreeWidgetItem *parent, const QString &name,
                 const QString &icon, const QUrl &url) {
    auto *item =
        parent ? new QTreeWidgetItem(parent) : new QTreeWidgetItem(places);
    item->setText(0, name);
    item->setIcon(0, Fusion::icon(icon));
    if (url.isValid())
      item->setData(0, UrlRole, url.toString());
    item->setToolTip(0, Fusion::displayPath(url));
    if (url == current)
      places->setCurrentItem(item);
    return item;
  };
  auto *pc = add(nullptr, "This PC", "fusion-computer", Fusion::computerUrl());
  pc->setData(0, SectionRole, "computer");
  auto addVolume = [&](QTreeWidgetItem *parent, const Volume &volume) {
    auto *item =
        add(parent, volume.name,
            volume.usb() ? "drive-removable-media-usb" : "drive-harddisk",
            volume.mounted() ? QUrl::fromLocalFile(volume.mount) : QUrl());
    item->setData(0, VolumeRole, QVariant::fromValue(volume));
    item->setToolTip(0, volume.device + "\n" +
                            (volume.mounted() ? volume.mount : "Not mounted"));
    if (!volume.mounted())
      item->setForeground(0, palette().color(QPalette::PlaceholderText));
    if (volume.device == selectedDrive)
      places->setCurrentItem(item);
  };
  for (const auto &volume : drives->volumes)
    if (volume.mounted())
      addVolume(pc, volume);
  quickRoot = add(nullptr, "Quick access", "bookmarks", {});
  quickRoot->setData(0, SectionRole, "quickAccess");
  auto list = preferences.places();
  for (int i = 0; i < list.size(); ++i) {
    const auto &entry = list[i];
    auto *item = add(quickRoot, entry["name"].toString(),
                     entry.value("icon", "folder").toString(),
                     QUrl(entry["url"].toString()));
    item->setData(0, PinRole, i);
    item->setFlags(item->flags() | Qt::ItemIsDragEnabled |
                   Qt::ItemIsDropEnabled);
  }
  add(nullptr, "Network", "network-workgroup", QUrl("remote:/"));
  add(nullptr, "Trash", "user-trash", QUrl("trash:/"));
  QTreeWidgetItem *unmounted = nullptr;
  for (const auto &volume : drives->volumes)
    if (!volume.mounted()) {
      if (!unmounted) {
        unmounted = add(nullptr, "Unmounted drives", "drive-harddisk", {});
        unmounted->setData(0, SectionRole, "unmounted");
      }
      addVolume(unmounted, volume);
    }
  pc->setExpanded(expanded);
  quickRoot->setExpanded(quickExpanded);
  if (unmounted)
    unmounted->setExpanded(unmountedExpanded);
  places->verticalScrollBar()->setValue(scroll);
}
void FilesWindow::pin(const QUrl &url) {
  if (!url.isValid() || Fusion::isComputer(url))
    return;
  auto list = preferences.places();
  for (const auto &entry : list)
    if (QUrl(entry["url"].toString()).adjusted(QUrl::StripTrailingSlash) ==
        url.adjusted(QUrl::StripTrailingSlash))
      return;
  QUrl safe = url;
  safe.setPassword({});
  list.append({{"name", Fusion::title(safe)},
               {"url", safe.toString()},
               {"icon", safe.isLocalFile() ? "folder" : "folder-remote"}});
  preferences.setPlaces(list);
  rebuildPlaces();
}
void FilesWindow::placeMenu(const QPoint &point) {
  auto *item = places->itemAt(point);
  if (!item)
    return;
  if (item->data(0, VolumeRole).isValid()) {
    drives->menu(item->data(0, VolumeRole).value<Volume>(),
                 places->viewport()->mapToGlobal(point), this);
    return;
  }
  QMenu menu(this);
  const QUrl url(item->data(0, UrlRole).toString());
  if (url.scheme() == "trash")
    menu.addAction(Fusion::icon("user-trash"), "Empty Trash…", this, [this] { Fusion::emptyTrash(this); });
  if (url.isValid())
    menu.addAction("Open in new tab", this,
                   [this, url] { openLocation(url, true); });
  if (item->data(0, PinRole).isValid()) {
    const int index = item->data(0, PinRole).toInt();
    menu.addAction("Rename shortcut…", this, [this, index] {
      auto list = preferences.places();
      bool ok;
      auto name = QInputDialog::getText(this, "Rename shortcut",
                                        "Name:", QLineEdit::Normal,
                                        list[index]["name"].toString(), &ok);
      if (ok && !name.trimmed().isEmpty()) {
        list[index]["name"] = name;
        preferences.setPlaces(list);
        rebuildPlaces();
      }
    });
    menu.addAction("Unpin from quick access", this, [this, index] {
      auto list = preferences.places();
      list.removeAt(index);
      preferences.setPlaces(list);
      rebuildPlaces();
    });
  }
  menu.addSeparator();
  menu.addAction("Add folder shortcut…", this, [this] {
    const auto folder = QFileDialog::getExistingDirectory(this, "Pin a folder");
    if (!folder.isEmpty())
      pin(QUrl::fromLocalFile(folder));
  });
  menu.exec(places->viewport()->mapToGlobal(point));
}
void FilesWindow::bind(const QString &id, const QString &key) {
  auto *action = new QAction(this);
  action->setObjectName(id);
  action->setShortcut(QKeySequence(key));
  addAction(action);
  shortcuts[id] = action;
  connect(action, &QAction::triggered, this, [this, id] {
    // Only keyboard shortcuts defer to a focused text editor. An explicit
    // context-menu action must work even when the address bar retains focus.
    if (isTextEditing() && QStringList{"trash", "delete", "open", "copy", "cut", "paste", "selectAll", "undo"}.contains(id))
      return;
    if (id == "open" && browser() && !Fusion::isComputer(browser()->location())) {
      for (const auto &item : browser()->selectedItems()) openItem(item);
      return;
    }
    runAction(id);
  });
}
void FilesWindow::track(KJob *job) {
  if (!job)
    return;
  KJobWidgets::setWindow(job, this);
  // Keep copies alive after the last browser window closes. The existing
  // Fusion JobView service continues to show progress and cancellation.
  auto locker = std::make_shared<QEventLoopLocker>();
  connect(job, &KJob::result, qApp, [locker](KJob *) {});
  connect(job, &KJob::result, this, [this](KJob *result) {
    if (result->error() && result->error() != KIO::ERR_USER_CANCELED) {
      message(result->errorString());
      if (qobject_cast<Fusion::RemovalJob *>(result) || result->property("fusionTransfer").toBool()) {
        auto *error = new QMessageBox(QMessageBox::Warning, "File operation could not finish",
                                      result->errorString(), QMessageBox::Ok, this);
        error->setAttribute(Qt::WA_DeleteOnClose);
        error->open();
      }
    }
    emit operationFinished(result->error());
  });
  connect(job, &KJob::infoMessage, this, [this](KJob *, const QString &text) { message(text); });
}
void FilesWindow::openItem(const KFileItem &item, bool newTab) {
  if (item.isNull())
    return;
  if (item.isDir()) {
    openLocation(item.url(), newTab);
    return;
  }
  if (item.url().isLocalFile() && QFileInfo(item.url().toLocalFile()).isExecutable() &&
      !Fusion::executionCommand(item.url()).isEmpty()) {
    execute(item.url());
    return;
  }
  openAssociated({item});
}
void FilesWindow::execute(const QUrl &url) {
  auto command = Fusion::executionCommand(url);
  if (command.isEmpty()) return;
  const auto program = command.takeFirst();
  auto *job = new KIO::CommandLauncherJob(program, command);
  job->setWorkingDirectory(QFileInfo(url.toLocalFile()).absolutePath());
  job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, this));
  track(job);
  job->start();
}
void FilesWindow::openAssociated(const KFileItemList &items) {
  for (const auto &item : items) {
    if (item.isDir()) { openLocation(item.url()); continue; }
    const auto preferred = KApplicationTrader::preferredService(item.mimetype());
    if (!preferred) { chooseApplication({item}); continue; }
    track(Fusion::launchApplication({{"app", preferred->storageId()}, {"mime", item.mimetype()},
                                    {"urls", QJsonArray{item.url().toString(QUrl::FullyEncoded)}}}, this));
  }
}
void FilesWindow::chooseApplication(const KFileItemList &items) {
  if (items.isEmpty()) return;
  Fusion::ApplicationDialog dialog(items, this);
  if (dialog.exec() != QDialog::Accepted) return;
  auto request = dialog.request();
  QJsonArray urls;
  for (const auto &item : items) urls.append(item.url().toString(QUrl::FullyEncoded));
  request["urls"] = urls;
  track(Fusion::launchApplication(request, this));
}
void FilesWindow::runAction(const QString &id) {
  auto *tab = browser();
  if (!tab)
    return;
  const auto items = tab->selectedItems();
  const auto urls = tab->selectedUrls();
  const auto location = tab->location();
  if (id == "address" || id == "addressAlt") {
    tab->editAddress();
    return;
  }
  if (id == "newTab") {
    addTab(Fusion::computerUrl());
    return;
  }
  if (id == "closeTab") {
    emit tabs->tabCloseRequested(tabs->currentIndex());
    return;
  }
  if (id == "nextTab" || id == "previousTab") {
    tabs->setCurrentIndex(
        (tabs->currentIndex() + tabs->count() + (id == "nextTab" ? 1 : -1)) %
        tabs->count());
    return;
  }
  if (id == "newWindow") {
    auto *window = new FilesWindow(location);
    window->show();
    return;
  }
  if (id == "back") {
    tab->navigator->goBack();
    return;
  }
  if (id == "forward") {
    tab->navigator->goForward();
    return;
  }
  if (id == "up") {
    tab->navigator->goUp();
    return;
  }
  if (id == "refresh") {
    tab->refresh();
    return;
  }
  if (id == "hidden") {
    hiddenAction->toggle();
    return;
  }
  if (id == "preview") {
    previewAction->trigger();
    return;
  }
  if (id == "filter") {
    tab->filter->setFocus();
    tab->filter->selectAll();
    return;
  }
  if (id == "connect") {
    bool ok;
    const auto address = QInputDialog::getText(
        this, "Connect to server",
        "Address (smb://server/share or sftp://host/path):", QLineEdit::Normal,
        "smb://", &ok);
    if (ok && !address.isEmpty())
      openLocation(Fusion::userUrl(address));
    return;
  }
  if (id == "copy" || id == "cut" || id == "paste") {
    if (places->hasFocus() && places->currentItem() &&
        places->currentItem()->data(0, VolumeRole).isValid()) {
      volumeAction(places->currentItem()->data(0, VolumeRole).value<Volume>(),
                   id);
      return;
    }
    if (Fusion::isComputer(location)) {
      const auto volume = tab->selectedVolume();
      if (!volume.device.isEmpty())
        volumeAction(volume, id);
      else if (id == "paste")
        computerMenu(QCursor::pos());
      return;
    }
  }
  if (id == "selectAll") {
    tab->selectAll();
    return;
  }
  if (id == "undo") {
    KIO::FileUndoManager::self()->uiInterface()->setParentWidget(this);
    KIO::FileUndoManager::self()->undo();
    return;
  }
  if (id == "execute") {
    if (urls.size() == 1) execute(urls.first());
    return;
  }
  if (id == "open" || id == "openTab") {
    if (Fusion::isComputer(location) && !tab->selectedVolume().device.isEmpty())
      drives->operate(tab->selectedVolume(), "open", this);
    else if (id == "open")
      openAssociated(items);
    else
      for (const auto &item : items)
        openItem(item, id == "openTab");
    return;
  }
  if (id == "copyPath") {
    QStringList paths;
    for (const auto &url : urls)
      paths << Fusion::displayPath(url);
    if (paths.isEmpty())
      paths << Fusion::displayPath(location);
    QApplication::clipboard()->setText(paths.join('\n'));
    return;
  }
  if (id == "pin") {
    if (items.isEmpty())
      pin(location);
    else
      for (const auto &item : items)
        if (item.isDir())
          pin(item.url());
    return;
  }
  if (id == "properties") {
    if (places->hasFocus() && places->currentItem() &&
        places->currentItem()->data(0, VolumeRole).isValid()) {
      drives->showProperties(
          places->currentItem()->data(0, VolumeRole).value<Volume>(), this);
      return;
    }
    if (Fusion::isComputer(location)) {
      const auto volume = tab->selectedVolume();
      if (!volume.device.isEmpty())
        drives->showProperties(volume, this);
      return;
    }
    auto *dialog = items.isEmpty() ? new KPropertiesDialog(location, this)
                                   : new KPropertiesDialog(items, this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->show();
    return;
  }
  if (id == "compress" || id == "extract") {
    archive(id == "extract");
    return;
  }
  if (id == "openWith") {
    chooseApplication(items);
    return;
  }
  if (id == "cut" || id == "copy") {
    if (urls.isEmpty())
      return;
    auto *mime = new QMimeData;
    mime->setUrls(urls);
    KIO::setClipboardDataCut(mime, id == "cut");
    QApplication::clipboard()->setMimeData(mime);
    return;
  }
  if (Fusion::isComputer(location))
    return;
  if (id == "paste") {
    track(Fusion::pasteFiles(location, this));
    return;
  }
  if (id == "rename") {
    if (items.isEmpty())
      return;
    if (items.size() == 1) { tab->renameSelected(); return; }
    auto *dialog = new KIO::RenameFileDialog(items, this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    connect(dialog, &KIO::RenameFileDialog::renamingFinished, this,
            [tab = QPointer<Browser>(tab)](const QList<QUrl> &urls) {
              if (tab && !urls.isEmpty())
                tab->selectUrl(urls.first());
            });
    dialog->show();
    return;
  }
  if (id == "newFolder") {
    bool ok;
    const QString name = QInputDialog::getText(
        this, "New folder", "Folder name:", QLineEdit::Normal, "New folder",
        &ok);
    if (!ok)
      return;
    if (!Fusion::validName(name)) {
      message("Choose a name without /, and different from . or ..");
      return;
    }
    QUrl dest = location;
    dest.setPath(location.path() + (location.path().endsWith('/') ? "" : "/") +
                 name);
    auto *job = KIO::mkdir(dest);
    KIO::FileUndoManager::self()->recordJob(KIO::FileUndoManager::Mkdir, {},
                                            dest, job);
    track(job);
    connect(job, &KJob::result, this,
            [tab = QPointer<Browser>(tab), dest](KJob *job) {
              if (!job->error() && tab)
                tab->selectUrl(dest);
            });
    return;
  }
  if (id == "trash" || id == "delete") {
    if (urls.isEmpty())
      return;
    const bool permanent = id == "delete" || location.scheme() == "trash";
    if (permanent) {
      if (QMessageBox::warning(this, "Delete permanently",
                               QString("Permanently delete %1 selected "
                                       "item(s)?\nThis cannot be undone.")
                                   .arg(urls.size()),
                               QMessageBox::Yes | QMessageBox::Cancel,
                               QMessageBox::Cancel) != QMessageBox::Yes)
        return;
    }
    QList<Fusion::TrashIcon> artwork;
    if (!permanent && preferences.settings.value("trashAnimation", true).toBool()) {
      for (const auto &item : items) {
        const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(item.url()));
        const auto rect = tab->view()->visualRect(index);
        if (!rect.intersects(tab->view()->viewport()->rect())) continue;
        const int size = qBound(22, tab->view()->iconSize().width(), 80);
        auto icon = qvariant_cast<QIcon>(index.data(Qt::DecorationRole));
        if (icon.isNull()) icon = Fusion::icon(item.iconName());
        const auto center = mapFromGlobal(tab->view()->viewport()->mapToGlobal(rect.topLeft() + QPoint(rect.width()/2, size/2 + 8)));
        artwork.append({item.url(), icon.pixmap(size, size), QRectF(center.x()-size/2, center.y()-size/2, size, size)});
        if (artwork.size() == 8) break;
      }
    }
    auto *job = new Fusion::RemovalJob(items, permanent ? "delete" : "trash", this);
    connect(job, &Fusion::RemovalJob::removed, this, [this, artwork, location](const QList<QUrl> &removed) {
      if (!browser() || browser()->location() != location) return;
      QList<Fusion::TrashIcon> succeeded;
      for (const auto &icon : artwork) if (removed.contains(icon.url)) succeeded << icon;
      QPoint target(places->viewport()->width()/2, places->viewport()->height()-24);
      for (int i = 0; i < places->topLevelItemCount(); ++i) {
        auto *item = places->topLevelItem(i);
        if (QUrl(item->data(0, UrlRole).toString()).scheme() == "trash") {
          const auto rect = places->visualItemRect(item);
          if (rect.intersects(places->viewport()->rect())) target = QPoint(rect.left()+20, rect.center().y());
        }
      }
      Fusion::animateTrash(this, succeeded, mapFromGlobal(places->viewport()->mapToGlobal(target)));
      browser()->refresh();
    });
    track(job);
    return;
  }
  if (id == "restore") {
    if (!urls.isEmpty()) {
      auto *job = new Fusion::RemovalJob(items, QString("restore"), this);
      connect(job, &Fusion::RemovalJob::removed, this, [tab = QPointer<Browser>(tab)] { if (tab) tab->refresh(); });
      track(job);
    }
    return;
  }
  if (id == "terminal") {
    QUrl directory =
        items.size() == 1 && items[0].isDir() ? items[0].url() : location;
    if (!directory.isLocalFile()) {
      message("Open terminal here is available for local folders.");
      return;
    }
    if (!QProcess::startDetached("kitty",
                                 {"--directory", directory.toLocalFile()}))
      message("Kitty could not be started.");
    return;
  }
}
void FilesWindow::archive(bool extract) {
  const auto urls = browser()->selectedUrls();
  if (urls.isEmpty())
    return;
  if (QStandardPaths::findExecutable("ark").isEmpty()) {
    message("Ark is required for archive actions. Install Ark and try again.");
    return;
  }
  QStringList args = extract
                         ? QStringList{"--batch", "--dialog", "--autosubfolder"}
                         : QStringList{"--add", "--dialog"};
  if (extract && browser()->location().isLocalFile())
    args << "--destination" << browser()->location().toLocalFile();
  args << "--";
  for (const auto &url : urls)
    args << (url.isLocalFile() ? url.toLocalFile() : url.toString());
  if (!QProcess::startDetached("ark", args))
    message("Ark could not be started.");
}
void FilesWindow::addArkActions(QMenu *menu, const KFileItemList &items, bool compress, bool extract,
                                const std::function<bool()> &guard) {
  Fusion::addArkActions(menu, items, compress, extract, this, arkPlugins, browser()->location(),
                       [this](const QString &text) { message(text); }, guard);
}
void FilesWindow::volumeAction(const Volume &volume, const QString &id) {
  if (id == "cut") {
    message("Open the drive and select files to cut. A mounted drive itself "
            "cannot be moved.");
    return;
  }
  const auto location = drives->mountedLocation(volume);
  if (!location.isValid() || location.isEmpty())
    return;
  if (id == "copy") {
    auto *data = new QMimeData;
    data->setUrls({location});
    KIO::setClipboardDataCut(data, false);
    QApplication::clipboard()->setMimeData(data);
  } else if (id == "paste") {
    if (volume.readOnly) {
      message("This drive is read only.");
      return;
    }
    const auto *data = QApplication::clipboard()->mimeData();
    if (KIO::canPasteMimeData(data))
      track(Fusion::pasteFiles(location, this));
  }
}
void FilesWindow::addVolumeActions(QMenu *menu, const Volume &volume) {
  menu->addSeparator();
  QHash<QString, QVariantMap> configured;
  for (const auto &entry : preferences.menu())
    configured.insert(entry["id"].toString(), entry);
  for (const auto &entry : QList<QStringList>{
           {"cut", "Cut", "edit-cut", "Ctrl+X"},
           {"copy", "Copy", "edit-copy", "Ctrl+C"},
           {"paste", "Paste into drive", "edit-paste", "Ctrl+V"}}) {
    const auto settings = configured.value(entry[0]);
    if (!settings.value("enabled", true).toBool())
      continue;
    QString name = settings.value("name", entry[1]).toString();
    if (entry[0] == "paste" && name == "Paste")
      name = "Paste into drive";
    auto *action = menu->addAction(
        Fusion::icon(settings.value("icon", entry[2]).toString()), name);
    action->setObjectName(entry[0]);
    action->setShortcut(QKeySequence(entry[3]));
    action->setEnabled(
        volume.mounted() && entry[0] != "cut" &&
        (entry[0] != "paste" ||
         (!volume.readOnly &&
          KIO::canPasteMimeData(QApplication::clipboard()->mimeData()))));
    if (entry[0] == "cut")
      action->setToolTip("Open the drive to cut files or folders inside it.");
    connect(action, &QAction::triggered, this,
            [this, volume, id = entry[0]] { volumeAction(volume, id); });
  }
  if (volume.mounted()) {
    const KFileItemList items{KFileItem(QUrl::fromLocalFile(volume.mount),
                                        "inode/directory", S_IFDIR)};
    addArkActions(
        menu, items,
        configured.value("compress").value("enabled", true).toBool(), false,
        [this, volume] { return !drives->mountedLocation(volume).isEmpty(); });
  }
}
void FilesWindow::computerMenu(const QPoint &point) {
  QMenu menu(this);
  menu.setObjectName("computerContextMenu");
  auto *paste = menu.addMenu(Fusion::icon("edit-paste"), "Paste into…");
  paste->setEnabled(
      KIO::canPasteMimeData(QApplication::clipboard()->mimeData()));
  for (const auto &volume : drives->volumes)
    if (volume.mounted() && !volume.readOnly)
      paste->addAction(Fusion::icon(volume.usb() ? "drive-removable-media-usb"
                                                 : "drive-harddisk"),
                       volume.name + " · " + volume.mount, this,
                       [this, volume] { volumeAction(volume, "paste"); });
  if (paste->isEmpty())
    paste->setEnabled(false);
  menu.addAction(Fusion::icon("view-refresh"), "Refresh", this,
                 [this] { drives->refresh(); });
  menu.exec(point);
}
void FilesWindow::fileMenu(const QPoint &point) {
  const auto items = browser()->selectedItems();
  const auto location = browser()->location();
  QMenu menu(this);
  menu.setObjectName("fileContextMenu");
  if (location.scheme() == "trash")
    menu.addAction(Fusion::icon("user-trash"), "Empty Trash…", this, [this] { Fusion::emptyTrash(this); });
  bool compress = false, extract = false, arkAdded = false;
  for (const auto &entry : preferences.menu()) {
    if (entry["id"] == "compress")
      compress = entry.value("enabled", true).toBool();
    if (entry["id"] == "extract")
      extract = entry.value("enabled", true).toBool();
  }
  KService::Ptr preferred;
  if (!items.isEmpty() && !items.first().isDir()) {
    const auto type = items.first().mimetype();
    if (std::all_of(items.cbegin(), items.cend(), [&](const KFileItem &item) {
          return !item.isDir() && item.mimetype() == type;
        }))
      preferred = KApplicationTrader::preferredService(type);
  }
  if (location.scheme() == "trash" && !items.isEmpty())
    menu.addAction(Fusion::icon("edit-undo"), "Restore", this,
                   [this] { runAction("restore"); });
  for (const auto &entry : preferences.menu()) {
    if (!entry.value("enabled", true).toBool())
      continue;
    const QString id = entry["id"].toString();
    if (id == "execute" &&
        (items.size() != 1 || Fusion::executionCommand(items.first().url()).isEmpty()))
      continue;
    if (id == "compress" || id == "extract") {
      if (!arkAdded && !items.isEmpty()) {
        addArkActions(&menu, items, compress, extract);
        arkAdded = true;
      }
      continue;
    }
    if (id == "openTab" && !items.isEmpty() &&
        !std::all_of(items.cbegin(), items.cend(),
                     [](const KFileItem &item) { return item.isDir(); }))
      continue;
    if (items.isEmpty() &&
        QStringList{"open", "openTab", "openWith", "cut", "copy", "rename",
                    "trash", "delete", "compress", "extract"}
            .contains(id))
      continue;
    if (id == "pin" && !items.isEmpty() &&
        !std::all_of(items.begin(), items.end(),
                     [](const KFileItem &item) { return item.isDir(); }))
      continue;
    QString label = entry["name"].toString(), icon = entry["icon"].toString();
    if (id == "trash" && location.scheme() == "trash") label = "Delete permanently…";
    if (id == "open" && preferred && label == "Open") {
      label = "Open with " + QString(preferred->name()).replace('&', "&&");
      if (icon == "document-open" && !preferred->icon().isEmpty())
        icon = preferred->icon();
    }
    auto *action = menu.addAction(Fusion::icon(icon), label);
    action->setObjectName(id);
    if (shortcuts.contains(id))
      action->setShortcut(shortcuts[id]->shortcut());
    if (id == "paste")
      action->setEnabled(
          KIO::canPasteMimeData(QApplication::clipboard()->mimeData()));
    connect(action, &QAction::triggered, this, [this, entry, id] {
      if (id.startsWith("custom:"))
        customAction(entry);
      else
        runAction(id);
    });
  }
  menu.addSeparator();
  menu.addAction("Customize this menu…", this, &FilesWindow::customizeMenu);
  menu.exec(point);
}
void FilesWindow::customAction(const QVariantMap &entry) {
  const auto urls = browser()->selectedUrls().isEmpty()
                        ? QList<QUrl>{browser()->location()}
                        : browser()->selectedUrls();
  auto parts = Fusion::expandCommand(entry["command"].toString(), urls);
  if (parts.isEmpty()) {
    message("This action needs local files, or has an invalid command. %F and "
            "%U must be separate arguments.");
    return;
  }
  const QString program = parts.takeFirst();
  const QString working = browser()->location().isLocalFile()
                              ? browser()->location().toLocalFile()
                              : QDir::homePath();
  if (!QProcess::startDetached(program, parts, working))
    message("The custom action could not be started.");
}
void FilesWindow::customizeMenu() {
  Fusion::customizeMenu(preferences, this);
}
void FilesWindow::configure() {
  QDialog dialog(this);
  dialog.setObjectName("filesConfiguration");
  dialog.setWindowTitle("Configure Fusion Files");
  dialog.resize(530, 420);
  auto *layout = new QVBoxLayout(&dialog);
  layout->setContentsMargins(24, 22, 24, 20);
  layout->setSpacing(14);
  auto *heading = new QLabel("Your files, your way");
  heading->setObjectName("settingsHeading");
  layout->addWidget(heading);
  auto *intro = new QLabel("Choose what appears while you browse. These settings are saved for your desktop.");
  intro->setWordWrap(true);
  layout->addWidget(intro);
  auto *display = new QGroupBox("Browsing");
  auto *displayLayout = new QVBoxLayout(display);
  auto *pane = new QCheckBox("Show the preview pane");
  pane->setObjectName("configurePreview");
  pane->setChecked(previewAction->isChecked());
  displayLayout->addWidget(pane);
  auto *thumbnails = new QCheckBox("Show picture thumbnails on file icons");
  thumbnails->setObjectName("configureThumbnails");
  thumbnails->setChecked(preferences.settings.value("thumbnails", true).toBool());
  displayLayout->addWidget(thumbnails);
  auto *hint = new QLabel("Local pictures only. Remote folders keep file-type icons.");
  hint->setObjectName("muted");
  displayLayout->addWidget(hint);
  auto *hidden = new QCheckBox("Show hidden files and folders");
  hidden->setChecked(hiddenAction->isChecked());
  displayLayout->addWidget(hidden);
  layout->addWidget(display);
  auto *behavior = new QGroupBox("File actions");
  auto *behaviorLayout = new QVBoxLayout(behavior);
  auto *animation = new QCheckBox("Animate files moving to Trash");
  animation->setObjectName("configureTrashAnimation");
  animation->setChecked(preferences.settings.value("trashAnimation", true).toBool());
  behaviorLayout->addWidget(animation);
  auto *menu = new QPushButton("Customize context menu…");
  connect(menu, &QPushButton::clicked, this, &FilesWindow::customizeMenu);
  behaviorLayout->addWidget(menu);
  layout->addWidget(behavior);
  layout->addStretch();
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
  layout->addWidget(buttons);
  connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  if (dialog.exec() != QDialog::Accepted) return;
  preferences.settings.setValue("thumbnails", thumbnails->isChecked());
  preferences.settings.setValue("trashAnimation", animation->isChecked());
  if (pane->isChecked() != previewAction->isChecked()) previewAction->trigger();
  hiddenAction->setChecked(hidden->isChecked());
  for (int i = 0; i < tabs->count(); ++i)
    static_cast<Browser *>(tabs->widget(i))->setThumbnails(thumbnails->isChecked());
  preferences.settings.sync();
}
void FilesWindow::showShortcuts() {
  QMessageBox::information(
      this, "Keyboard shortcuts",
      "F2 — Rename\nCtrl+C / Ctrl+X / Ctrl+V — Copy / cut / paste\nDelete — "
      "Move to Trash\nShift+Delete — Delete permanently (confirmation)\nCtrl+Z "
      "— Undo\nCtrl+Shift+N — New folder\nCtrl+A — Select all\nCtrl+L or Alt+D "
      "— Edit full path\nAlt+Left / Right / Up — Back / forward / parent\nF5 — "
      "Refresh\nAlt+. / Ctrl+H — Hidden files\nAlt+P — Preview pane\nCtrl+F — Filter "
      "current folder\nCtrl+Shift+C — Copy full path\nCtrl+T / Ctrl+W — New / "
      "close tab\nCtrl+Tab / Ctrl+Shift+Tab — Switch tabs\nCtrl+N — New "
      "window\nAlt+Enter — Properties");
}
void FilesWindow::reloadTheme() {
  if (theme.state() != QProcess::NotRunning) {
    themeDebounce.start();
    return;
  }
  theme.start("python3", {Fusion::root() + "/file_manager/appearance.py"});
}
void FilesWindow::message(const QString &text) {
  statusBar()->showMessage(text, 15000);
  if (browser()) {
    browser()->notice->setText(text);
    browser()->notice->show();
  }
}
void FilesWindow::closeEvent(QCloseEvent *event) {
  if (browser())
    browser()->saveView();
  if (geometryKey == "external/geometry")
    preferences.settings.setValue("external/size", size());
  else if (geometryKey != "geometry")
    preferences.settings.setValue(geometryKey, saveGeometry());
  preferences.settings.setValue(splitterKey, splitter->saveState());
  preferences.settings.sync();
  QMainWindow::closeEvent(event);
}

void FilesWindow::preparePicker() {
  tabs->setTabsClosable(false);
  tabs->tabBar()->setTabButton(0, QTabBar::RightSide, nullptr);
  if (auto *button = findChild<QToolButton *>("newTabButton")) button->hide();
  for (const auto &id : {"newTab", "newWindow", "closeTab", "nextTab", "previousTab"})
    if (shortcuts.contains(id)) shortcuts[id]->setEnabled(false);
  if (auto *menu = findChild<QMenu *>("fileOptionsMenu"))
    for (auto *action : menu->actions())
      if (action->text() == "New tab" || action->text() == "New window") action->setVisible(false);
}
