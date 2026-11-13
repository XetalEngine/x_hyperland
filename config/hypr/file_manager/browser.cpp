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
#include <KIO/SimpleJob>
#include <KPluginMetaData>
#include <KProtocolInfo>
#include <KJobWidgets>
#include <KUrlComboBox>
#include <QBackingStore>
#include <QLocalSocket>
#include <QtConcurrent>
#include <cerrno>
#include <unistd.h>
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
    drag->setPixmap(pixmap(scale));drag->setHotSpot({-12,-8});
    qApp->installEventFilter(this);
    connect(drag,&QDrag::actionChanged,this,[this](Qt::DropAction next) {
      accepted=next;updateAction();
    });
    // Copy carries shortcut URLs on Wayland; modifiers distinguish that from
    // an ordinary copy. Never show an allowed action over a rejected target.
    connect(&modifiers,&QTimer::timeout,this,[this] { updateAction(); });
    modifiers.start(32);
    const auto runtime=qEnvironmentVariable("XDG_RUNTIME_DIR"), signature=qEnvironmentVariable("HYPRLAND_INSTANCE_SIGNATURE");
    if (!runtime.isEmpty() && !signature.isEmpty()) socketPath=runtime+"/hypr/"+signature+"/.socket.sock";
    connect(&probe,&QLocalSocket::connected,this,[this] { probe.write("j/xetal-file-drag"); });
    connect(&probe,&QLocalSocket::readyRead,this,[this] { reply+=probe.readAll();if(reply.size()>4096)probe.abort(); });
    connect(&probe,&QLocalSocket::disconnected,this,[this] {
      const auto value=QJsonDocument::fromJson(reply).object();reply.clear();
      if (!value.value("active").toBool()) { nativeAction.clear();return; }
      nativeAction=value.value("action").toString();updateAction();
    });
    connect(&poll,&QTimer::timeout,this,[this] {
      if (probe.state()!=QLocalSocket::UnconnectedState) {
        if (pending.elapsed()>250) { probe.abort();nativeAction.clear(); }
        return;
      }
      if (!socketPath.isEmpty()) { reply.clear();pending.restart();probe.connectToServer(socketPath); }
    });
    poll.start(50); // Async, only for the duration of this drag; no GUI-thread waits.
  }
  ~FileDragFeedback() override { probe.disconnect(this);probe.abort();qApp->removeEventFilter(this); }
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
  Qt::DropAction action = Qt::IgnoreAction, accepted = Qt::IgnoreAction;
  QTimer modifiers;
  QTimer poll;
  QLocalSocket probe;
  QByteArray reply;
  QString socketPath, nativeAction;
  QElapsedTimer pending;
  QPointer<QWindow> window;
  std::unique_ptr<QBackingStore> backing;
  void updateAction() {
    auto next=accepted;
    const auto keys=QGuiApplication::keyboardModifiers();
    if (next==Qt::CopyAction && keys.testFlag(Qt::ControlModifier) && keys.testFlag(Qt::ShiftModifier))
      next=Qt::LinkAction;
    if (!nativeAction.isEmpty()) next=nativeAction=="copy"?Qt::CopyAction:nativeAction=="move"?Qt::MoveAction:nativeAction=="link"?Qt::LinkAction:Qt::IgnoreAction;
    if (action==next) return;
    action=next;paint();
  }
  QPixmap pixmap(qreal scale) const {
    QPixmap image(QSize(64,64)*scale);image.setDevicePixelRatio(scale);image.fill(Qt::transparent);
    QPainter painter(&image);painter.setRenderHint(QPainter::Antialiasing);
    painter.setOpacity(action==Qt::MoveAction?.45:1);
    icon.paint(&painter,QRect(10,4,48,48));painter.setOpacity(1);
    if (count>1) {
      painter.setPen(Qt::NoPen);painter.setBrush(palette.highlight());painter.drawRoundedRect(QRectF(38,0,26,20),8,8);
      painter.setPen(palette.highlightedText().color());painter.drawText(QRect(38,0,26,20),Qt::AlignCenter,QString::number(count));
    }
    if (action==Qt::IgnoreAction) {
      painter.setPen(QPen(Qt::white,1.5));painter.setBrush(QColor("#d53645"));
      painter.drawEllipse(QRectF(4,40,20,20));
      painter.setPen(QPen(Qt::white,2.5));painter.drawLine(QPointF(8,44),QPointF(20,56));
    } else if (action==Qt::CopyAction || action==Qt::LinkAction) {
      painter.setPen(QPen(Qt::white,1.5));painter.setBrush(QColor("#2468bb"));
      painter.drawRoundedRect(QRectF(4,40,20,20),4,4);
      painter.setPen(QPen(Qt::white,2));
      if (action==Qt::CopyAction) {
        painter.drawLine(QPointF(9,50),QPointF(19,50));painter.drawLine(QPointF(14,45),QPointF(14,55));
      } else {
        painter.drawLine(QPointF(9,55),QPointF(9,48));painter.drawLine(QPointF(9,48),QPointF(19,48));
        painter.drawLine(QPointF(15,44),QPointF(19,48));painter.drawLine(QPointF(15,52),QPointF(19,48));
      }
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
  drag->mimeData()->setData("application/x-hyperfusion-file-drag", "1");
  FileDragFeedback feedback(drag,qvariant_cast<QIcon>(indexes.first().data(Qt::DecorationRole)),
                            indexes.size(),view->palette(),view->devicePixelRatioF());
  // KIO owns file removal and Undo; the view must not remove source rows when
  // the destination reports Move before its asynchronous job completes.
  drag->exec((supported & (Qt::CopyAction | Qt::MoveAction)) | Qt::LinkAction, Qt::MoveAction);
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
  navigationRow = address;
  address->setObjectName("addressRow");
  auto *row = new QHBoxLayout(address);
  row->setContentsMargins(4, 2, 4, 2);
  row->setSpacing(6);
  navigator = new PathBar(this);
  navigator->setObjectName("addressBar");
  row->addWidget(navigator, 1);
  filter = new QLineEdit;
  filter->setObjectName("folderFilter");
  filter->setPlaceholderText("Filter this folder…");
  filter->setToolTip("Filter names in this folder · Ctrl+Shift+F");
  filter->setClearButtonEnabled(true);
  row->addWidget(filter);
  layout->addWidget(address);
  notice = new QLabel;
  notice->setTextFormat(Qt::PlainText);
  notice->setWordWrap(true);
  notice->setContentsMargins(14, 8, 14, 8);
  notice->hide();
  layout->addWidget(notice);
  administratorBar = new QFrame;
  administratorBar->setObjectName("administratorAccess");
  auto *adminRow = new QHBoxLayout(administratorBar);
  adminRow->setContentsMargins(14, 8, 14, 8);
  auto *adminLabel = new QLabel("Administrator access · File operations in this tab can use administrator permissions.");
  adminLabel->setWordWrap(true);
  adminRow->addWidget(adminLabel, 1);
  auto *normalAccess = new QPushButton("Use normal access");
  normalAccess->setObjectName("normalFolderAccess");
  normalAccess->setToolTip("Return this tab to ordinary file access. The system may briefly remember authentication.");
  adminRow->addWidget(normalAccess);
  connect(normalAccess, &QPushButton::clicked, this, [this] {
    navigate(Fusion::ordinaryFileUrl(location()));
  });
  administratorBar->hide();
  layout->addWidget(administratorBar);
  stack = new QStackedWidget;
  layout->addWidget(stack, 1);
  folderMessage = new QWidget;
  folderMessage->setObjectName("folderMessage");
  auto *messageLayout = new QVBoxLayout(folderMessage);
  messageLayout->setContentsMargins(24, 24, 24, 24);
  messageLayout->addStretch();
  auto *card = new QFrame;
  card->setObjectName("folderMessageCard");
  card->setMaximumWidth(560);
  auto *cardLayout = new QVBoxLayout(card);
  cardLayout->setContentsMargins(28, 26, 28, 26);
  cardLayout->setSpacing(14);
  folderSymbol = new QLabel;
  cardLayout->addWidget(folderSymbol);
  folderHeading = new QLabel;
  folderHeading->setObjectName("folderMessageHeading");
  folderHeading->setWordWrap(true);
  cardLayout->addWidget(folderHeading);
  folderExplanation = new QLabel;
  folderExplanation->setObjectName("folderMessageExplanation");
  folderExplanation->setTextFormat(Qt::PlainText);
  folderExplanation->setWordWrap(true);
  cardLayout->addWidget(folderExplanation);
  auto *messageActions = new QHBoxLayout;
  folderAction = new QPushButton;
  folderAction->setObjectName("folderMessageAction");
  messageActions->addWidget(folderAction);
  auto *back = new QPushButton("Go back");
  back->setObjectName("folderMessageBack");
  messageActions->addWidget(back);
  messageActions->addStretch();
  cardLayout->addLayout(messageActions);
  // Give the card its available width before measuring wrapped labels. A
  // horizontally aligned widget can otherwise keep a height calculated for a
  // wider size and clip the final lines of its explanation.
  auto *cardRow = new QHBoxLayout;
  cardRow->addStretch();
  cardRow->addWidget(card, 100);
  cardRow->addStretch();
  messageLayout->addLayout(cardRow);
  messageLayout->addStretch(2);
  stack->addWidget(folderMessage);
  connect(back, &QPushButton::clicked, navigator, &PathBar::goBack);
  connect(navigator, &PathBar::historyChanged, this, [this, back] {
    back->setEnabled(navigator->historyIndex() > 0);
  });
  connect(folderAction, &QPushButton::clicked, this, [this] {
    switch (currentFolderAction) {
    case FolderAction::ShowHidden:
      setHidden(true);
      emit hiddenFilesRequested();
      break;
    case FolderAction::Unlock: {
      if (!location().isLocalFile() || !location().host().isEmpty()) return;
      if (!KProtocolInfo::isKnownProtocol("admin")) {
        listingError = "Administrator access requires the kio-admin package. Install it using Control Panel → Packages, then try again.";
        updateFolderMessage();
        return;
      }
      auto url = location();
      url.setScheme("admin");
      navigate(url);
      break;
    }
    case FolderAction::Retry: refresh(); break;
    case FolderAction::None: break;
    }
  });
  computer = new DriveShelf(preferences, drives);
  connect(computer, &DriveShelf::operationRequested, this, [this](const Volume &volume, const QString &action) {
    drives->operate(volume, action, this);
  });
  connect(computer, &DriveShelf::volumeContextRequested, this, [this](const Volume &volume, const QPoint &point) {
    drives->menu(volume, point, this);
  });
  connect(computer, &DriveShelf::backgroundContextRequested, this, &Browser::computerContextRequested);
  stack->addWidget(computer);
  model = new KDirModel(this);
  model->setDropsAllowed(KDirModel::DropOnDirectory);
  model->dirLister()->setAutoErrorHandlingEnabled(false);
  model->dirLister()->setMainWindow(window());
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
  defaultColumns = details->header()->saveState();
  connect(details->header(), &QHeaderView::sectionResized, this, [this] { saveView(); });
  connect(details->header(), &QHeaderView::sectionMoved, this, [this] { saveView(); });
  connect(details->header(), &QHeaderView::sortIndicatorChanged, this, [this] { saveView(); });
  details->header()->setContextMenuPolicy(Qt::CustomContextMenu);
  connect(details->header(), &QHeaderView::customContextMenuRequested, this,
          &Browser::columnMenu);
  for (auto *view : {static_cast<QAbstractItemView *>(icons),
                     static_cast<QAbstractItemView *>(details)}) {
    view->setSelectionMode(QAbstractItemView::ExtendedSelection);
    view->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    view->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
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
    if (searchActive()) { closeSearch(); filter->setFocus(); }
    proxy->setFilterFixedString(text);
    updateStatus();
  });
  connect(navigator, &PathBar::urlChanged, this, &Browser::load);
  connect(navigator, &PathBar::aboutToNavigate, this, &Browser::rememberPlace);
  connect(navigator, &PathBar::fileActivated, this, [this](const QUrl &url) {
    emit openRequested(model->itemForIndex(model->indexForUrl(url)), false);
  });
  connect(navigator, &PathBar::editingCancelled, this, [this] { view()->setFocus(); });
  connect(navigator, &PathBar::tabRequested, this, [this](const QUrl &url) {
    emit openRequested(KFileItem(url, QString(), S_IFDIR), true);
  });
  connect(model->dirLister(), &KDirLister::started, this,
          [this] {
            listingBusy = true;
            ++accessGeneration;
            listingFailed = privateFolder = false;
            listingError.clear();
            updateFolderMessage();
            emit statusChanged("Loading…");
          });
  connect(model->dirLister(), &KDirLister::listingDirCompleted, this, [this](const QUrl &url) {
    if (url.adjusted(QUrl::StripTrailingSlash) != loadedUrl.adjusted(QUrl::StripTrailingSlash)) return;
    listingBusy = false;
    updateStatus();
    if (pendingSelection.isValid()) {
      selectUrl(pendingSelection);
    } else if (restoringPlace) {
      const auto generation = placeGeneration;
      QTimer::singleShot(0, this, [this, generation] {
        if (generation == placeGeneration) restorePlace();
      });
    }
  });
  connect(model->dirLister(), &KDirLister::jobError, this, &Browser::handleListingError);
  connect(model->dirLister(), &KDirLister::redirection, this,
          [this](const QUrl &, const QUrl &to) {
            if (to != location()) {
              QSignalBlocker blocker(navigator);
              navigator->setLocationUrl(to);
              loadedUrl = to;
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
  saveView();
  disconnect(drives, nullptr, this, nullptr);
  for (auto *child : findChildren<QObject *>())
    disconnect(child, nullptr, this, nullptr);
  model->dirLister()->stop();
  // FilesWindow hosts this tab's address controls in its shared toolbar.
  if (navigationRow) delete navigationRow;
}
void Browser::navigate(const QUrl &url) {
  if (!url.isValid() || url.isEmpty())
    return;
  closeSearch();
  if (url == location()) {
    refresh();
    return;
  }
  navigator->setLocationUrl(url);
}
void Browser::load(const QUrl &url) {
  saveView();
  loadedUrl = url;
  ++placeGeneration;
  pendingPlace = navigator->visitState();
  restoringPlace = !pendingPlace.isEmpty();
  closeSearch();
  pendingSelection.clear();
  notice->hide();
  applyFolderView(url);
  filter->setText(pendingPlace.value("filter").toString());
  listingBusy = !Fusion::isComputer(url);
  ++accessGeneration;
  listingFailed = privateFolder = false;
  listingError.clear();
  administratorBar->setVisible(url.scheme() == "admin");
  icons->clearSelection();
  if (Fusion::isComputer(url)) {
    model->dirLister()->stop();
    stack->setCurrentWidget(computer);
    filter->setEnabled(false);
    updateStatus();
    if (restoringPlace) {
      const auto generation = placeGeneration;
      QTimer::singleShot(0, this, [this, generation] { if (generation == placeGeneration) restorePlace(); });
    }
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
  if (searchActive()) {
    search->start();
    return;
  }
  if (Fusion::isComputer(location()))
    drives->refresh();
  else {
    notice->hide();
    if (listingFailed) {
      // Failed listings are not necessarily cached by KDirLister. Reload must
      // create a fresh job, including after a cancelled authentication prompt.
      model->openUrl(location(), KDirModel::Reload);
    } else model->dirLister()->updateDirectory(location());
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
  updateFolderMessage();
  previews->updateIcons();
  saveView();
  if (!applyingView) emit viewSettingsChanged();
}
void Browser::setHidden(bool value) {
  model->dirLister()->setShowHiddenFiles(value);
  model->dirLister()->emitChanges();
  updateStatus();
  saveView();
  if (!applyingView) emit viewSettingsChanged();
}
void Browser::setThumbnails(bool enabled) {
  thumbnailsVisible = enabled;
  previews->setPreviewShown(enabled && location().isLocalFile());
  previews->updateIcons();
  saveView();
}
void Browser::selectUrl(const QUrl &url) {
  restoringPlace = false; pendingPlace.clear();
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
  if (applyingView || loadedUrl.isEmpty()) return;
  preferences->setFolderView(loadedUrl, {{"view", viewMode}, {"columns", details->header()->saveState()},
      {"hidden", model->dirLister()->showHiddenFiles()}, {"thumbnails", thumbnailsVisible},
      {"preview", previewVisible}, {"previewWidth", previewWidth}});
}
void Browser::applyFolderView(const QUrl &url) {
  applyingView = true;
  const auto state = preferences->folderView(url);
  const auto columns = state.value("columns", defaultColumns).toByteArray();
  if (!details->header()->restoreState(columns)) details->header()->restoreState(defaultColumns);
  details->setColumnHidden(KDirModel::Name, false);
  previewVisible = state.value("preview", true).toBool();
  previewWidth = qBound(240, state.value("previewWidth", 270).toInt(), 420);
  model->dirLister()->setShowHiddenFiles(state.value("hidden", false).toBool());
  setThumbnails(state.value("thumbnails", true).toBool());
  setView(state.value("view", 2).toInt());
  applyingView = false;
}
void Browser::setPreview(bool visible, int width) {
  previewVisible = visible;
  if (width >= 0) previewWidth = qBound(240, width, 420);
  saveView();
}
void Browser::rememberPlace() {
  if (restoringPlace || loadedUrl.isEmpty()) return;
  QVariantList selected;
  // Keep the folder's own selection even when a search is displayed over it.
  for (const auto &index : view()->selectionModel()->selectedRows())
    selected << model->itemForIndex(proxy->mapToSource(index)).url();
  const auto current = model->itemForIndex(proxy->mapToSource(view()->currentIndex())).url();
  QVariantMap state{{"selected", selected}, {"current", current}, {"filter", filter->text()},
      {"x", view()->horizontalScrollBar()->value()}, {"y", view()->verticalScrollBar()->value()}};
  if (Fusion::isComputer(loadedUrl)) state = computer->place();
  navigator->setVisitState(state);
}
void Browser::restorePlace() {
  if (!restoringPlace) return;
  const auto state = pendingPlace;
  pendingPlace.clear(); restoringPlace = false;
  if (Fusion::isComputer(loadedUrl)) { computer->restorePlace(state); return; }
  QItemSelection selection;
  for (const auto &url : state.value("selected").toList()) {
    const auto index = proxy->mapFromSource(model->indexForUrl(url.toUrl()));
    if (index.isValid()) selection.select(index, index);
  }
  view()->selectionModel()->select(selection, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
  const auto current = proxy->mapFromSource(model->indexForUrl(state.value("current").toUrl()));
  if (current.isValid()) view()->selectionModel()->setCurrentIndex(current, QItemSelectionModel::NoUpdate);
  view()->doItemsLayout();
  view()->horizontalScrollBar()->setValue(state.value("x").toInt());
  view()->verticalScrollBar()->setValue(state.value("y").toInt());
}
QVariantMap Browser::session() { rememberPlace(); saveView(); return navigator->session(); }
void Browser::restoreSession(const QVariantMap &saved) { navigator->restoreSession(saved); }
void Browser::editAddress() {
  navigator->setUrlEditable(true);
  navigator->editor()->setFocus();
  navigator->editor()->lineEdit()->selectAll();
}
bool Browser::searchActive() const { return search && !search->isHidden(); }
void Browser::beginSearch() {
  if (!search) {
    search = new SearchPane(this);
    static_cast<QVBoxLayout *>(layout())->addWidget(search, 1);
    search->hide();
    connect(search, &SearchPane::closeRequested, this, &Browser::closeSearch);
    connect(search, &SearchPane::selectionChanged, this, &Browser::selectionChanged);
    connect(search, &SearchPane::openRequested, this, [this](const QUrl &url, bool directory) {
      emit openRequested(KFileItem(url, QString(), directory ? S_IFDIR : S_IFREG), false);
    });
    connect(search, &SearchPane::revealRequested, this, [this](const QUrl &url) {
      navigate(url.adjusted(QUrl::RemoveFilename | QUrl::StripTrailingSlash));
      selectUrl(url);
    });
  }
  if (!searchActive()) search->setLocation(location());
  stack->hide();
  notice->hide();
  search->show();
  search->focusQuery();
  emit selectionChanged();
}
void Browser::closeSearch() {
  if (!searchActive()) return;
  search->cancel();
  search->hide();
  stack->show();
  view()->setFocus();
  emit selectionChanged();
  updateStatus();
}
QAbstractItemView *Browser::view() const {
  return viewMode == 4 ? static_cast<QAbstractItemView *>(details) : icons;
}
KFileItemList Browser::selectedItems() const {
  KFileItemList items;
  if (searchActive()) {
    for (const auto &url : search->selectedUrls()) items << KFileItem(url);
    return items;
  }
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
  if (searchActive()) { search->results->selectAll(); return; }
  if (!Fusion::isComputer(location())) view()->selectAll();
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
Volume Browser::selectedVolume() const { return searchActive() ? Volume{} : computer->selectedVolume(); }
void Browser::updateCards() {
  computer->refresh();
  if (Fusion::isComputer(location())) updateStatus();
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
  updateFolderMessage();
  if (listingFailed) {
    emit statusChanged(privateFolder ? "This folder is private" : "Folder could not be opened");
    return;
  }
  if (currentFolderAction == FolderAction::ShowHidden) {
    emit statusChanged("Only hidden items · Show hidden files to see them");
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
void Browser::handleListingError(KIO::Job *job) {
  if (Fusion::isComputer(location())) return;
  if (auto *simple = qobject_cast<KIO::SimpleJob *>(job))
    if (!simple->url().matches(location(), QUrl::StripTrailingSlash)) return;
  listingBusy = false;
  listingFailed = true;
  const auto generation = ++accessGeneration;
  privateFolder = location().isLocalFile() && location().host().isEmpty() &&
      job->error() == KIO::ERR_ACCESS_DENIED;
  // KIO errorString may contain HTML. Render it as plain text inside our card.
  QTextDocument description;
  description.setHtml(job->errorString());
  listingError = description.toPlainText();
  if (job->error() == KIO::ERR_USER_CANCELED)
    listingError = "Authentication was cancelled. No access was granted. You can try again or go back.";
  updateStatus();
  if (location().isLocalFile() && location().host().isEmpty() && job->error() == KIO::ERR_CANNOT_ENTER_DIRECTORY) {
    // This KIO error also includes disk/I/O failures. Check actual access off
    // the GUI thread before calling the folder private or offering elevation.
    const auto path = QFile::encodeName(location().toLocalFile());
    auto *probe = new QFutureWatcher<bool>(this);
    connect(probe, &QFutureWatcher<bool>::finished, this, [this, probe, generation] {
      if (listingFailed && generation == accessGeneration) {
        privateFolder = probe->result();
        updateStatus();
      }
      probe->deleteLater();
    });
    probe->setFuture(QtConcurrent::run([path] {
      return ::access(path.constData(), R_OK | X_OK) != 0 && (errno == EACCES || errno == EPERM);
    }));
  }
}
void Browser::updateFolderMessage() {
  if (Fusion::isComputer(location())) return;
  currentFolderAction = FolderAction::None;
  if (listingFailed) {
    if (privateFolder) {
      folderHeading->setText("This folder is private");
      folderExplanation->setText("Unlock it with an administrator account on this running system. "
          "The desktop will ask for your credentials. The mounted system’s login password is not used.\n\n" + listingError);
      folderSymbol->setPixmap(Fusion::icon("folder-locked", "dialog-password").pixmap(48, 48));
      folderAction->setText("Unlock folder…");
      currentFolderAction = FolderAction::Unlock;
    } else {
      folderHeading->setText("Could not open this folder");
      folderExplanation->setText(listingError);
      folderSymbol->setPixmap(Fusion::icon("dialog-warning").pixmap(48, 48));
      folderAction->setText("Try again");
      currentFolderAction = FolderAction::Retry;
    }
  } else if (!listingBusy && proxy->rowCount() == 0 && filter->text().isEmpty() &&
             !model->dirLister()->showHiddenFiles()) {
    const auto all = model->dirLister()->items(KDirLister::AllItems);
    if (!all.isEmpty() && std::all_of(all.cbegin(), all.cend(), [](const KFileItem &item) { return item.isHidden(); })) {
      folderHeading->setText("This folder contains hidden files");
      folderExplanation->setText(QString("%1 hidden item(s) are available here. Linux settings and app data often have names beginning with a dot.\n\nShow hidden files to see them · Ctrl+H").arg(all.size()));
      folderSymbol->setPixmap(Fusion::icon("folder-hidden", "folder").pixmap(48, 48));
      folderAction->setText("Show hidden files");
      currentFolderAction = FolderAction::ShowHidden;
    }
  }
  stack->setCurrentWidget(currentFolderAction == FolderAction::None
      ? static_cast<QWidget *>(view()) : folderMessage);
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
  if (restoringPlace && (watched == icons || watched == details ||
      (icons && watched == icons->viewport()) || (details && watched == details->viewport())) &&
      (event->type() == QEvent::MouseButtonPress || event->type() == QEvent::Wheel || event->type() == QEvent::KeyPress)) {
    restoringPlace = false; pendingPlace.clear();
  }
  if (!icons || !details)
    return QWidget::eventFilter(watched, event);
  if (event->type() == QEvent::KeyPress) {
    auto *key = static_cast<QKeyEvent *>(event);
    if (key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter) {
      for (const auto &item : selectedItems()) emit openRequested(item, false);
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
    const auto item = itemAt(target, drag->position().toPoint());
    const auto destination = !item.isNull() && item.isDir() ? item.url() : location();
    const auto action = Fusion::fileDropDestination(destination)
        ? Fusion::fileDropAction(drag->mimeData(), drag->modifiers(), drag->possibleActions()) : Qt::IgnoreAction;
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
