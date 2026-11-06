#include "browser.h"
#include "transfers.h"
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
#include <QBackingStore>
#include <functional>
#include <memory>

namespace {
class FilesItemDelegate : public KFileItemDelegate {
public:
  using Rename = std::function<void(const QModelIndex &, const QString &)>;
  FilesItemDelegate(QObject *parent, Rename rename) : KFileItemDelegate(parent), rename(std::move(rename)) {}
  QWidget *createEditor(QWidget *parent, const QStyleOptionViewItem &option, const QModelIndex &index) const override {
    auto *editor = KFileItemDelegate::createEditor(parent, option, index);
    editor->setObjectName("inlineRename");
    if (auto *text = qobject_cast<QTextEdit *>(editor)) text->document()->setDocumentMargin(0);
    return editor;
  }
  void setEditorData(QWidget *editor, const QModelIndex &index) const override {
    auto *text = qobject_cast<QTextEdit *>(editor);
    // Thumbnail/model refreshes must not replace a name already being edited.
    if (!text || text->isEnabled()) return;
    const auto alignment = text->alignment();
    KFileItemDelegate::setEditorData(editor, index);
    const auto item = index.data(KDirModel::FileItemRole).value<KFileItem>();
    const auto name = item.name();
    text->setPlainText(name); text->setAlignment(alignment);
    const int dot = name.lastIndexOf('.');
    const int end = !item.isDir() && dot > 0 ? dot : name.size();
    auto cursor = text->textCursor(); cursor.setPosition(0);
    cursor.setPosition(end, QTextCursor::KeepAnchor); text->setTextCursor(cursor);
  }
  void setModelData(QWidget *editor, QAbstractItemModel *, const QModelIndex &index) const override {
    if (auto *text = qobject_cast<QTextEdit *>(editor)) rename(index, text->toPlainText());
  }
  void updateEditorGeometry(QWidget *editor, const QStyleOptionViewItem &option, const QModelIndex &index) const override {
    KFileItemDelegate::updateEditorGeometry(editor, option, index);
    auto rect = editor->geometry();
    rect.setHeight(qMax(rect.height(), editor->fontMetrics().lineSpacing() + 4));
    editor->setGeometry(rect);
  }
private:
  Rename rename;
};

// Qt keeps a snapshot of QDrag::pixmap() for the native drag surface. Paint
// that same surface through QBackingStore when the requested action changes;
// Hyprland overrides drag cursors, so a cursor-only badge is invisible there.
// No native handles or Qt private headers are needed. If a platform uses a
// different drag window, it retains the initial standard QDrag pixmap.
class FileDragFeedback : public QObject {
public:
  FileDragFeedback(QDrag *drag, const QIcon &icon, int count, const QPalette &palette, qreal scale)
      : icon(icon), count(count), palette(palette) {
    action=QGuiApplication::keyboardModifiers().testFlag(Qt::ControlModifier)?Qt::CopyAction:Qt::MoveAction;
    drag->setPixmap(pixmap(scale));drag->setHotSpot({-12,-8});
    qApp->installEventFilter(this);
    // Some Wayland compositors never report source action changes. The Ctrl
    // badge must still follow the key while crossing application boundaries.
    connect(&modifiers,&QTimer::timeout,this,[this] {
      const auto next=QGuiApplication::keyboardModifiers().testFlag(Qt::ControlModifier)?Qt::CopyAction:Qt::MoveAction;
      if (action==next) return;
      action=next;paint();
    });
    modifiers.start(32); // Repaint only when the key changes, and only while dragging.
  }
  ~FileDragFeedback() override { qApp->removeEventFilter(this); }
protected:
  bool eventFilter(QObject *object,QEvent *event) override {
    if (!window && event->type()==QEvent::Show && object->inherits("QShapedPixmapWindow")) {
      window=qobject_cast<QWindow *>(object);
      if (window) {
        backing=std::make_unique<QBackingStore>(window);
        connect(window,&QObject::destroyed,this,[this]{backing.reset();window=nullptr;});
      }
    }
    if (object==window && backing) {
      if (event->type()==QEvent::UpdateRequest) { paint();return true; }
      if (event->type()==QEvent::Expose || event->type()==QEvent::Resize || event->type()==QEvent::DevicePixelRatioChange)
        QTimer::singleShot(0,this,[this]{paint();});
    }
    return false;
  }
private:
  QIcon icon;
  int count;
  QPalette palette;
  Qt::DropAction action;
  QTimer modifiers;
  QPointer<QWindow> window;
  std::unique_ptr<QBackingStore> backing;
  QPixmap pixmap(qreal scale) const {
    QPixmap image(QSize(64,64)*scale);image.setDevicePixelRatio(scale);image.fill(Qt::transparent);
    QPainter painter(&image);painter.setRenderHint(QPainter::Antialiasing);
    icon.paint(&painter,QRect(10,4,48,48));
    if (count>1) {
      painter.setPen(Qt::NoPen);painter.setBrush(palette.highlight());painter.drawRoundedRect(QRectF(38,0,26,20),8,8);
      painter.setPen(palette.highlightedText().color());painter.drawText(QRect(38,0,26,20),Qt::AlignCenter,QString::number(count));
    }
    if (action==Qt::CopyAction) {
      painter.setPen(QPen(Qt::white,1.5));painter.setBrush(QColor("#2468bb"));
      painter.drawRoundedRect(QRectF(4,40,20,20),4,4);
      painter.setPen(QPen(Qt::white,2));painter.drawLine(QPointF(9,50),QPointF(19,50));
      painter.drawLine(QPointF(14,45),QPointF(14,55));
    }
    return image;
  }
  void paint() {
    if (!window || !backing || !window->isExposed()) return;
    const QRect rect(QPoint(),window->size());backing->resize(rect.size());backing->beginPaint(rect);
    QPainter painter(backing->paintDevice());painter.setCompositionMode(QPainter::CompositionMode_Source);
    painter.fillRect(rect,Qt::transparent);painter.drawPixmap(0,0,pixmap(window->devicePixelRatio()));painter.end();
    backing->endPaint();backing->flush(rect);
  }
};
void startFileDrag(QAbstractItemView *view, Qt::DropActions supported) {
  QModelIndexList indexes;
  for (const auto &index : view->selectionModel()->selectedIndexes())
    if (index.column() == KDirModel::Name) indexes << index;
  if (indexes.isEmpty()) return;
  auto *drag = new QDrag(view);
  drag->setMimeData(view->model()->mimeData(indexes));
  FileDragFeedback feedback(drag,qvariant_cast<QIcon>(indexes.first().data(Qt::DecorationRole)),
                            indexes.size(),view->palette(),view->devicePixelRatioF());
  // KIO owns file removal and Undo; the view must not remove source rows when
  // the destination reports Move before its asynchronous job completes.
  drag->exec(supported & (Qt::CopyAction | Qt::MoveAction), Qt::MoveAction);
}
class FilesDetailsView : public QTreeView {
protected:
  void startDrag(Qt::DropActions actions) override { startFileDrag(this, actions); }
};
}

class FilesIconView : public QListView {
public:
  using QListView::QListView;
  QModelIndex indexAt(const QPoint &position) const override {
    const auto index = QListView::indexAt(position);
    if (!index.isValid()) return {};
    auto *delegate = qobject_cast<KFileItemDelegate *>(itemDelegateForIndex(index));
    if (!delegate) return index;
    QStyleOptionViewItem option;
    initViewItemOption(&option);
    option.rect = visualRect(index);
    if (selectionModel()->isSelected(index)) option.state |= QStyle::State_Selected;
    // The painted cell includes selection padding. Only the actual icon and
    // filename are file hits; its remaining space can start a rubber band.
    return delegate->shape(option, index).contains(position) ? index : QModelIndex();
  }
protected:
  void startDrag(Qt::DropActions actions) override { startFileDrag(this, actions); }
};

class FilesFilter : public KDirSortFilterProxyModel {
public:
  using KDirSortFilterProxyModel::KDirSortFilterProxyModel;
  QJsonArray patterns;
  bool directoriesOnly = false;
  void update(const QJsonArray &value, bool dirs) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 10, 0)
    beginFilterChange();
#endif
    patterns = value;
    directoriesOnly = dirs;
#if QT_VERSION >= QT_VERSION_CHECK(6, 10, 0)
    endFilterChange(Direction::Rows);
#else
    invalidateFilter();
#endif
  }
protected:
  bool filterAcceptsRow(int row, const QModelIndex &parent) const override {
    if (!KDirSortFilterProxyModel::filterAcceptsRow(row, parent)) return false;
    const auto *model = static_cast<KDirModel *>(sourceModel());
    const auto item = model->itemForIndex(model->index(row, 0, parent));
    if (item.isDir()) return true;
    if (directoriesOnly) return false;
    if (patterns.isEmpty()) return true;
    for (const auto &entry : patterns) {
      const auto pair = entry.toArray();
      if (pair.size() != 2) continue;
      const QString value = pair[1].toString();
      if (pair[0].toInt() == 0) {
        const auto expression = QRegularExpression::wildcardToRegularExpression(value);
        if (QRegularExpression(expression).match(item.name()).hasMatch()) return true;
      } else if (pair[0].toInt() == 1) {
        const auto mime = QMimeDatabase().mimeTypeForName(item.mimetype());
        if (mime.name() == value || mime.inherits(value) ||
            (value.endsWith("/*") && mime.name().startsWith(value.left(value.size()-1)))) return true;
      }
    }
    return false;
  }
};

void Browser::setPickerFilter(const QJsonArray &patterns, bool directoriesOnly) {
  static_cast<FilesFilter *>(proxy)->update(patterns, directoriesOnly);
}

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
  driveSplitter = new QSplitter(Qt::Vertical);
  driveSplitter->setObjectName("driveSections");
  driveSplitter->setChildrenCollapsible(false);
  driveSplitter->setHandleWidth(9);
  // Keep every section tall enough for all its drive rows. On a short display,
  // scroll the complete drive view instead of clipping rows in each section.
  auto *driveScroll = new QScrollArea;
  driveScroll->setObjectName("computerDrivesScroll");
  driveScroll->setWidgetResizable(true);
  driveScroll->setFrameShape(QFrame::NoFrame);
  driveScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  driveScroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Ignored);
  driveScroll->setWidget(driveSplitter);
  driveSplitter->installEventFilter(this);
  computer->installEventFilter(this);
  auto addSection = [this](DriveSection &section, const QString &title,
                            const QString &id, int minimum) {
    auto *panel = new QWidget;
    panel->setMinimumHeight(minimum);
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(0, 5, 0, 5);
    auto *heading = new QLabel(title);
    heading->setObjectName("driveSectionTitle");
    layout->addWidget(heading);
    section.scroll = new QScrollArea;
    section.scroll->setObjectName(id);
    section.scroll->setProperty("driveSection", true);
    section.scroll->setWidgetResizable(true);
    section.scroll->setFrameShape(QFrame::NoFrame);
    section.scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    section.scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *body = new QWidget;
    body->setObjectName("driveRows");
    section.layout = new QVBoxLayout(body);
    section.layout->setContentsMargins(0, 0, 4, 0);
    section.layout->setSpacing(12);
    section.layout->addStretch();
    section.scroll->setWidget(body);
    layout->addWidget(section.scroll, 1);
    driveSplitter->addWidget(panel);
  };
  addSection(mountedSection, "Mounted drives", "mountedDrives", 145);
  addSection(usbSection, "USB devices", "usbDrives", 175);
  addSection(unmountedSection, "Unmounted drives", "unmountedDrives", 175);
  driveSplitter->setStretchFactor(0, 0);
  driveSplitter->setStretchFactor(1, 0);
  driveSplitter->setStretchFactor(2, 1);
  driveSplitter->setSizes({235, 155, 250});
  for (int i = 1; i < driveSplitter->count(); ++i)
    driveSplitter->handle(i)->setToolTip("Drag to resize drive sections");
  if (preferences->settings.contains("computerSections")) {
    driveSplitter->restoreState(
        preferences->settings.value("computerSections").toByteArray());
  }
  connect(driveSplitter, &QSplitter::splitterMoved, this, [this] {
    preferences->settings.setValue("computerSections",
                                   driveSplitter->saveState());
  });
  homeLayout->addWidget(driveScroll, 1);
  emptyDrives = new QLabel("No drives detected.");
  emptyDrives->setObjectName("emptyDrives");
  emptyDrives->setProperty("muted", true);
  homeLayout->addWidget(emptyDrives, 1, Qt::AlignTop);
  auto *hint = new QLabel(
      "Double-click a drive to open it. Right-click for mount options.");
  hint->setObjectName("muted");
  homeLayout->addWidget(hint);
  stack->addWidget(computer);
  model = new KDirModel(this);
  model->setDropsAllowed(KDirModel::DropOnDirectory);
  model->dirLister()->setAutoErrorHandlingEnabled(false);
  proxy = new FilesFilter(this);
  proxy->setSourceModel(model);
  proxy->setSortFoldersFirst(true);
  proxy->setSortCaseSensitivity(Qt::CaseInsensitive);
  proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
  proxy->setFilterKeyColumn(0);
  proxy->sort(0);
  icons = new FilesIconView;
  icons->setObjectName("files");
  icons->setModel(proxy);
  icons->setMovement(QListView::Static);
  icons->setResizeMode(QListView::Adjust);
  icons->setUniformItemSizes(true);
  icons->setWordWrap(true);
  icons->setSpacing(5);
  icons->setSelectionRectVisible(true);
  icons->setItemDelegate(new FilesItemDelegate(icons, [this](const QModelIndex &index, const QString &name) { renameItem(index, name); }));
  details = new FilesDetailsView;
  details->setObjectName("details");
  details->setModel(proxy);
  details->setItemDelegate(new FilesItemDelegate(details, [this](const QModelIndex &index, const QString &name) { renameItem(index, name); }));
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
    view->setDefaultDropAction(Qt::MoveAction);
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
  auto updateAddress = [this] {
    const auto items = selectedItems();
    navigator->setSelectedFileUrl(items.size() == 1 && !items.first().isDir()
                                     ? items.first().url() : QUrl{});
  };
  connect(icons->selectionModel(), &QItemSelectionModel::selectionChanged, this,
          updateAddress);
  connect(proxy, &QAbstractItemModel::dataChanged, this, updateAddress);
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
  connect(navigator, &PathBar::fileActivated, this, [this](const QUrl &url) {
    emit openRequested(model->itemForIndex(model->indexForUrl(url)), false);
  });
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
void Browser::refreshIcons() {
  // Ask the preview provider to replace cached themed pixmaps, without
  // reopening the folder or losing selection, history or an inline rename.
  previews->updateIcons();
  icons->viewport()->update();
  details->viewport()->update();
}
void Browser::setView(int mode) {
  viewMode = qBound(0, mode, 4);
  preferences->settings.setValue("view", viewMode);
  const int size = mode == 0 ? 24 : mode == 1 ? 48 : mode == 2 ? 80 : 20;
  icons->setIconSize({size, size});
  details->setIconSize({20, 20});
  const bool compact = mode == 3;
  icons->setViewMode(compact ? QListView::ListMode : QListView::IconMode);
  // QListView resets these when changing view mode with Static movement.
  // Keep the arranged grid, but allow native URI drags to folders and apps.
  icons->setDragEnabled(true);
  icons->setAcceptDrops(true);
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
void Browser::renameSelected() {
  const auto items = selectedItems();
  if (items.size() != 1 || Fusion::isComputer(location())) return;
  const auto index = proxy->mapFromSource(model->indexForUrl(items.first().url()));
  if (!index.isValid()) return;
  view()->setCurrentIndex(index); view()->scrollTo(index); view()->setFocus();
  view()->edit(index);
}
void Browser::renameItem(const QModelIndex &index, const QString &name) {
  const auto item = model->itemForIndex(proxy->mapToSource(index));
  if (item.isNull() || name == item.name()) return;
  if (!Fusion::validName(name)) {
    notice->setText("Choose a name without /, and different from . or .."); notice->show(); return;
  }
  const auto from = item.url();
  auto to = from.adjusted(QUrl::RemoveFilename); to.setPath(to.path() + name);
  auto *job = KIO::moveAs(from, to, KIO::HideProgressInfo);
  job->setUiDelegate(nullptr); // A rename collision is an error, never an overwrite.
  KIO::FileUndoManager::self()->recordCopyJob(job);
  connect(job, &KJob::result, this, [this, to, folder = location()](KJob *result) {
    if (!result->error() && location() == folder) selectUrl(to);
  });
  emit jobStarted(job);
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
  const auto previousGroups = mountedSection.groups.keys() + usbSection.groups.keys() + unmountedSection.groups.keys();
  // Classify physical drives, not individual partitions: a partially mounted
  // disk belongs in one row with all its partitions. USB devices stay together.
  QMap<QString, QList<Volume>> groups;
  QStringList order;
  for (const auto &volume : drives->volumes) {
    const QString key = volume.driveKey();
    if (!groups.contains(key))
      order << key;
    groups[key] << volume;
  }
  QMap<QString, DriveSection *> sections;
  for (auto it = groups.begin(); it != groups.end(); ++it) {
    auto &volumes = it.value();
    const bool usb = std::any_of(volumes.cbegin(), volumes.cend(),
                                [](const Volume &v) { return v.usb(); });
    const bool mounted = std::any_of(volumes.cbegin(), volumes.cend(),
                                    [](const Volume &v) { return v.mounted(); });
    sections[it.key()] = usb ? &usbSection
                            : mounted ? &mountedSection : &unmountedSection;
    std::stable_sort(volumes.begin(), volumes.end(),
                     [](const Volume &a, const Volume &b) {
                       if (a.size != b.size)
                         return a.size > b.size;
                       return a.device < b.device;
                     });
  }
  QMap<DriveSection *, int> positions, rowIndices;
  QPointer<QWidget> rowFocus;
  for (auto *section : {&mountedSection, &usbSection, &unmountedSection})
    positions[section] = section->scroll->verticalScrollBar()->value();
  for (auto *section : {&mountedSection, &usbSection, &unmountedSection}) {
    for (const auto &key : section->groups.keys()) {
      if (sections.value(key) == section)
        continue;
      auto *group = section->groups.take(key);
      section->layout->removeWidget(group);
      if (auto *destination = sections.value(key)) {
        // Reparent an existing row when the drive mounts/unmounts. Selection,
        // keyboard focus and the row's horizontal position stay intact.
        const QPointer<QWidget> focused = QApplication::focusWidget();
        const bool restoreFocus = focused && group->isAncestorOf(focused);
        group->setParent(destination->scroll->widget());
        destination->groups.insert(key, group);
        destination->layout->insertWidget(0, group);
        group->show();
        if (restoreFocus)
          rowFocus = focused;
      } else {
        driveLists.removeAll(group->findChild<QListWidget *>());
        delete group;
      }
    }
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
  for (const auto &key : order) {
    auto *section = sections[key];
    const auto &volumes = groups[key];
    QGroupBox *group = section->groups.value(key);
    if (!group) {
      // QGroupBox inherits the active theme's shape, including square corners.
      group = new QGroupBox;
      group->setObjectName("physicalDriveGroup");
      group->setProperty("driveKey", key);
      group->setProperty("physicalDrive", true);
      group->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
      auto *layout = new QVBoxLayout(group);
      layout->setContentsMargins(10, 10, 10, 4);
      layout->setSpacing(5);
      auto *header = new QHBoxLayout;
      header->setContentsMargins(6, 0, 6, 0);
      auto *art = new QLabel;
      art->setObjectName("driveRowIcon");
      art->setFixedSize(32, 32);
      header->addWidget(art);
      auto *identity = new QVBoxLayout;
      identity->setSpacing(2);
      auto *heading = new QLabel;
      heading->setObjectName("driveRowTitle");
      heading->setTextFormat(Qt::PlainText);
      heading->setWordWrap(true);
      auto *description = new QLabel;
      description->setObjectName("driveRowDescription");
      description->setTextFormat(Qt::PlainText);
      description->setWordWrap(true);
      identity->addWidget(heading);
      identity->addWidget(description);
      header->addLayout(identity, 1);
      auto *automatic = new QCheckBox("Auto mount");
      automatic->setObjectName("autoMountDrive");
      automatic->setToolTip("Mount the volumes you’ve successfully mounted on this drive at sign-in and when reconnected. "
                            "Uses your normal system authorization if needed. "
                            "Unchecking keeps them mounted now and disables future automatic mounts.");
      header->addWidget(automatic, 0, Qt::AlignTop);
      connect(automatic, &QCheckBox::clicked, this, [this, group](bool enabled) {
        drives->setAutoMount(group->property("driveKey").toString(), enabled);
      });
      layout->addLayout(header);
      auto *list = new QListWidget;
      configureCards(list);
      list->setProperty("driveKey", key);
      list->setWrapping(false);
      list->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
      list->setFixedHeight(136);
      layout->addWidget(list);
      section->groups.insert(key, group);
    }
    section->layout->insertWidget(rowIndices[section]++, group);
    const auto &disk = volumes.first();
    group->findChild<QLabel *>("driveRowIcon")->setPixmap(
        Fusion::icon(section == &usbSection ? "drive-removable-media-usb"
                                            : "drive-harddisk").pixmap(32, 32));
    group->findChild<QLabel *>("driveRowTitle")
        ->setText(disk.driveModel.isEmpty() ? QFileInfo(key).fileName()
                                          : disk.driveModel);
    QStringList description{key};
    if (disk.driveSize)
      description << QLocale().formattedDataSize(disk.driveSize);
    const int mounted = std::count_if(volumes.cbegin(), volumes.cend(),
                                      [](const Volume &v) { return v.mounted(); });
    description << QString("%1 %2 · %3 mounted")
                       .arg(volumes.size())
                       .arg(volumes.size() == 1 ? "volume" : "partitions")
                       .arg(mounted);
    group->findChild<QLabel *>("driveRowDescription")
        ->setText(description.join(" · "));
    const auto automatic = drives->autoMountChoice(key);
    auto *check = group->findChild<QCheckBox *>("autoMountDrive");
    {
      QSignalBlocker blocker(check);
      check->setVisible(automatic.available);
      check->setTristate(automatic.state == Qt::PartiallyChecked);
      check->setCheckState(automatic.state);
    }
    populate(group->findChild<QListWidget *>(), volumes);
  }
  for (auto *section : {&mountedSection, &usbSection, &unmountedSection}) {
    // QSplitter also hides the adjacent handle and redistributes its space.
    section->scroll->parentWidget()->setVisible(!section->groups.isEmpty());
    section->scroll->verticalScrollBar()->setValue(positions[section]);
  }
  driveSplitter->setVisible(!groups.isEmpty());
  emptyDrives->setVisible(groups.isEmpty());
  if (rowFocus)
    rowFocus->setFocus(Qt::OtherFocusReason);
  queueDriveLayout(previousGroups != mountedSection.groups.keys() + usbSection.groups.keys() + unmountedSection.groups.keys());
  if (Fusion::isComputer(location()))
    updateStatus();
}
void Browser::queueDriveLayout(bool fitContents) {
  fitSectionContents |= fitContents;
  if (driveLayoutQueued) return;
  driveLayoutQueued = true;
  QTimer::singleShot(0, this, [this] {
    driveLayoutQueued = false;
    fitDriveSections();
  });
}
void Browser::fitDriveSections() {
  if (!computer->isVisible() || !driveSplitter->isVisible()) return;
  QList<int> wanted;
  int count = 0, total = 0;
  for (auto *section : {&mountedSection, &usbSection, &unmountedSection}) {
    auto *panel = section->scroll->parentWidget();
    int height = 0;
    if (!section->groups.isEmpty()) {
      ++count;
      const auto margins = panel->layout()->contentsMargins();
      const int heading = panel->findChild<QLabel *>("driveSectionTitle")->sizeHint().height();
      const int content = qMax(section->layout->minimumSize().height(),
                              section->layout->totalHeightForWidth(section->scroll->viewport()->width()));
      height = content + heading + margins.top() + margins.bottom() + panel->layout()->spacing()
               + 2 * section->scroll->frameWidth();
    }
    panel->setMinimumHeight(height);
    section->scroll->verticalScrollBar()->setValue(0);
    wanted << height;
    total += height;
  }
  driveSplitter->setMinimumHeight(total + qMax(0, count - 1) * driveSplitter->handleWidth());
  if (fitSectionContents) driveSplitter->setSizes(wanted);
  fitSectionContents = false;
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
  const auto index = view->indexAt(position);
  return index.isValid() ? model->itemForIndex(proxy->mapToSource(index)) : KFileItem();
}
bool Browser::eventFilter(QObject *watched, QEvent *event) {
  if ((watched == computer || watched == driveSplitter) &&
      (event->type() == QEvent::Resize || event->type() == QEvent::Show ||
       event->type() == QEvent::StyleChange || event->type() == QEvent::FontChange))
    queueDriveLayout();
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
    const auto action = Fusion::fileDropAction(drag->mimeData(), drag->modifiers(), drag->possibleActions());
    if (action == Qt::IgnoreAction) drag->ignore();
    else { drag->setDropAction(action);drag->accept(); }
    return true;
  }
  if (event->type() == QEvent::Drop) {
    auto *drop = static_cast<QDropEvent *>(event);
    const auto action = Fusion::fileDropAction(drop->mimeData(), drop->modifiers(), drop->possibleActions());
    if (action == Qt::IgnoreAction) { drop->ignore();return true; }
    const auto item = itemAt(target, drop->position().toPoint());
    const QUrl dest = !item.isNull() && item.isDir() ? item.url() : location();
    drop->setDropAction(action);
    auto *job = Fusion::dropFiles(drop, dest, window(), target->viewport()->mapToGlobal(drop->position().toPoint()));
    if (!job) { drop->ignore();return true; }
    KJobWidgets::setWindow(job, window());
    emit jobStarted(job);
    drop->accept();
    return true;
  }
  return QWidget::eventFilter(watched, event);
}
