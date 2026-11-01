#include "browser.h"
#include <KDirLister>
#include <KFileItemDelegate>
#include <KFilePreviewGenerator>
#include <KIO/CopyJob>
#include <KIO/DropJob>
#include <KIO/FileUndoManager>
#include <KIO/Job>
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
  auto *subtitle = new QLabel("Devices & drives");
  subtitle->setObjectName("muted");
  homeLayout->addWidget(subtitle);
  cards = new QListWidget;
  cards->setObjectName("driveCards");
  cards->setViewMode(QListView::IconMode);
  cards->setResizeMode(QListView::Adjust);
  cards->setMovement(QListView::Static);
  cards->setSpacing(2);
  cards->setGridSize({328, 116});
  cards->setMouseTracking(true);
  cards->setItemDelegate(new DriveDelegate(cards));
  cards->setContextMenuPolicy(Qt::CustomContextMenu);
  homeLayout->addWidget(cards, 1);
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
  previews = new KFilePreviewGenerator(icons);
  previews->setPreviewShown(true);
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
  connect(cards, &QListWidget::itemDoubleClicked, this,
          [this](QListWidgetItem *item) {
            drives->operate(item->data(Qt::UserRole).value<Volume>(), "open",
                            this);
          });
  cards->installEventFilter(this);
  connect(cards, &QWidget::customContextMenuRequested, this,
          [this](const QPoint &point) {
            if (auto *item = cards->itemAt(point))
              drives->menu(item->data(Qt::UserRole).value<Volume>(),
                           cards->viewport()->mapToGlobal(point), this);
          });
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
  for (const auto &index : icons->selectionModel()->selectedRows(0)) {
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
  if (Fusion::isComputer(location()))
    cards->selectAll();
  else
    view()->selectAll();
}
void Browser::updateCards() {
  const int scroll = cards->verticalScrollBar()->value();
  QString selected;
  if (cards->currentItem())
    selected = cards->currentItem()->data(Qt::UserRole).value<Volume>().device;
  cards->clear();
  for (const auto &volume : drives->volumes) {
    auto *item = new QListWidgetItem(cards);
    item->setData(Qt::UserRole, QVariant::fromValue(volume));
    item->setText(volume.name);
    item->setToolTip(volume.name + "\n" + volume.device +
                     (volume.mount.isEmpty() ? "" : "\n" + volume.mount));
    if (volume.device == selected)
      cards->setCurrentItem(item);
  }
  cards->verticalScrollBar()->setValue(scroll);
  if (Fusion::isComputer(location()))
    updateStatus();
}
void Browser::updateStatus() {
  if (Fusion::isComputer(location())) {
    emit statusChanged(QString("%1 volumes").arg(drives->volumes.size()));
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
  if (event->type() == QEvent::KeyPress) {
    auto *key = static_cast<QKeyEvent *>(event);
    if (key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter) {
      if (watched == cards && cards->currentItem())
        drives->operate(
            cards->currentItem()->data(Qt::UserRole).value<Volume>(), "open",
            this);
      else
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
