#include "window.h"
#include "../theme/file_preview.hpp"
#include <KApplicationTrader>
#include <KFileItemActions>
#include <KIO/ApplicationLauncherJob>
#include <KIO/CopyJob>
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
#include <KOpenWithDialog>
#include <KPropertiesDialog>
#include <KService>
#include <memory>

namespace {
enum PlaceRole { UrlRole = Qt::UserRole, PinRole, VolumeRole };
class PlacesTree : public QTreeWidget {
public:
  using QTreeWidget::QTreeWidget;
  std::function<void(const QUrl &)> pin;
  std::function<void(int, int)> reorder;

protected:
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
    if (event->mimeData()->hasUrls())
      event->acceptProposedAction();
  }
  void dragMoveEvent(QDragMoveEvent *event) override {
    if (event->mimeData()->hasUrls())
      event->acceptProposedAction();
  }
  void dropEvent(QDropEvent *event) override {
    if (event->source() == this &&
        event->mimeData()->hasFormat("application/x-fusion-place")) {
      auto *item = itemAt(event->position().toPoint());
      if (item && item->data(0, PinRole).isValid())
        reorder(event->mimeData()->data("application/x-fusion-place").toInt(),
                item->data(0, PinRole).toInt());
    } else
      for (const auto &url : event->mimeData()->urls())
        if (url.isLocalFile() && QFileInfo(url.toLocalFile()).isDir())
          pin(url);
    event->acceptProposedAction();
  }
};
bool isTextEditing() {
  auto *focus = QApplication::focusWidget();
  return qobject_cast<QLineEdit *>(focus) || qobject_cast<QTextEdit *>(focus) ||
         qobject_cast<QPlainTextEdit *>(focus);
}
} // namespace
FilesWindow::FilesWindow(const QUrl &initial, bool scanDrives,
                         const QString &settingsPath)
    : preferences(settingsPath) {
  setObjectName("fusionFiles");
  setAttribute(Qt::WA_DeleteOnClose);
  setWindowTitle("Fusion Files");
  setWindowIcon(Fusion::icon("fusion-computer"));
  resize(1180, 760);
  setMinimumSize(760, 450);
  if (preferences.settings.contains("geometry"))
    restoreGeometry(preferences.settings.value("geometry").toByteArray());
  drives = new Drives(this, scanDrives);
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
  auto *folder =
      tool("folder-new", "New folder", [this] { runAction("newFolder"); });
  folder->setToolTip("New folder · Ctrl+Shift+N");
  views = new QComboBox;
  views->setObjectName("viewMode");
  views->addItems(
      {"Small icons", "Medium icons", "Large icons", "List", "Details"});
  views->setCurrentIndex(preferences.settings.value("view", 2).toInt());
  toolbar->addWidget(views);
  previewAction = tool("view-preview", "Preview pane", [this] {
    previewStack->setVisible(previewAction->isChecked());
    preferences.settings.setValue("preview", previewAction->isChecked());
    updatePreview();
  });
  previewAction->setCheckable(true);
  previewAction->setChecked(
      preferences.settings.value("preview", false).toBool());
  auto *menuButton = new QToolButton;
  menuButton->setProperty("fusionIcon", "application-menu");
  menuButton->setIcon(Fusion::icon("application-menu"));
  menuButton->setToolTip("File manager options");
  menuButton->setPopupMode(QToolButton::InstantPopup);
  auto *menu = new QMenu(menuButton);
  menuButton->setMenu(menu);
  toolbar->addWidget(menuButton);
  menu->addAction("New tab", this, [this] { runAction("newTab"); });
  menu->addAction("New window", this, [this] { runAction("newWindow"); });
  menu->addAction("Open location…", this, [this] { browser()->editAddress(); });
  menu->addAction("Connect to server…", this, [this] { runAction("connect"); });
  menu->addSeparator();
  hiddenAction = menu->addAction("Show hidden files");
  hiddenAction->setCheckable(true);
  hiddenAction->setChecked(
      preferences.settings.value("hidden", false).toBool());
  connect(hiddenAction, &QAction::toggled, this, [this](bool value) {
    preferences.settings.setValue("hidden", value);
    for (int i = 0; i < tabs->count(); ++i)
      static_cast<Browser *>(tabs->widget(i))->setHidden(value);
  });
  menu->addAction("Customize context menu…", this, &FilesWindow::customizeMenu);
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
  tree->reorder = [this](int from, int to) {
    auto list = preferences.places();
    if (from >= 0 && to >= 0 && from < list.size() && to < list.size()) {
      list.move(from, to);
      preferences.setPlaces(list);
      rebuildPlaces();
    }
  };
  tabs = new QTabWidget;
  tabs->setDocumentMode(true);
  tabs->setTabsClosable(true);
  tabs->setMovable(true);
  tabs->setTabBarAutoHide(false);
  splitter->addWidget(tabs);
  auto *newTab = new QToolButton;
  newTab->setText("+");
  newTab->setToolTip("New tab · Ctrl+T");
  tabs->setCornerWidget(newTab);
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
  if (preferences.settings.contains("splitter"))
    splitter->restoreState(
        preferences.settings.value("splitter").toByteArray());
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
  connect(views, &QComboBox::currentIndexChanged, this, [this](int index) {
    if (browser())
      browser()->setView(index);
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
                          {"hidden", "Ctrl+H"},
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
            qApp->setFont(QFont(value["font"].toString("Noto Sans"), 10));
            QIcon::setThemeName(value["iconTheme"].toString());
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
  setWindowTitle(Fusion::title(url) + " — Fusion Files");
  QSignalBlocker blocker(views);
  views->setCurrentIndex(browser()->viewMode);
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
  bool expanded = true, quickExpanded = true;
  if (places->topLevelItemCount()) {
    expanded = places->topLevelItem(0)->isExpanded();
    if (places->topLevelItemCount() > 1)
      quickExpanded = places->topLevelItem(1)->isExpanded();
  }
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
  pc->setExpanded(expanded);
  for (const auto &volume : drives->volumes) {
    auto *item =
        add(pc, volume.name,
            volume.removable ? "drive-removable-media-usb" : "drive-harddisk",
            volume.mounted() ? QUrl::fromLocalFile(volume.mount) : QUrl());
    item->setData(0, VolumeRole, QVariant::fromValue(volume));
    item->setToolTip(0, volume.device + "\n" +
                            (volume.mounted() ? volume.mount : "Not mounted"));
    if (!volume.mounted())
      item->setForeground(0, palette().color(QPalette::PlaceholderText));
  }
  quickRoot = add(nullptr, "Quick access", "bookmarks", {});
  quickRoot->setExpanded(quickExpanded);
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
  connect(action, &QAction::triggered, this, [this, id] { runAction(id); });
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
    if (result->error() && result->error() != KIO::ERR_USER_CANCELED)
      message(result->errorString());
    emit operationFinished(result->error());
  });
}
void FilesWindow::openItem(const KFileItem &item, bool newTab) {
  if (item.isNull())
    return;
  if (item.isDir()) {
    openLocation(item.url(), newTab);
    return;
  }
  auto *job = new KIO::OpenUrlJob(item.url(), item.mimetype());
  job->setUiDelegate(KIO::createDefaultJobUiDelegate(
      KJobUiDelegate::AutoHandlingEnabled, this));
  job->setRunExecutables(false);
  job->setShowOpenOrExecuteDialog(true);
  track(job);
  job->start();
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
  if (isTextEditing() &&
      (id == "trash" || id == "delete" || id == "open" || id == "copy" ||
       id == "cut" || id == "paste" || id == "selectAll" || id == "undo"))
    return;
  if (id == "selectAll") {
    tab->selectAll();
    return;
  }
  if (id == "undo") {
    KIO::FileUndoManager::self()->uiInterface()->setParentWidget(this);
    KIO::FileUndoManager::self()->undo();
    return;
  }
  if (id == "open" || id == "openTab") {
    if (Fusion::isComputer(location) && tab->cards->currentItem())
      drives->operate(
          tab->cards->currentItem()->data(Qt::UserRole).value<Volume>(), "open",
          this);
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
    if (urls.isEmpty())
      return;
    KOpenWithDialog dialog(urls, this);
    dialog.setSaveNewApplications(true);
    if (dialog.exec() == QDialog::Accepted && dialog.service()) {
      auto *job = new KIO::ApplicationLauncherJob(dialog.service());
      job->setUrls(urls);
      job->setUiDelegate(KIO::createDefaultJobUiDelegate(
          KJobUiDelegate::AutoHandlingEnabled, this));
      track(job);
      job->start();
    }
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
    track(KIO::paste(QApplication::clipboard()->mimeData(), location));
    return;
  }
  if (id == "rename") {
    if (items.isEmpty())
      return;
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
    if (id == "delete") {
      if (QMessageBox::warning(this, "Delete permanently",
                               QString("Permanently delete %1 selected "
                                       "item(s)?\nThis cannot be undone.")
                                   .arg(urls.size()),
                               QMessageBox::Yes | QMessageBox::Cancel,
                               QMessageBox::Cancel) != QMessageBox::Yes)
        return;
      track(KIO::del(urls));
    } else {
      auto *job = KIO::trash(urls);
      KIO::FileUndoManager::self()->recordCopyJob(job);
      track(job);
    }
    return;
  }
  if (id == "restore") {
    if (!urls.isEmpty())
      track(KIO::restoreFromTrash(urls));
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
void FilesWindow::fileMenu(const QPoint &point) {
  const auto items = browser()->selectedItems();
  const auto location = browser()->location();
  QMenu menu(this);
  if (location.scheme() == "trash" && !items.isEmpty())
    menu.addAction(Fusion::icon("edit-undo"), "Restore", this,
                   [this] { runAction("restore"); });
  for (const auto &entry : preferences.menu()) {
    if (!entry.value("enabled", true).toBool())
      continue;
    const QString id = entry["id"].toString();
    if (items.isEmpty() &&
        QStringList{"open", "openTab", "openWith", "cut", "copy", "rename",
                    "trash", "delete", "compress", "extract"}
            .contains(id))
      continue;
    if (id == "extract" &&
        !std::any_of(items.begin(), items.end(), [](const KFileItem &item) {
          const auto type = item.mimetype();
          return type.contains("zip") || type.contains("tar") ||
                 type.contains("rar") || type.contains("compressed") ||
                 type.contains("7z") || type.contains("archive");
        }))
      continue;
    if (id == "pin" && !items.isEmpty() &&
        !std::all_of(items.begin(), items.end(),
                     [](const KFileItem &item) { return item.isDir(); }))
      continue;
    auto *action = menu.addAction(Fusion::icon(entry["icon"].toString()),
                                  entry["name"].toString());
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
  QDialog dialog(this);
  dialog.setWindowTitle("Customize context menu");
  dialog.resize(680, 550);
  auto *layout = new QVBoxLayout(&dialog);
  auto *intro = new QLabel(
      "Choose the actions you use. Drag to reorder; uncheck to hide.");
  layout->addWidget(intro);
  auto *list = new QListWidget;
  list->setDragDropMode(QAbstractItemView::InternalMove);
  layout->addWidget(list, 1);
  auto populate = [&](const QList<QVariantMap> &entries) {
    list->clear();
    for (const auto &entry : entries) {
      auto *item = new QListWidgetItem(Fusion::icon(entry["icon"].toString()),
                                       entry["name"].toString(), list);
      item->setData(Qt::UserRole, entry);
      item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
      item->setCheckState(
          entry.value("enabled", true).toBool() ? Qt::Checked : Qt::Unchecked);
    }
  };
  populate(preferences.menu());
  auto *buttons = new QHBoxLayout;
  layout->addLayout(buttons);
  auto edit = [&](bool creating) {
    auto *item = list->currentItem();
    if (!creating && !item)
      return;
    QVariantMap data =
        creating ? QVariantMap{{"id", "custom:" + QUuid::createUuid().toString(
                                                      QUuid::WithoutBraces)},
                               {"enabled", true},
                               {"icon", "application-x-executable"}}
                 : item->data(Qt::UserRole).toMap();
    QDialog editor(&dialog);
    editor.setWindowTitle(creating ? "Add action" : "Edit action");
    auto *form = new QFormLayout(&editor);
    auto *name = new QLineEdit(data["name"].toString());
    auto *icon = new QLineEdit(data["icon"].toString());
    form->addRow("Name", name);
    form->addRow("Icon name or image path", icon);
    auto *choose = new QPushButton("Choose icon…");
    form->addRow("", choose);
    connect(choose, &QPushButton::clicked, &editor, [&] {
      const auto path = QFileDialog::getOpenFileName(
          &editor, "Choose icon", {}, "Images (*.svg *.png *.jpg *.webp)");
      if (!path.isEmpty())
        icon->setText(path);
    });
    auto *command = new QLineEdit(data["command"].toString());
    const bool custom = data["id"].toString().startsWith("custom:");
    if (custom) {
      form->addRow("Command", command);
      auto *hint =
          new QLabel("%f / %F: local file(s) · %u / %U: URL(s)\nArguments are "
                     "passed directly, without a shell.");
      form->addRow(hint);
    }
    auto *box =
        new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
    form->addRow(box);
    connect(box, &QDialogButtonBox::accepted, &editor, &QDialog::accept);
    connect(box, &QDialogButtonBox::rejected, &editor, &QDialog::reject);
    if (editor.exec() != QDialog::Accepted ||
        name->text().trimmed().isEmpty() ||
        (custom && QProcess::splitCommand(command->text()).isEmpty()))
      return;
    data["name"] = name->text();
    data["icon"] = icon->text();
    if (custom)
      data["command"] = command->text();
    if (creating) {
      item = new QListWidgetItem(list);
      item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
      item->setCheckState(Qt::Checked);
    }
    item->setText(name->text());
    item->setIcon(Fusion::icon(icon->text()));
    item->setData(Qt::UserRole, data);
  };
  for (const auto &label : {"Add…", "Edit…", "Remove", "Restore defaults"}) {
    auto *button = new QPushButton(label);
    buttons->addWidget(button);
    connect(button, &QPushButton::clicked, &dialog, [&, label] {
      if (QString(label) == "Add…")
        edit(true);
      else if (QString(label) == "Edit…")
        edit(false);
      else if (QString(label) == "Remove") {
        auto *item = list->currentItem();
        if (item && item->data(Qt::UserRole)
                        .toMap()["id"]
                        .toString()
                        .startsWith("custom:"))
          delete item;
        else if (item)
          item->setCheckState(Qt::Unchecked);
      } else
        populate(Fusion::menuDefaults());
    });
  }
  auto *box =
      new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
  layout->addWidget(box);
  connect(box, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  connect(box, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  if (dialog.exec() == QDialog::Accepted) {
    QList<QVariantMap> entries;
    for (int i = 0; i < list->count(); ++i) {
      auto *item = list->item(i);
      auto data = item->data(Qt::UserRole).toMap();
      data["enabled"] = item->checkState() == Qt::Checked;
      entries << data;
    }
    preferences.setMenu(entries);
  }
}
void FilesWindow::showShortcuts() {
  QMessageBox::information(
      this, "Keyboard shortcuts",
      "F2 — Rename\nCtrl+C / Ctrl+X / Ctrl+V — Copy / cut / paste\nDelete — "
      "Move to Trash\nShift+Delete — Delete permanently (confirmation)\nCtrl+Z "
      "— Undo\nCtrl+Shift+N — New folder\nCtrl+A — Select all\nCtrl+L or Alt+D "
      "— Edit full path\nAlt+Left / Right / Up — Back / forward / parent\nF5 — "
      "Refresh\nCtrl+H — Hidden files\nAlt+P — Preview pane\nCtrl+F — Filter "
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
  preferences.settings.setValue("geometry", saveGeometry());
  preferences.settings.setValue("splitter", splitter->saveState());
  preferences.settings.sync();
  QMainWindow::closeEvent(event);
}
