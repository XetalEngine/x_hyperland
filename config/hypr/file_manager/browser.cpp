#include "browser.h"
#include <KDirLister>
#include <KFileItemDelegate>
#include <KFilePreviewGenerator>
#include <KIO/CopyJob>
#include <KIO/DropJob>
#include <KIO/FileUndoManager>
#include <KIO/Job>
#include <KIO/PreviewJob>
#include <KPluginMetaData>
#include <KJobWidgets>
#include <KUrlComboBox>

Browser::Browser(Fusion::Preferences *settings, Drives *volumes,
                 QWidget *parent)
    : QWidget(parent), preferences(settings), drives(volumes) {
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(0);
  auto *address = new QFrame;
  address->setObjectName("addressRow");
  auto *row = new QHBoxLayout(address);
  row->setContentsMargins(10, 8, 10, 8);
  navigator = new PathBar(this);
  navigator->setObjectName("addressBar");
  navigator->setUrlEditable(
      preferences->settings.value("addressEditable", false).toBool());
  row->addWidget(navigator, 1);
  filter = new QLineEdit;
  filter->setObjectName("folderFilter");
  filter->setPlaceholderText("Filter this folder…");
  filter->setClearButtonEnabled(true);
  row->addWidget(filter);
  layout->addWidget(address);
  notice = new QLabel;
  notice->setWordWrap(true);
  notice->setContentsMargins(14, 8, 14, 8);
  notice->hide();
  layout->addWidget(notice);
  stack = new QStackedWidget;
  layout->addWidget(stack, 1);
  computer = new QWidget;
  computer->setObjectName("computerPage");
  auto *homeLayout = new QVBoxLayout(computer);
  homeLayout->setContentsMargins(24, 18, 20, 16);
  auto *title = new QLabel("This PC");
  title->setObjectName("computerTitle");
  homeLayout->addWidget(title);
  driveSplitter = new QSplitter(Qt::Vertical);
  driveSplitter->setObjectName("driveSections");
  driveSplitter->setChildrenCollapsible(false);
  driveSplitter->setHandleWidth(9);
  auto *mountedPanel = new QWidget;
  mountedPanel->setMinimumHeight(145);
  auto *mountedPanelLayout = new QVBoxLayout(mountedPanel);
  mountedPanelLayout->setContentsMargins(0, 0, 0, 9);
  auto *mountedTitle = new QLabel("Mounted drives");
  mountedTitle->setObjectName("driveSectionTitle");
  mountedPanelLayout->addWidget(mountedTitle);
  mountedScroll = new QScrollArea;
  mountedScroll->setObjectName("mountedDrives");
  mountedScroll->setWidgetResizable(true);
  mountedScroll->setFrameShape(QFrame::NoFrame);
  mountedScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  auto *mountedBody = new QWidget;
  mountedBody->setObjectName("mountedDriveRows");
  mountedLayout = new QVBoxLayout(mountedBody);
  mountedLayout->setContentsMargins(0, 0, 0, 0);
  mountedLayout->setSpacing(14);
  mountedEmpty = new QLabel("No mounted internal drives.");
  mountedEmpty->setObjectName("muted");
  mountedLayout->addWidget(mountedEmpty);
  mountedLayout->addStretch();
  mountedScroll->setWidget(mountedBody);
  mountedPanelLayout->addWidget(mountedScroll, 1);
  driveSplitter->addWidget(mountedPanel);
  auto *usbPanel = new QWidget;
  usbPanel->setObjectName("usbDrivePanel");
  usbPanel->setMinimumHeight(95);
  auto *usbLayout = new QVBoxLayout(usbPanel);
  usbLayout->setContentsMargins(0, 9, 0, 9);
  auto *usbTitle = new QLabel("USB devices");
  usbTitle->setObjectName("driveSectionTitle");
  usbLayout->addWidget(usbTitle);
  usbEmpty = new QLabel("No USB devices connected.");
  usbEmpty->setObjectName("muted");
  usbLayout->addWidget(usbEmpty);
  usbCards = new QListWidget;
  configureCards(usbCards);
  usbLayout->addWidget(usbCards, 1);
  driveSplitter->addWidget(usbPanel);
  auto *unmountedPanel = new QWidget;
  unmountedPanel->setMinimumHeight(175);
  auto *unmountedLayout = new QVBoxLayout(unmountedPanel);
  unmountedLayout->setContentsMargins(0, 12, 0, 0);
  auto *unmountedTitle = new QLabel("Unmounted drives");
  unmountedTitle->setObjectName("driveSectionTitle");
  unmountedLayout->addWidget(unmountedTitle);
  unmountedEmpty = new QLabel("No unmounted internal drives.");
  unmountedEmpty->setObjectName("muted");
  unmountedLayout->addWidget(unmountedEmpty);
  cards = new QListWidget;
  configureCards(cards);
  unmountedLayout->addWidget(cards, 1);
  driveSplitter->addWidget(unmountedPanel);
  driveSplitter->setStretchFactor(0, 0);
  driveSplitter->setStretchFactor(1, 0);
  driveSplitter->setStretchFactor(2, 1);
  driveSplitter->setSizes({235, 155, 250});
  driveSplitter->handle(1)->setToolTip(
      "Drag to resize mounted drives and USB devices");
  driveSplitter->handle(2)->setToolTip(
      "Drag to resize USB devices and unmounted drives");
  if (preferences->settings.contains("computerSections")) {
    driveLayoutReady = driveSplitter->restoreState(
        preferences->settings.value("computerSections").toByteArray());
  }
  connect(driveSplitter, &QSplitter::splitterMoved, this, [this] {
    driveLayoutReady = true;
    preferences->settings.setValue("computerSections",
                                   driveSplitter->saveState());
  });
  homeLayout->addWidget(driveSplitter, 1);
  auto *hint = new QLabel(
      "Double-click a drive to open it. Right-click for mount options.");
  hint->setObjectName("muted");
  homeLayout->addWidget(hint);
  stack->addWidget(computer);
  model = new KDirModel(this);
  model->dirLister()->setAutoErrorHandlingEnabled(false);
  proxy = new KDirSortFilterProxyModel(this);
  proxy->setSourceModel(model);
  proxy->setSortFoldersFirst(true);
  proxy->setSortCaseSensitivity(Qt::CaseInsensitive);
  proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
  proxy->setFilterKeyColumn(0);
  proxy->sort(0);
  icons = new QListView;
  icons->setObjectName("files");
  icons->setModel(proxy);
  icons->setMovement(QListView::Static);
  icons->setResizeMode(QListView::Adjust);
  icons->setUniformItemSizes(true);
  icons->setWordWrap(true);
  icons->setSpacing(5);
  icons->setItemDelegate(new KFileItemDelegate(icons));
  details = new QTreeView;
  details->setObjectName("details");
  details->setModel(proxy);
  details->setRootIsDecorated(false);
  details->setItemsExpandable(false);
  details->setAllColumnsShowFocus(true);
  details->setUniformRowHeights(true);
  details->setSortingEnabled(true);
  details->sortByColumn(0, Qt::AscendingOrder);
  details->setSelectionModel(icons->selectionModel());
  details->setSelectionBehavior(QAbstractItemView::SelectRows);
  details->header()->setSectionsMovable(true);
  details->header()->setFirstSectionMovable(true);
  details->header()->setStretchLastSection(false);
  details->header()->setSectionResizeMode(QHeaderView::Interactive);
  details->setColumnWidth(KDirModel::Name, 320);
  details->setColumnWidth(KDirModel::Size, 110);
  details->setColumnWidth(KDirModel::ModifiedTime, 190);
  details->setColumnWidth(KDirModel::Type, 180);
  for (int i = 0; i < KDirModel::ColumnCount; ++i)
    details->setColumnHidden(i, i == KDirModel::Permissions ||
                                    i == KDirModel::Owner ||
                                    i == KDirModel::Group);
  const QByteArray header =
      preferences->settings.value("columns").toByteArray();
  if (!header.isEmpty())
    details->header()->restoreState(header);
  details->setColumnHidden(KDirModel::Name, false);
  details->header()->setContextMenuPolicy(Qt::CustomContextMenu);
  connect(details->header(), &QHeaderView::customContextMenuRequested, this,
          &Browser::columnMenu);
  for (auto *view : {static_cast<QAbstractItemView *>(icons),
                     static_cast<QAbstractItemView *>(details)}) {
    view->setSelectionMode(QAbstractItemView::ExtendedSelection);
    view->setEditTriggers(QAbstractItemView::NoEditTriggers);
    view->setDragEnabled(true);
    view->setAcceptDrops(true);
    view->setDragDropMode(QAbstractItemView::DragDrop);
    view->setDefaultDropAction(Qt::CopyAction);
    view->setDropIndicatorShown(true);
    view->setContextMenuPolicy(Qt::CustomContextMenu);
    view->viewport()->installEventFilter(this);
    view->installEventFilter(this);
    connect(view, &QAbstractItemView::doubleClicked, this,
            [this](const QModelIndex &index) {
              emit openRequested(model->itemForIndex(proxy->mapToSource(index)),
                                 false);
            });
    connect(view, &QWidget::customContextMenuRequested, this,
            [this, view](const QPoint &position) {
              const auto index = view->indexAt(position);
              if (!index.isValid())
                view->clearSelection();
              else if (!view->selectionModel()->isSelected(index))
                view->selectionModel()->setCurrentIndex(
                    index, QItemSelectionModel::ClearAndSelect |
                               QItemSelectionModel::Rows);
              emit contextRequested(view->viewport()->mapToGlobal(position));
            });
    stack->addWidget(view);
  }
  // KFilePreviewGenerator disables previews if constructed without an icon
  // size. Later updateIcons() alone cannot turn them back on.
  icons->setIconSize({80, 80});
  previews = new KFilePreviewGenerator(icons);
  QStringList imagePlugins;
  for (const auto &plugin : KIO::PreviewJob::availableThumbnailerPlugins())
    for (const auto &type : plugin.mimeTypes())
      if (type.startsWith("image/")) { imagePlugins << plugin.pluginId(); break; }
  previews->setEnabledPlugins(imagePlugins);
  setThumbnails(preferences->settings.value("thumbnails", true).toBool());
  connect(icons->selectionModel(), &QItemSelectionModel::selectionChanged, this,
          [this] {
            emit selectionChanged();
            updateStatus();
          });
  connect(filter, &QLineEdit::textChanged, this, [this](const QString &text) {
    proxy->setFilterFixedString(text);
    updateStatus();
  });
  connect(navigator, &PathBar::urlChanged, this, &Browser::load);
  connect(navigator, &PathBar::editableStateChanged, this, [this](bool value) {
    preferences->settings.setValue("addressEditable", value);
  });
  connect(navigator, &PathBar::tabRequested, this, [this](const QUrl &url) {
    emit openRequested(KFileItem(url, QString(), S_IFDIR), true);
  });
  connect(model->dirLister(), &KDirLister::started, this,
          [this] { emit statusChanged("Loading…"); });
  connect(model->dirLister(), &KDirLister::completed, this, [this] {
    updateStatus();
    if (pendingSelection.isValid())
      selectUrl(pendingSelection);
  });
  connect(model->dirLister(), &KDirLister::jobError, this,
          [this](KIO::Job *job) {
            notice->setText(job->errorString());
            notice->show();
            updateStatus();
          });
  connect(model->dirLister(), &KDirLister::redirection, this,
          [this](const QUrl &, const QUrl &to) {
            if (to != location()) {
              QSignalBlocker blocker(navigator);
              navigator->setLocationUrl(to);
              emit locationChanged(to);
            }
          });
  connect(proxy, &QAbstractItemModel::rowsInserted, this,
          [this] { updateStatus(); });
  connect(proxy, &QAbstractItemModel::rowsRemoved, this,
          [this] { updateStatus(); });
  connect(drives, &Drives::changed, this, &Browser::updateCards);
  model->dirLister()->setShowHiddenFiles(
      preferences->settings.value("hidden", false).toBool());
  setView(preferences->settings.value("view", 2).toInt());
  updateCards();
  load(Fusion::computerUrl());
}
QUrl Browser::location() const { return navigator->locationUrl(); }
Browser::~Browser() {
  disconnect(drives, nullptr, this, nullptr);
  for (auto *child : findChildren<QObject *>())
    disconnect(child, nullptr, this, nullptr);
  model->dirLister()->stop();
}
void Browser::navigate(const QUrl &url) {
  if (!url.isValid() || url.isEmpty())
    return;
  if (url == location()) {
    refresh();
    return;
  }
  navigator->setLocationUrl(url);
}
void Browser::load(const QUrl &url) {
  pendingSelection.clear();
  notice->hide();
  filter->clear();
  icons->clearSelection();
  setThumbnails(preferences->settings.value("thumbnails", true).toBool());
  if (Fusion::isComputer(url)) {
    model->dirLister()->stop();
    stack->setCurrentWidget(computer);
    filter->setEnabled(false);
    updateStatus();
  } else {
    filter->setEnabled(true);
    stack->setCurrentWidget(viewMode == 4 ? static_cast<QWidget *>(details)
                                          : icons);
    model->openUrl(url);
  }
  emit locationChanged(url);
  emit selectionChanged();
}
void Browser::refresh() {
  if (Fusion::isComputer(location()))
    drives->refresh();
  else {
    notice->hide();
    model->dirLister()->updateDirectory(location());
  }
}
void Browser::setView(int mode) {
  viewMode = qBound(0, mode, 4);
  preferences->settings.setValue("view", viewMode);
  const int size = mode == 0 ? 24 : mode == 1 ? 48 : mode == 2 ? 80 : 20;
  icons->setIconSize({size, size});
  details->setIconSize({20, 20});
  const bool compact = mode == 3;
  icons->setViewMode(compact ? QListView::ListMode : QListView::IconMode);
  icons->setFlow(compact ? QListView::TopToBottom : QListView::LeftToRight);
  icons->setWrapping(true);
  icons->setWordWrap(!compact);
  icons->setGridSize(compact ? QSize(220, 32) : QSize(size + 68, size + 52));
  if (!Fusion::isComputer(location()))
    stack->setCurrentWidget(mode == 4 ? static_cast<QWidget *>(details)
                                      : icons);
  previews->updateIcons();
}
void Browser::setHidden(bool value) {
  model->dirLister()->setShowHiddenFiles(value);
  model->dirLister()->emitChanges();
}
void Browser::setThumbnails(bool enabled) {
  previews->setPreviewShown(enabled && location().isLocalFile());
  previews->updateIcons();
}
void Browser::selectUrl(const QUrl &url) {
  const auto index = proxy->mapFromSource(model->indexForUrl(url));
  if (!index.isValid()) {
    pendingSelection = url;
    return;
  }
  pendingSelection.clear();
  view()->selectionModel()->setCurrentIndex(
      index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
  view()->scrollTo(index);
}
void Browser::saveView() {
  preferences->settings.setValue("columns", details->header()->saveState());
}
void Browser::editAddress() {
  navigator->setUrlEditable(true);
  navigator->editor()->setFocus();
  navigator->editor()->lineEdit()->selectAll();
}
QAbstractItemView *Browser::view() const {
  return viewMode == 4 ? static_cast<QAbstractItemView *>(details) : icons;
}
KFileItemList Browser::selectedItems() const {
  KFileItemList items;
  if (Fusion::isComputer(location()))
    return items;
  // Icon/list views select the name cell, while Details selects whole rows.
  // selectedRows() requires every model column to be selected, so an ordinary
  // icon click used to look like an empty selection to every file action.
  for (const auto &index : view()->selectionModel()->selectedIndexes()) {
    if (index.column() != KDirModel::Name)
      continue;
    const auto item = model->itemForIndex(proxy->mapToSource(index));
    if (!item.isNull())
      items << item;
  }
  return items;
}
QList<QUrl> Browser::selectedUrls() const {
  QList<QUrl> urls;
  for (const auto &item : selectedItems())
    urls << item.url();
  return urls;
}
void Browser::selectAll() {
  if (Fusion::isComputer(location())) {
    for (auto *list : driveLists)
      if (list->hasFocus()) {
        list->selectAll();
        return;
      }
  } else
    view()->selectAll();
}
Volume Browser::selectedVolume() const {
  for (auto *list : driveLists)
    if (!list->selectedItems().isEmpty())
      return list->selectedItems().first()->data(Qt::UserRole).value<Volume>();
  return {};
}
void Browser::configureCards(QListWidget *list) {
  list->setObjectName("driveCards");
  list->setViewMode(QListView::IconMode);
  list->setResizeMode(QListView::Adjust);
  list->setMovement(QListView::Static);
  list->setSpacing(2);
  list->setGridSize({328, 116});
  list->setMouseTracking(true);
  list->setFrameShape(QFrame::NoFrame);
  list->setItemDelegate(new DriveDelegate(list));
  list->setContextMenuPolicy(Qt::CustomContextMenu);
  list->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
  list->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
  list->installEventFilter(this);
  driveLists.append(list);
  connect(list, &QListWidget::itemSelectionChanged, this, [this, list] {
    if (list->selectedItems().isEmpty())
      return;
    for (auto *other : driveLists)
      if (other != list) {
        QSignalBlocker blocker(other);
        other->clearSelection();
      }
  });
  connect(list, &QListWidget::itemDoubleClicked, this,
          [this](QListWidgetItem *item) {
            drives->operate(item->data(Qt::UserRole).value<Volume>(), "open",
                            this);
          });
  connect(list, &QWidget::customContextMenuRequested, this,
          [this, list](const QPoint &point) {
            if (auto *item = list->itemAt(point)) {
              list->setCurrentItem(item);
              drives->menu(item->data(Qt::UserRole).value<Volume>(),
                           list->viewport()->mapToGlobal(point), this);
            } else
              emit computerContextRequested(
                  list->viewport()->mapToGlobal(point));
          });
}
void Browser::updateCards() {
  const QString selected = selectedVolume().device;
  const int mountedPosition = mountedScroll->verticalScrollBar()->value();
  QMap<QString, QList<Volume>> groups;
  QStringList order;
  QList<Volume> unmounted, usb;
  for (const auto &volume : drives->volumes)
    if (volume.usb())
      usb << volume;
    else if (volume.mounted()) {
      const QString key = volume.driveKey();
      if (!groups.contains(key))
        order << key;
      groups[key] << volume;
    } else
      unmounted << volume;
  for (const auto &key : mountedGroups.keys())
    if (!groups.contains(key)) {
      auto *group = mountedGroups.take(key);
      auto *list = group->findChild<QListWidget *>();
      driveLists.removeAll(list);
      mountedLayout->removeWidget(group);
      delete group;
    }
  auto populate = [&](QListWidget *list, const QList<Volume> &volumes) {
    const int vertical = list->verticalScrollBar()->value();
    const int horizontal = list->horizontalScrollBar()->value();
    QSignalBlocker blocker(list);
    // Update matching items in place, so a periodic space refresh cannot
    // interrupt a click, keyboard focus or a horizontally scrolled row.
    for (int i = 0; i < volumes.size(); ++i) {
      const auto &volume = volumes[i];
      QListWidgetItem *item = i < list->count() ? list->item(i) : nullptr;
      if (!item ||
          item->data(Qt::UserRole).value<Volume>().device != volume.device) {
        int found = -1;
        for (int j = i + 1; j < list->count(); ++j)
          if (list->item(j)->data(Qt::UserRole).value<Volume>().device ==
              volume.device) {
            found = j;
            break;
          }
        item = found >= 0 ? list->takeItem(found) : new QListWidgetItem;
        list->insertItem(i, item);
      }
      item->setData(Qt::UserRole, QVariant::fromValue(volume));
      item->setText(volume.name);
      item->setToolTip(volume.name + "\n" + volume.device +
                       (volume.mount.isEmpty() ? "" : "\n" + volume.mount));
      if (volume.device == selected)
        list->setCurrentItem(item);
    }
    while (list->count() > volumes.size())
      delete list->takeItem(list->count() - 1);
    list->verticalScrollBar()->setValue(vertical);
    list->horizontalScrollBar()->setValue(horizontal);
  };
  for (int i = 0; i < order.size(); ++i) {
    const auto &key = order[i];
    const auto &volumes = groups[key];
    QWidget *group = mountedGroups.value(key);
    if (!group) {
      group = new QWidget;
      group->setObjectName("mountedDiskGroup");
      group->setProperty("driveKey", key);
      auto *layout = new QVBoxLayout(group);
      layout->setContentsMargins(0, 0, 0, 0);
      layout->setSpacing(3);
      auto *heading = new QLabel;
      heading->setObjectName("driveRowTitle");
      heading->setTextFormat(Qt::PlainText);
      heading->setWordWrap(true);
      auto *description = new QLabel;
      description->setObjectName("driveRowDescription");
      description->setTextFormat(Qt::PlainText);
      description->setWordWrap(true);
      layout->addWidget(heading);
      layout->addWidget(description);
      auto *list = new QListWidget;
      configureCards(list);
      list->setProperty("driveKey", key);
      list->setWrapping(false);
      list->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
      list->setFixedHeight(140);
      layout->addWidget(list);
      mountedGroups.insert(key, group);
    }
    mountedLayout->insertWidget(i, group);
    const auto &disk = volumes.first();
    group->findChild<QLabel *>("driveRowTitle")
        ->setText(disk.driveModel.isEmpty() ? QFileInfo(key).fileName()
                                            : disk.driveModel);
    QStringList description{key};
    if (disk.driveSize)
      description << QLocale().formattedDataSize(disk.driveSize);
    description << QString("%1 mounted %2")
                       .arg(volumes.size())
                       .arg(volumes.size() == 1 ? "partition" : "partitions");
    group->findChild<QLabel *>("driveRowDescription")
        ->setText(description.join(" · "));
    populate(group->findChild<QListWidget *>(), volumes);
  }
  populate(cards, unmounted);
  std::stable_sort(usb.begin(), usb.end(),
                   [](const Volume &a, const Volume &b) {
                     return a.mounted() && !b.mounted();
                   });
  populate(usbCards, usb);
  mountedEmpty->setVisible(groups.isEmpty());
  unmountedEmpty->setVisible(unmounted.isEmpty());
  usbEmpty->setVisible(usb.isEmpty());
  usbCards->parentWidget()->setMinimumHeight(usb.isEmpty() ? 95 : 175);
  mountedScroll->verticalScrollBar()->setValue(mountedPosition);
  if (!driveLayoutReady && !drives->volumes.isEmpty()) {
    driveLayoutReady = true;
    QTimer::singleShot(0, this, [this] {
      const int available = driveSplitter->height();
      const int wanted =
          mountedGroups.isEmpty() ? 145 : mountedGroups.size() * 190 + 38;
      const int top = qMin(wanted, qMax(145, int(available * .5)));
      const int middle = usbCards->count() ? 170 : 95;
      driveSplitter->setSizes(
          {top, middle, qMax(145, available - top - middle)});
    });
  }
  if (Fusion::isComputer(location()))
    updateStatus();
}
void Browser::updateStatus() {
  if (Fusion::isComputer(location())) {
    const int mounted =
        std::count_if(drives->volumes.cbegin(), drives->volumes.cend(),
                      [](const Volume &v) { return v.mounted(); });
    emit statusChanged(QString("%1 mounted · %2 unmounted")
                           .arg(mounted)
                           .arg(drives->volumes.size() - mounted));
    return;
  }
  const auto items = selectedItems();
  quint64 size = 0;
  for (const auto &item : items)
    if (!item.isDir())
      size += item.size();
  emit statusChanged(items.isEmpty()
                         ? QString("%1 items").arg(proxy->rowCount())
                         : QString("%1 selected · %2")
                               .arg(items.size())
                               .arg(QLocale().formattedDataSize(size)));
}
void Browser::columnMenu(const QPoint &position) {
  QMenu menu(this);
  for (int i = 0; i < model->columnCount(); ++i) {
    auto *action =
        menu.addAction(model->headerData(i, Qt::Horizontal).toString());
    action->setCheckable(true);
    action->setChecked(!details->isColumnHidden(i));
    action->setEnabled(i != KDirModel::Name);
    connect(action, &QAction::toggled, this, [this, i](bool visible) {
      details->setColumnHidden(i, !visible);
      saveView();
    });
  }
  menu.exec(details->header()->mapToGlobal(position));
}
KFileItem Browser::itemAt(QAbstractItemView *view,
                          const QPoint &position) const {
  return model->itemForIndex(proxy->mapToSource(view->indexAt(position)));
}
bool Browser::eventFilter(QObject *watched, QEvent *event) {
  if (!icons || !details)
    return QWidget::eventFilter(watched, event);
  if (event->type() == QEvent::KeyPress) {
    auto *key = static_cast<QKeyEvent *>(event);
    if (key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter) {
      if (auto *list = qobject_cast<QListWidget *>(watched);
          driveLists.contains(list)) {
        if (list->currentItem())
          drives->operate(
              list->currentItem()->data(Qt::UserRole).value<Volume>(), "open",
              this);
      } else
        for (const auto &item : selectedItems())
          emit openRequested(item, false);
      return true;
    }
  }
  auto *target = watched == icons->viewport() || watched == icons
                     ? static_cast<QAbstractItemView *>(icons)
                 : watched == details->viewport() || watched == details
                     ? static_cast<QAbstractItemView *>(details)
                     : nullptr;
  if (!target)
    return QWidget::eventFilter(watched, event);
  if (event->type() == QEvent::MouseButtonRelease) {
    auto *mouse = static_cast<QMouseEvent *>(event);
    if (mouse->button() == Qt::MiddleButton) {
      const auto item = itemAt(target, mouse->position().toPoint());
      if (!item.isNull())
        emit openRequested(item, true);
      return true;
    }
    if (mouse->button() == Qt::BackButton) {
      navigator->goBack();
      return true;
    }
    if (mouse->button() == Qt::ForwardButton) {
      navigator->goForward();
      return true;
    }
  }
  if (event->type() == QEvent::DragEnter || event->type() == QEvent::DragMove) {
    auto *drag = static_cast<QDragMoveEvent *>(event);
    if (drag->mimeData()->hasUrls()) {
      drag->acceptProposedAction();
      return true;
    }
  }
  if (event->type() == QEvent::Drop) {
    auto *drop = static_cast<QDropEvent *>(event);
    if (!drop->mimeData()->hasUrls())
      return false;
    const auto item = itemAt(target, drop->position().toPoint());
    const QUrl dest = !item.isNull() && item.isDir() ? item.url() : location();
    auto *job = KIO::drop(drop, dest);
    KJobWidgets::setWindow(job, window());
    emit jobStarted(job);
    drop->acceptProposedAction();
    return true;
  }
  return QWidget::eventFilter(watched, event);
}
