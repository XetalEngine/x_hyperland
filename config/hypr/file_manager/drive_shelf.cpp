#include "drive_shelf.h"
#include "menu_icons.h"

namespace {
// Long device labels should yield space to controls, while retaining the full
// text for tooltips and accessibility.
class ShelfLabel : public QLabel {
public:
  explicit ShelfLabel(const QString &id, QWidget *parent = nullptr) : QLabel(parent) {
    setObjectName(id); setTextFormat(Qt::PlainText);
    setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
  }
protected:
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this); painter.setFont(font()); painter.setPen(palette().color(foregroundRole()));
    painter.drawText(contentsRect(), Qt::AlignLeft | Qt::AlignVCenter,
                     fontMetrics().elidedText(text(), Qt::ElideRight, contentsRect().width()));
  }
};
QString sizeText(quint64 size) { return QLocale().formattedDataSize(size); }
void repolish(QWidget *widget) {
  widget->style()->unpolish(widget); widget->style()->polish(widget); widget->update();
}
}

VolumeCard::VolumeCard(QWidget *parent) : QFrame(parent) {
  setObjectName("volumeCard"); setFocusPolicy(Qt::StrongFocus);
  setMinimumHeight(104);
  setContextMenuPolicy(Qt::CustomContextMenu);
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
  row = new QHBoxLayout(this); row->setContentsMargins(14, 12, 14, 12); row->setSpacing(14);
  art = new QLabel; art->setObjectName("volumeSymbol"); art->setFixedSize(34, 34);
  row->addWidget(art, 0, Qt::AlignVCenter);
  identity = new QVBoxLayout; identity->setSpacing(4); identity->setAlignment(Qt::AlignVCenter); row->addLayout(identity, 1);
  name = new ShelfLabel("volumeName"); identity->addWidget(name);
  description = new ShelfLabel("volumeDescription"); identity->addWidget(description);
  metrics = new QWidget; metrics->setObjectName("volumeMetrics");
  auto *measure = new QVBoxLayout(metrics); measure->setContentsMargins(0, 3, 0, 0); measure->setSpacing(4);
  usage = new QProgressBar; usage->setObjectName("volumeUsage"); usage->setRange(0, 1000);
  usage->setTextVisible(false); usage->setFixedHeight(5); measure->addWidget(usage);
  space = new ShelfLabel("volumeSpace"); measure->addWidget(space);
  identity->addWidget(metrics);
  auto *actions = new QVBoxLayout; actions->setSpacing(6); row->addLayout(actions);
  status = new QLabel; status->setObjectName("volumeStatusBadge");
  status->setTextFormat(Qt::PlainText); status->setAlignment(Qt::AlignCenter);
  actions->addWidget(status, 0, Qt::AlignRight); actions->addStretch();
  mount = new QPushButton("Mount"); mount->setObjectName("mountVolume"); mount->setMinimumWidth(80);
  auto policy = mount->sizePolicy(); policy.setRetainSizeWhenHidden(true); mount->setSizePolicy(policy);
  mount->installEventFilter(this); actions->addWidget(mount, 0, Qt::AlignRight);
  connect(mount, &QPushButton::clicked, this, [this] { emit selected(); emit mountRequested(); });
}
void VolumeCard::setVolume(const Volume &volume) {
  current = volume; setProperty("device", volume.device);
  name->setText(volume.name); name->setToolTip(volume.name);
  description->setText(volume.mounted() ? volume.mount
      : (volume.filesystem.isEmpty() ? QString("No filesystem") : volume.filesystem.toUpper()) + " · " + sizeText(volume.size));
  description->setToolTip(description->text());
  const bool known = volume.mounted() && volume.spaceKnown && volume.total > 0;
  usage->setVisible(known);
  const int used = known ? qBound(0, int(1000.0 * (1.0 - qMin(1.0, double(volume.available) / volume.total))), 1000) : 0;
  usage->setValue(used); usage->setToolTip(QString::number(qRound(used / 10.0)) + "% used");
  space->setText(known ? sizeText(volume.available) + " free of " + sizeText(volume.total)
      : volume.mounted() ? "Space unavailable" : QString());
  space->setToolTip(space->text());
  metrics->setVisible(volume.mounted());
  status->setText(volume.mounted() ? (volume.readOnly ? "Read only" : "Mounted")
      : volume.locked() ? "Encrypted" : volume.filesystem == "swap" ? "Swap" : "Not mounted");
  mount->setEnabled(!volume.mounted() && volume.mountable());
  mount->setAccessibleName("Mount " + volume.name);
  setAccessibleName(volume.name + " · " + description->text() + " · " + status->text() + " · " + space->text());
  setToolTip(volume.name + '\n' + volume.device + '\n' + description->text());
  art->setPixmap(Fusion::symbolicIcon(volume.usb() ? "drive-removable-media-usb" : "drive-storage").pixmap(34, 34));
  updateMount(); updateGeometry();
}
void VolumeCard::setSelected(bool value) {
  if (property("selected").toBool() == value) return;
  setProperty("selected", value); repolish(this);
}
void VolumeCard::setListMode(bool value) { listMode = value; updateLayout(); }
void VolumeCard::updateLayout() {
  const bool next = listMode && width() >= 600;
  if (compact == next) return;
  compact = next;
  setMinimumHeight(compact ? 80 : 104);
  if (compact) {
    identity->removeWidget(metrics); row->insertWidget(2, metrics, 1);
    metrics->setMinimumWidth(150); metrics->setMaximumWidth(300);
  } else {
    row->removeWidget(metrics); identity->addWidget(metrics);
    metrics->setMinimumWidth(0); metrics->setMaximumWidth(QWIDGETSIZE_MAX);
  }
  updateGeometry();
}
void VolumeCard::updateMount() {
  // Reserve its space so entering a card never moves labels or capacity bars.
  mount->setVisible(mount->isEnabled() && (underMouse() || hasFocus() || mount->hasFocus()));
}
void VolumeCard::mousePressEvent(QMouseEvent *event) {
  if (event->button() == Qt::LeftButton || event->button() == Qt::RightButton) {
    setFocus(Qt::MouseFocusReason); emit selected(); event->accept();
  } else QFrame::mousePressEvent(event);
}
void VolumeCard::mouseDoubleClickEvent(QMouseEvent *event) {
  if (event->button() == Qt::LeftButton) { emit selected(); emit openRequested(); event->accept(); }
  else QFrame::mouseDoubleClickEvent(event);
}
void VolumeCard::keyPressEvent(QKeyEvent *event) {
  if (event->modifiers() == Qt::NoModifier) {
    if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
      emit openRequested(); event->accept(); return;
    }
    if (event->key() == Qt::Key_Left || event->key() == Qt::Key_Up ||
        event->key() == Qt::Key_Right || event->key() == Qt::Key_Down) {
      emit stepRequested(event->key() == Qt::Key_Left || event->key() == Qt::Key_Up ? -1 : 1);
      event->accept(); return;
    }
  }
  QFrame::keyPressEvent(event);
}
void VolumeCard::focusInEvent(QFocusEvent *event) { QFrame::focusInEvent(event); emit selected(); updateMount(); }
void VolumeCard::focusOutEvent(QFocusEvent *event) {
  QFrame::focusOutEvent(event); QTimer::singleShot(0, this, [this] { updateMount(); });
}
void VolumeCard::enterEvent(QEnterEvent *event) { QFrame::enterEvent(event); updateMount(); }
void VolumeCard::leaveEvent(QEvent *event) { QFrame::leaveEvent(event); updateMount(); }
void VolumeCard::resizeEvent(QResizeEvent *event) { QFrame::resizeEvent(event); updateLayout(); }
void VolumeCard::changeEvent(QEvent *event) {
  QFrame::changeEvent(event);
  if (art && event->type() == QEvent::PaletteChange)
    art->setPixmap(Fusion::symbolicIcon(current.usb() ? "drive-removable-media-usb" : "drive-storage").pixmap(34, 34));
}
bool VolumeCard::eventFilter(QObject *object, QEvent *event) {
  if (object == mount && (event->type() == QEvent::FocusIn || event->type() == QEvent::FocusOut))
    QTimer::singleShot(0, this, [this] { updateMount(); });
  return QFrame::eventFilter(object, event);
}

DriveShelf::DriveShelf(Fusion::Preferences *settings, Drives *service, QWidget *parent)
    : QWidget(parent), preferences(settings), drives(service) {
  setObjectName("computerPage");
  auto *layout = new QVBoxLayout(this); layout->setContentsMargins(16, 12, 16, 8); layout->setSpacing(12);
  auto *header = new QHBoxLayout;
  auto *identity = new QVBoxLayout; identity->setSpacing(2);
  auto *title = new QLabel("This PC"); title->setObjectName("computerHeading"); identity->addWidget(title);
  auto *subtitle = new QLabel("Storage and devices"); subtitle->setObjectName("computerSubtitle"); identity->addWidget(subtitle);
  header->addLayout(identity, 1);
  auto *choices = new QButtonGroup(this); choices->setExclusive(true);
  auto choice = [&](const QString &id, const QString &symbol, const QString &label, int mode) {
    auto *button = new QToolButton; button->setObjectName(id); button->setCheckable(true);
    button->setIcon(Fusion::symbolicIcon(symbol)); button->setIconSize({18, 18});
    button->setAccessibleName(label); button->setToolTip(label); choices->addButton(button, mode); header->addWidget(button);
    return button;
  };
  shelfButton = choice("computerShelfView", "view-grid", "Drive shelf", 0);
  listButton = choice("computerListView", "view-list", "Storage list", 1);
  const bool list = preferences->settings.value("computer/listView", false).toBool();
  (list ? listButton : shelfButton)->setChecked(true);
  connect(choices, &QButtonGroup::idClicked, this, [this](int mode) {
    preferences->settings.setValue("computer/listView", mode == 1); queueLayout();
  });
  layout->addLayout(header);
  scroll = new QScrollArea; scroll->setObjectName("computerDrivesScroll"); scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame); scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Ignored); scroll->viewport()->installEventFilter(this);
  body = new QWidget; body->setObjectName("driveShelfBody");
  body->setContextMenuPolicy(Qt::CustomContextMenu);
  connect(body, &QWidget::customContextMenuRequested, this, [this](const QPoint &p) { emit backgroundContextRequested(body->mapToGlobal(p)); });
  grid = new QGridLayout(body); grid->setContentsMargins(0, 0, 4, 0);
  grid->setHorizontalSpacing(24); grid->setVerticalSpacing(20); grid->setAlignment(Qt::AlignTop);
  scroll->setWidget(body); layout->addWidget(scroll, 1);
  empty = new QLabel("No drives detected."); empty->setObjectName("emptyDrives"); layout->addWidget(empty);
  auto *hint = new QLabel("Double-click a volume to open · Right-click for more options"); hint->setObjectName("muted");
  hint->setWordWrap(true); layout->addWidget(hint);
  refresh();
}
QString DriveShelf::expansionKey(const QString &drive) const {
  return "computer/systemExpanded/" + QString::fromLatin1(QCryptographicHash::hash(drive.toUtf8(), QCryptographicHash::Sha256).toHex());
}
void DriveShelf::refresh() {
  QMap<QString, QList<Volume>> inventory;
  for (const auto &volume : drives->volumes) inventory[volume.driveKey()] << volume;
  for (auto it = cards.begin(); it != cards.end();) {
    if (std::none_of(drives->volumes.cbegin(), drives->volumes.cend(), [&](const Volume &v) { return v.device == it.key(); })) {
      delete it.value(); it = cards.erase(it);
    } else ++it;
  }
  // A device can acquire a different physical-parent identity after unlock.
  // Retain its card before removing the old group, just as for a mount change.
  for (const auto &volume : drives->volumes)
    if (auto *card = cards.value(volume.device); card && card->volume().driveKey() != volume.driveKey())
      card->setParent(body);
  for (const auto &key : groups.keys()) if (!inventory.contains(key)) {
    delete groups.take(key).frame; topologyChanged = true;
  }
  auto nextOrder = inventory.keys();
  auto priority = [&](const QString &key) {
    const auto &volumes = inventory[key];
    if (std::any_of(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return v.mounted(); })) return 0;
    if (std::any_of(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return v.usb(); })) return 1;
    return 2;
  };
  std::stable_sort(nextOrder.begin(), nextOrder.end(), [&](const QString &a, const QString &b) { return priority(a) < priority(b); });
  topologyChanged |= order != nextOrder; order = nextOrder;
  for (const auto &key : order) {
    if (!groups.contains(key)) {
      Group group;
      group.frame = new QFrame(body); group.frame->setObjectName("physicalDriveGroup"); group.frame->setProperty("driveKey", key);
      group.frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
      auto *layout = new QVBoxLayout(group.frame); layout->setContentsMargins(0, 12, 0, 2); layout->setSpacing(8);
      auto *header = new QHBoxLayout; header->setContentsMargins(6, 0, 4, 2); header->setSpacing(10);
      group.art = new QLabel; group.art->setFixedSize(24, 24); header->addWidget(group.art);
      auto *identity = new QVBoxLayout; identity->setSpacing(2);
      group.name = new ShelfLabel("driveRowTitle"); group.description = new ShelfLabel("driveRowDescription");
      identity->addWidget(group.name); identity->addWidget(group.description); header->addLayout(identity, 1);
      group.automatic = new QCheckBox("Auto mount"); group.automatic->setObjectName("autoMountDrive");
      group.automatic->setToolTip("Mount this drive's previously approved volumes at sign-in and when reconnected.");
      header->addWidget(group.automatic);
      connect(group.automatic, &QCheckBox::clicked, this, [this, key](bool enabled) { drives->setAutoMount(key, enabled); });
      layout->addLayout(header);
      group.dataLayout = new QVBoxLayout; group.dataLayout->setContentsMargins(0, 0, 0, 0); group.dataLayout->setSpacing(8);
      layout->addLayout(group.dataLayout);
      group.disclosure = new QToolButton; group.disclosure->setObjectName("systemPartitions"); group.disclosure->setCheckable(true);
      group.disclosure->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); group.disclosure->setAutoRaise(true);
      group.disclosure->setChecked(preferences->settings.value(expansionKey(key), false).toBool());
      layout->addWidget(group.disclosure, 0, Qt::AlignLeft);
      group.systemBody = new QWidget; group.systemBody->setObjectName("systemPartitionBody");
      group.systemLayout = new QVBoxLayout(group.systemBody); group.systemLayout->setContentsMargins(0, 0, 0, 0); group.systemLayout->setSpacing(8);
      layout->addWidget(group.systemBody);
      groups.insert(key, group); topologyChanged = true;
      connect(group.disclosure, &QToolButton::toggled, this, [this, key](bool expanded) {
        auto &group = groups[key]; group.systemBody->setVisible(expanded);
        group.disclosure->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow);
        if (!expanded) {
          auto *card = cards.value(selected);
          if (card && group.systemBody->isAncestorOf(card)) {
            auto *first = group.dataLayout->count() ? qobject_cast<VolumeCard *>(group.dataLayout->itemAt(0)->widget()) : nullptr;
            selectDevice(first ? first->volume().device : QString());
          }
        }
        preferences->settings.setValue(expansionKey(key), expanded); queueLayout();
      });
    }
    auto &group = groups[key]; auto volumes = inventory[key];
    std::stable_sort(volumes.begin(), volumes.end(), [](const Volume &a, const Volume &b) { return a.size != b.size ? a.size > b.size : a.device < b.device; });
    const auto &disk = volumes.first();
    group.art->setPixmap(Fusion::symbolicIcon(disk.usb() ? "drive-removable-media-usb" : "drive-storage").pixmap(24, 24));
    group.name->setText(disk.driveModel.isEmpty() ? QFileInfo(key).fileName() : disk.driveModel);
    group.name->setToolTip(group.name->text());
    group.description->setText(key + (disk.driveSize ? " · " + sizeText(disk.driveSize) : QString()) + (disk.usb() ? " · USB" : QString()));
    group.description->setToolTip(group.description->text());
    const auto automatic = drives->autoMountChoice(key);
    { QSignalBlocker block(group.automatic); group.automatic->setVisible(automatic.available);
      group.automatic->setTristate(automatic.state == Qt::PartiallyChecked); group.automatic->setCheckState(automatic.state); }
    int dataIndex = 0, systemIndex = 0;
    for (const auto &volume : volumes) {
      auto *card = cards.value(volume.device);
      if (!card) {
        card = new VolumeCard(group.frame); cards.insert(volume.device, card);
        connect(card, &VolumeCard::selected, this, [this, card] { selectDevice(card->volume().device); });
        connect(card, &VolumeCard::openRequested, this, [this, card] { emit operationRequested(card->volume(), "open"); });
        connect(card, &VolumeCard::mountRequested, this, [this, card] { emit operationRequested(card->volume(), "mount"); });
        connect(card, &VolumeCard::stepRequested, this, [this, card](int delta) { step(card, delta); });
        connect(card, &QWidget::customContextMenuRequested, this, [this, card](const QPoint &p) {
          selectDevice(card->volume().device);
          emit volumeContextRequested(card->volume(), card->mapToGlobal(p.x() < 0 ? card->rect().center() : p));
        });
      }
      card->setVolume(volume);
      auto *destination = volume.compactCard() ? group.systemLayout : group.dataLayout;
      const int index = volume.compactCard() ? systemIndex++ : dataIndex++;
      if (destination->indexOf(card) != index) destination->insertWidget(index, card);
      card->show(); card->setSelected(volume.device == selected);
    }
    group.disclosure->setText(QString("System partitions · %1").arg(systemIndex));
    group.disclosure->setVisible(systemIndex > 0);
    group.disclosure->setArrowType(group.disclosure->isChecked() ? Qt::DownArrow : Qt::RightArrow);
    group.systemBody->setVisible(systemIndex > 0 && group.disclosure->isChecked());
  }
  if (!cards.contains(selected)) selected.clear();
  scroll->setVisible(!groups.isEmpty()); empty->setVisible(groups.isEmpty()); queueLayout();
}
Volume DriveShelf::selectedVolume() const { return cards.contains(selected) ? cards[selected]->volume() : Volume{}; }
void DriveShelf::selectDevice(const QString &device, bool focus) {
  selected = cards.contains(device) ? device : QString();
  for (auto *card : cards) card->setSelected(card->volume().device == selected);
  if (auto *card = cards.value(selected)) {
    if (card->volume().compactCard()) groups[card->volume().driveKey()].disclosure->setChecked(true);
    if (focus) { card->setFocus(Qt::OtherFocusReason); scroll->ensureWidgetVisible(card, 0, 12); }
  }
}
QVariantMap DriveShelf::place() const { return {{"volume", selected}, {"y", scroll->verticalScrollBar()->value()}}; }
void DriveShelf::restorePlace(const QVariantMap &state) {
  selectDevice(state.value("volume").toString()); relayout();
  scroll->verticalScrollBar()->setValue(state.value("y").toInt());
}
void DriveShelf::step(VolumeCard *from, int delta) {
  QList<VolumeCard *> visible;
  for (const auto &key : order) {
    const auto &group = groups[key];
    for (auto *layout : {group.dataLayout, group.systemLayout})
      for (int i = 0; i < layout->count(); ++i)
        if (auto *card = qobject_cast<VolumeCard *>(layout->itemAt(i)->widget()); card && card->isVisible()) visible << card;
  }
  const int index = visible.indexOf(from) + delta;
  if (index >= 0 && index < visible.size()) selectDevice(visible[index]->volume().device, true);
}
void DriveShelf::queueLayout() {
  if (layoutQueued) return;
  layoutQueued = true; QTimer::singleShot(0, this, [this] { layoutQueued = false; relayout(); });
}
void DriveShelf::relayout() {
  const int next = listButton->isChecked() ? 1 : qMax(1, (scroll->viewport()->width() + 24) / (400 + 24));
  for (auto *card : cards) card->setListMode(listButton->isChecked());
  if (next != columns || topologyChanged) {
    const auto focused = QPointer<QWidget>(QApplication::focusWidget());
    while (auto *item = grid->takeAt(0)) delete item;
    for (int i = 0; i < qMax(columns, next); ++i) grid->setColumnStretch(i, i < next ? 1 : 0);
    columns = next; topologyChanged = false;
    for (int i = 0; i < order.size(); ++i) grid->addWidget(groups[order[i]].frame, i / columns, i % columns, Qt::AlignTop);
    if (focused && isAncestorOf(focused)) focused->setFocus(Qt::OtherFocusReason);
  }
  grid->activate(); body->setMinimumHeight(grid->minimumSize().height());
}
bool DriveShelf::eventFilter(QObject *object, QEvent *event) {
  if (object == scroll->viewport() && (event->type() == QEvent::Resize || event->type() == QEvent::Show)) queueLayout();
  return QWidget::eventFilter(object, event);
}
void DriveShelf::changeEvent(QEvent *event) {
  QWidget::changeEvent(event);
  if (event->type() == QEvent::PaletteChange || event->type() == QEvent::FontChange || event->type() == QEvent::StyleChange) {
    if (shelfButton) shelfButton->setIcon(Fusion::symbolicIcon("view-grid"));
    if (listButton) listButton->setIcon(Fusion::symbolicIcon("view-list"));
    if (body) QTimer::singleShot(0, this, [this] { refresh(); });
  }
}
