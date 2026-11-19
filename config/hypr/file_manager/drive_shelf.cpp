#include "drive_shelf.h"
#include "menu_icons.h"

namespace {
constexpr int tileWidth = 380, tileHeight = 120, rowGap = 10, columnGap = 18;
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
class SectionHeading : public QLabel {
protected:
  void paintEvent(QPaintEvent *event) override {
    QLabel::paintEvent(event);
    QPainter painter(this); painter.setPen(palette().color(QPalette::Midlight));
    const int columns = property("fixedColumns").toInt();
    if (columns > 0) {
      for (int column = 0; column < columns; ++column) {
        const int left = column * (tileWidth + columnGap);
        painter.drawLine(left, height() - 1, left + tileWidth - 1, height() - 1);
      }
    } else painter.drawLine(0, height() - 1, width() - 1, height() - 1);
  }
};
QString sizeText(quint64 size) { return QLocale().formattedDataSize(size); }
QString partitionSymbol(const Volume &volume) {
  if (volume.filesystem == "swap") return "partition-swap";
  const auto type = volume.partitionType.toLower();
  if (type == "de94bba4-06d1-4d40-a16a-bfd50179d6ac") return "partition-recovery";
  if (type == "e3c9e316-0b5c-4db8-817d-f92df00215ae") return "partition-reserved";
  return "partition-boot";
}
QString partitionTitle(const Volume &volume) {
  if (volume.filesystem == "swap") return "Swap partition";
  const auto type = volume.partitionType.toLower();
  if (type == "de94bba4-06d1-4d40-a16a-bfd50179d6ac") return "Recovery partition";
  if (type == "e3c9e316-0b5c-4db8-817d-f92df00215ae") return "Reserved partition";
  if (type == "21686148-6449-6e6f-744e-656564454649") return "BIOS boot partition";
  if (type == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b" || volume.filesystem.startsWith("fat") || volume.filesystem == "vfat")
    return "EFI boot partition";
  return "System partition";
}
void repolish(QWidget *widget) {
  widget->style()->unpolish(widget); widget->style()->polish(widget); widget->update();
}
}

VolumeCard::VolumeCard(QWidget *parent) : QFrame(parent) {
  setObjectName("volumeCard"); setFocusPolicy(Qt::StrongFocus);
  setContextMenuPolicy(Qt::CustomContextMenu);
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
  row = new QHBoxLayout(this); row->setContentsMargins(2, 3, 2, 3); row->setSpacing(10);
  art = new QLabel; art->setObjectName("volumeSymbol"); art->setFixedSize(30, 30);
  row->addWidget(art, 0, Qt::AlignVCenter);
  identityBody = new QWidget; identityBody->setObjectName("volumeIdentity");
  identity = new QVBoxLayout(identityBody); identity->setContentsMargins(0, 0, 0, 0);
  identity->setSpacing(2); identity->setAlignment(Qt::AlignVCenter); row->addWidget(identityBody, 1);
  name = new ShelfLabel("volumeName"); identity->addWidget(name);
  description = new ShelfLabel("volumeDescription"); identity->addWidget(description);
  metrics = new QWidget; metrics->setObjectName("volumeMetrics");
  auto *measure = new QVBoxLayout(metrics); measure->setContentsMargins(0, 2, 0, 0); measure->setSpacing(3);
  usage = new QProgressBar; usage->setObjectName("volumeUsage"); usage->setRange(0, 1000);
  usage->setTextVisible(false); usage->setFixedHeight(4); measure->addWidget(usage);
  space = new ShelfLabel("volumeSpace"); measure->addWidget(space); identity->addWidget(metrics);
  actionsBody = new QWidget; actionsBody->setObjectName("volumeActions");
  actionsBody->setSizePolicy(QSizePolicy::Maximum, QSizePolicy::Fixed);
  actionStack = new QStackedLayout(actionsBody); actionStack->setContentsMargins(0, 0, 0, 0);
  status = new QLabel; status->setObjectName("volumeStatusBadge");
  status->setTextFormat(Qt::PlainText); status->setAlignment(Qt::AlignCenter); actionStack->addWidget(status);
  mount = new QPushButton("Mount"); mount->setObjectName("mountVolume"); mount->setMinimumWidth(66);
  mount->installEventFilter(this); actionStack->addWidget(mount);
  row->addWidget(actionsBody, 0, Qt::AlignVCenter);
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
      : volume.mounted() && !volume.prefix() ? "Space unavailable" : QString());
  space->setToolTip(space->text());
  metrics->setVisible(!partitionMode && volume.mounted() && !volume.prefix());
  status->setText(volume.mount == "/" ? "System drive" : volume.prefix() ? (volume.type == "steam-prefix" ? "Steam" : "Wine / Proton")
      : volume.mounted() ? (volume.readOnly ? "Read only" : "Mounted")
      : volume.locked() ? "Encrypted" : volume.filesystem == "swap" ? "Swap" : "Not mounted");
  mount->setEnabled(!volume.mounted() && volume.mountable());
  mount->setAccessibleName("Mount " + volume.name);
  const auto role = volume.compactCard() ? partitionTitle(volume) + " · " : QString();
  setAccessibleName(role + volume.name + " · " + description->text() + " · " + status->text() + " · " + space->text());
  setToolTip(role + volume.name + '\n' + volume.device + '\n' + description->text()
      + (volume.size ? "\n" + sizeText(volume.size) : QString())
      + "\nDouble-click to open · Right-click for options");
  updateIcon();
  updateMount(); updateLayout(); updateGeometry();
}
void VolumeCard::setSelected(bool value) {
  if (property("selected").toBool() == value) return;
  setProperty("selected", value); repolish(this);
}
void VolumeCard::setListMode(bool value) { listMode = value; updateLayout(); }
void VolumeCard::setOriginalMode(bool value) {
  if (originalMode == value) return;
  originalMode = value; setProperty("original", value);
  row->setContentsMargins(value ? 14 : 2, value ? 10 : 3, value ? 14 : 2, value ? 10 : 3);
  updateLayout(); repolish(this);
}
void VolumeCard::setPartitionMode(bool value) {
  if (partitionMode == value) return;
  partitionMode = value; setProperty("partitionIcon", value);
  setMinimumSize(value ? QSize(28, 28) : QSize(0, 0));
  setMaximumSize(value ? QSize(28, 28) : QSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX));
  setSizePolicy(value ? QSizePolicy::Fixed : QSizePolicy::Expanding,
                value ? QSizePolicy::Fixed : QSizePolicy::Maximum);
  art->setFixedSize(value ? QSize(18, 18) : QSize(30, 30));
  updateIcon();
  identityBody->setVisible(!value); actionsBody->setVisible(!value);
  metrics->setVisible(!value && current.mounted() && !current.prefix());
  updateLayout(); updateMount(); repolish(this);
}
void VolumeCard::updateLayout() {
  const bool next = !partitionMode && listMode && width() >= 600;
  if (compact != next) {
    compact = next;
    if (compact) {
      identity->removeWidget(metrics); row->insertWidget(2, metrics, 1);
      metrics->setMinimumWidth(150); metrics->setMaximumWidth(300);
    } else {
      row->removeWidget(metrics); identity->addWidget(metrics);
      metrics->setMinimumWidth(0); metrics->setMaximumWidth(QWIDGETSIZE_MAX);
    }
  }
  if (!partitionMode) setMinimumHeight(originalMode ? 104 : compact ? 42 : current.mounted() && !current.prefix() ? 62 : 42);
  updateGeometry();
}
void VolumeCard::updateMount() {
  // Swap the badge for Mount in the same space; hover never changes the row size.
  const bool show = !partitionMode && mount->isEnabled() && (underMouse() || hasFocus() || mount->hasFocus());
  actionStack->setCurrentWidget(show ? static_cast<QWidget *>(mount) : status);
}
void VolumeCard::updateIcon() {
  art->setPixmap(Fusion::symbolicIcon(partitionMode ? partitionSymbol(current)
      : current.mount == "/" ? "drive-linux" : current.symbol()).pixmap(art->size()));
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
    updateIcon();
}
bool VolumeCard::eventFilter(QObject *object, QEvent *event) {
  if (object == mount && (event->type() == QEvent::FocusIn || event->type() == QEvent::FocusOut))
    QTimer::singleShot(0, this, [this] { updateMount(); });
  return QFrame::eventFilter(object, event);
}

DriveShelf::DriveShelf(Fusion::Preferences *settings, Drives *service, QWidget *parent)
    : QWidget(parent), preferences(settings), drives(service) {
  setObjectName("computerPage");
  setAttribute(Qt::WA_StyledBackground);
  auto *layout = new QVBoxLayout(this); layout->setContentsMargins(14, 10, 14, 8); layout->setSpacing(8);
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
  originalButton = choice("computerOriginalView", "view-shelf", "Original layout", 2);
  shelfButton = choice("computerShelfView", "view-grid", "Fixed-size cards", 0);
  listButton = choice("computerListView", "view-list", "Storage list", 1);
  const auto view = preferences->settings.value("computer/viewMode",
      preferences->settings.value("computer/listView", false).toBool() ? "list" : "tiles").toString();
  (view == "original" ? originalButton : view == "list" ? listButton : shelfButton)->setChecked(true);
  connect(choices, &QButtonGroup::idClicked, this, [this](int mode) {
    preferences->settings.setValue("computer/viewMode", mode == 2 ? "original" : mode == 1 ? "list" : "tiles");
    preferences->settings.setValue("computer/listView", mode == 1);
    topologyChanged = true; refresh();
  });
  layout->addLayout(header);
  scroll = new QScrollArea; scroll->setObjectName("computerDrivesScroll"); scroll->setWidgetResizable(true);
  scroll->viewport()->setObjectName("computerDrivesViewport");
  scroll->setFrameShape(QFrame::NoFrame); scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Ignored); scroll->viewport()->installEventFilter(this);
  body = new QWidget; body->setObjectName("driveShelfBody");
  body->setContextMenuPolicy(Qt::CustomContextMenu);
  connect(body, &QWidget::customContextMenuRequested, this, [this](const QPoint &p) { emit backgroundContextRequested(body->mapToGlobal(p)); });
  grid = new QGridLayout(body); grid->setContentsMargins(0, 0, 4, 0);
  grid->setHorizontalSpacing(columnGap); grid->setVerticalSpacing(16); grid->setAlignment(Qt::AlignTop);
  for (const int category : {0, 2, 3, 5}) {
    Section section; section.body = new QWidget(body); section.body->setObjectName("driveSection");
    section.body->setProperty("driveCategory", category);
    section.body->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    auto *layout = new QVBoxLayout(section.body); layout->setContentsMargins(0, 0, 0, 0); layout->setSpacing(8);
    section.heading = new SectionHeading; section.heading->setObjectName("driveSectionHeading");
    section.heading->setTextFormat(Qt::PlainText); layout->addWidget(section.heading);
    section.items = new QGridLayout; section.items->setContentsMargins(0, 0, 0, 0);
    section.items->setHorizontalSpacing(columnGap); section.items->setVerticalSpacing(rowGap); section.items->setAlignment(Qt::AlignTop | Qt::AlignLeft); layout->addLayout(section.items);
    sections.insert(category, section);
  }
  scroll->setWidget(body);
  body->setAutoFillBackground(false); scroll->viewport()->setAutoFillBackground(false);
  layout->addWidget(scroll, 1);
  empty = new QLabel("No drives detected."); empty->setObjectName("emptyDrives"); layout->addWidget(empty);
  auto *hint = new QLabel("Double-click a volume to open · Right-click for more options"); hint->setObjectName("muted");
  hint->setWordWrap(true); layout->addWidget(hint);
  refresh();
}
QString DriveShelf::expansionKey(const QString &drive) const {
  return "computer/systemExpanded/" + QString::fromLatin1(QCryptographicHash::hash(drive.toUtf8(), QCryptographicHash::Sha256).toHex());
}
void DriveShelf::refresh() {
  const bool original = originalButton->isChecked(), list = listButton->isChecked();
  const auto focused = QPointer<QWidget>(QApplication::focusWidget());
  const auto selectedBeforeRefresh = selected;
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
    if (std::any_of(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return v.mount == "/"; })) return 0;
    if (volumes.first().prefix()) return volumes.first().type == "wine-prefix" ? 3 : 4;
    if (std::any_of(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return v.mounted(); })) return 1;
    if (std::any_of(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return v.removableMedia(); })) return 2;
    return 5;
  };
  QMap<QString, int> nextCategories;
  for (const auto &key : nextOrder) nextCategories[key] = priority(key);
  topologyChanged |= categories != nextCategories; categories = nextCategories;
  std::stable_sort(nextOrder.begin(), nextOrder.end(), [&](const QString &a, const QString &b) {
    if (categories[a] != categories[b]) return categories[a] < categories[b];
    const auto &first = inventory[a].first(), &second = inventory[b].first();
    if (first.mediaPriority() != second.mediaPriority()) return first.mediaPriority() < second.mediaPriority();
    const int comparison = QString::localeAwareCompare(first.driveModel, second.driveModel);
    return comparison ? comparison < 0 : a < b;
  });
  topologyChanged |= order != nextOrder; order = nextOrder;
  for (const auto &key : order) {
    if (!groups.contains(key)) {
      Group group;
      group.frame = new QFrame(body); group.frame->setObjectName("physicalDriveGroup"); group.frame->setProperty("driveKey", key);
      group.frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
      group.layout = new QVBoxLayout(group.frame); group.layout->setContentsMargins(0, 0, 0, 0); group.layout->setSpacing(8);
      group.heading = new QWidget(group.frame); group.heading->setObjectName("physicalDriveHeading");
      auto *header = new QHBoxLayout(group.heading); header->setContentsMargins(2, 0, 2, 0); header->setSpacing(6);
      group.art = new QLabel; group.art->setFixedSize(24, 24); header->addWidget(group.art);
      auto *identity = new QVBoxLayout; identity->setContentsMargins(0, 0, 0, 0); identity->setSpacing(2);
      group.name = new ShelfLabel("driveRowTitle"); group.description = new ShelfLabel("driveRowDescription");
      identity->addWidget(group.name); identity->addWidget(group.description); header->addLayout(identity, 1);
      group.systemBody = new QWidget(group.heading); group.systemBody->setObjectName("systemPartitionIcons");
      group.systemBody->setAccessibleName("System partitions");
      group.systemLayout = new QBoxLayout(QBoxLayout::LeftToRight, group.systemBody);
      group.systemLayout->setContentsMargins(0, 0, 0, 0); group.systemLayout->setSpacing(3);
      header->addWidget(group.systemBody);
      group.automatic = new QCheckBox("Auto mount"); group.automatic->setObjectName("autoMountDrive");
      group.automatic->setToolTip("Mount this drive's previously approved volumes at sign-in and when reconnected.");
      header->addWidget(group.automatic);
      connect(group.automatic, &QCheckBox::clicked, this, [this, key](bool enabled) { drives->setAutoMount(key, enabled); });
      group.dataLayout = new QVBoxLayout; group.dataLayout->setContentsMargins(0, 0, 0, 0); group.dataLayout->setSpacing(rowGap);
      group.layout->addLayout(group.dataLayout);
      group.disclosure = new QToolButton; group.disclosure->setObjectName("systemPartitions"); group.disclosure->setCheckable(true);
      group.disclosure->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); group.disclosure->setAutoRaise(true);
      group.disclosure->setChecked(preferences->settings.value(expansionKey(key), false).toBool());
      group.layout->addWidget(group.disclosure, 0, Qt::AlignLeft);
      connect(group.disclosure, &QToolButton::toggled, this, [this, key](bool expanded) {
        auto &group = groups[key]; group.systemBody->setVisible(expanded);
        group.disclosure->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow);
        if (!expanded) {
          auto *card = cards.value(selected);
          if (card && group.systemBody->isAncestorOf(card)) {
            QString first;
            for (const auto &device : group.volumes)
              if (auto *candidate = cards.value(device); candidate && !candidate->volume().compactCard()) { first = device; break; }
            selectDevice(first);
          }
        }
        preferences->settings.setValue(expansionKey(key), expanded); queueLayout();
      });
      groups.insert(key, group); topologyChanged = true;
    }
    auto &group = groups[key]; auto volumes = inventory[key];
    std::stable_sort(volumes.begin(), volumes.end(), [](const Volume &a, const Volume &b) {
      if ((a.mount == "/") != (b.mount == "/")) return a.mount == "/";
      if (a.mounted() != b.mounted()) return a.mounted();
      return a.size != b.size ? a.size > b.size : a.device < b.device;
    });
    group.volumes.clear();
    for (const auto &volume : volumes) group.volumes << volume.device;
    for (const auto &device : group.tiles.keys()) if (!group.volumes.contains(device)) {
      if (group.tiles[device].frame->isAncestorOf(group.heading)) group.heading->setParent(group.frame);
      delete group.tiles.take(device).frame;
    }
    const auto primary = std::find_if(volumes.cbegin(), volumes.cend(), [](const Volume &v) { return !v.compactCard(); });
    // A standalone swap/boot device still gets a full tile (for example zram0).
    const auto primaryDevice = primary == volumes.cend() ? volumes.first().device : primary->device;
    const auto &disk = volumes.first();
    const auto model = disk.driveModel.isEmpty() ? QFileInfo(key).fileName() : disk.driveModel;
    group.frame->setProperty("original", original);
    group.frame->setMinimumWidth(original || list ? 0 : tileWidth);
    group.frame->setMaximumWidth(original || list ? QWIDGETSIZE_MAX : tileWidth);
    group.layout->setContentsMargins(0, original ? 12 : 0, 0, original ? 2 : 0);
    group.heading->setMinimumHeight(original ? 0 : 28);
    group.heading->setMaximumHeight(original ? QWIDGETSIZE_MAX : 28);
    group.name->setText(model);
    const auto detail = key + (disk.driveSize ? " · " + sizeText(disk.driveSize) : QString())
        + (disk.optical() ? " · Optical" : disk.legacyMedia() ? " · Removable media" : disk.usb() ? " · USB" : QString());
    group.name->setToolTip(model + '\n' + detail); group.description->setText(detail); group.description->setToolTip(detail);
    group.art->setPixmap(Fusion::symbolicIcon(disk.symbol()).pixmap(24, 24));
    group.art->setVisible(original); group.description->setVisible(original);
    const auto automatic = drives->autoMountChoice(key);
    { QSignalBlocker block(group.automatic); group.automatic->setVisible(automatic.available);
      group.automatic->setTristate(automatic.state == Qt::PartiallyChecked); group.automatic->setCheckState(automatic.state); }
    if (original) {
      if (group.layout->indexOf(group.heading) != 0) group.layout->insertWidget(0, group.heading);
      if (group.layout->indexOf(group.systemBody) < 0) group.layout->addWidget(group.systemBody);
    } else {
      auto *header = qobject_cast<QHBoxLayout *>(group.heading->layout());
      if (header->indexOf(group.systemBody) < 0) header->insertWidget(2, group.systemBody);
    }
    group.systemLayout->setDirection(original ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    group.systemLayout->setSpacing(original ? 8 : 3);
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
      const bool helper = volume.compactCard() && (original || volume.device != primaryDevice);
      card->setVolume(volume); card->setOriginalMode(original); card->setListMode(list); card->setPartitionMode(helper && !original);
      if (helper) {
        if (group.systemLayout->indexOf(card) != systemIndex) group.systemLayout->insertWidget(systemIndex, card);
        ++systemIndex;
        if (group.tiles.contains(volume.device)) group.tiles[volume.device].frame->hide();
      } else {
        if (!group.tiles.contains(volume.device)) {
          Tile tile; tile.frame = new QFrame(group.frame); tile.frame->setObjectName("driveTile"); tile.frame->setProperty("device", volume.device);
          tile.layout = new QVBoxLayout(tile.frame); tile.layout->setSpacing(4);
          tile.heading = new ShelfLabel("driveRowTitle"); tile.heading->setFixedHeight(28); tile.layout->addWidget(tile.heading);
          group.tiles.insert(volume.device, tile);
        }
        auto &tile = group.tiles[volume.device]; tile.frame->setProperty("original", original);
        tile.frame->setMinimumSize(original ? QSize(0, 0) : QSize(list ? 0 : tileWidth, tileHeight));
        tile.frame->setMaximumSize(original ? QSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX) : QSize(list ? QWIDGETSIZE_MAX : tileWidth, tileHeight));
        tile.layout->setContentsMargins(original ? 0 : 10, original ? 0 : 8, original ? 0 : 10, original ? 0 : 8);
        tile.heading->setText(model); tile.heading->setToolTip(group.name->toolTip());
        tile.heading->setVisible(!original && volume.device != primaryDevice);
        if (!original && volume.device == primaryDevice && tile.layout->indexOf(group.heading) < 0) tile.layout->insertWidget(0, group.heading);
        if (tile.layout->indexOf(card) < 0) tile.layout->addWidget(card, 1);
        if (group.dataLayout->indexOf(tile.frame) != dataIndex) group.dataLayout->insertWidget(dataIndex, tile.frame);
        ++dataIndex; tile.frame->show(); repolish(tile.frame);
      }
      card->show(); card->setSelected(volume.device == selected);
    }
    group.heading->setVisible(!disk.prefix());
    group.disclosure->setText(QString("System partitions · %1").arg(systemIndex));
    group.disclosure->setArrowType(group.disclosure->isChecked() ? Qt::DownArrow : Qt::RightArrow);
    group.disclosure->setVisible(original && systemIndex > 0);
    group.systemBody->setVisible(systemIndex > 0 && (!original || group.disclosure->isChecked()));
    group.systemBody->setToolTip(original ? QString() : QString("%1 system partitions · Hover for details, right-click for options").arg(systemIndex));
    repolish(group.frame); repolish(group.name); repolish(group.description);
  }
  selectDevice(selectedBeforeRefresh);
  if (focused && isAncestorOf(focused) && focused->isVisible()) focused->setFocus(Qt::OtherFocusReason);
  scroll->setVisible(!groups.isEmpty()); empty->setVisible(groups.isEmpty()); queueLayout();
  // A scan can change usage or mount state without changing the selected device.
  if (selected == selectedBeforeRefresh) emit selectionChanged();
}
Volume DriveShelf::selectedVolume() const { return cards.contains(selected) ? cards[selected]->volume() : Volume{}; }
void DriveShelf::selectDevice(const QString &device, bool focus) {
  const auto previous = selected;
  selected = cards.contains(device) ? device : QString();
  for (auto *card : cards) card->setSelected(card->volume().device == selected);
  if (auto *card = cards.value(selected)) {
    if (originalButton->isChecked() && card->volume().compactCard())
      groups[card->volume().driveKey()].disclosure->setChecked(true);
    if (focus) {
      // Put the card in its final section before assigning keyboard focus.
      // Reparenting a just-shown card would otherwise discard Qt's pending focus.
      if (layoutQueued || topologyChanged) relayout();
      card->setFocus(Qt::OtherFocusReason); scroll->ensureWidgetVisible(card, 0, 12);
    }
  }
  if (selected != previous) emit selectionChanged();
}
QVariantMap DriveShelf::place() const { return {{"volume", selected}, {"y", scroll->verticalScrollBar()->value()}}; }
void DriveShelf::restorePlace(const QVariantMap &state) {
  selectDevice(state.value("volume").toString()); relayout();
  scroll->verticalScrollBar()->setValue(state.value("y").toInt());
}
void DriveShelf::step(VolumeCard *from, int delta) {
  QList<VolumeCard *> visible;
  for (const auto &key : order)
    for (bool helpers : {false, true})
      for (const auto &device : groups[key].volumes)
        if (auto *card = cards.value(device); card && card->isVisible() && card->volume().compactCard() == helpers)
          visible << card;
  const int index = visible.indexOf(from) + delta;
  if (index >= 0 && index < visible.size()) selectDevice(visible[index]->volume().device, true);
}
void DriveShelf::queueLayout() {
  if (layoutQueued) return;
  layoutQueued = true; QTimer::singleShot(0, this, [this] { layoutQueued = false; relayout(); });
}
void DriveShelf::relayout() {
  const int width = qMax(1, scroll->viewport()->width() - 4);
  const bool list = listButton->isChecked(), original = originalButton->isChecked();
  const bool fixed = !list && !original;
  const int span = original ? 400 : tileWidth;
  const int next = list ? 1 : qMax(1, (width + columnGap) / (span + columnGap));
  const bool paired = fixed && width >= 2 * tileWidth + columnGap &&
      (categories.values().contains(0) || categories.values().contains(1)) && categories.values().contains(2);
  const int nextRemovable = list ? 1 : qMax(1, ((paired ? width - tileWidth - columnGap : width) + columnGap) / (span + columnGap));
  for (auto *card : cards) card->setListMode(list);
  if (next != columns || nextRemovable != removableColumns || paired != sideBySide || topologyChanged) {
    const auto focused = QPointer<QWidget>(QApplication::focusWidget());
    const auto selectedBeforeLayout = selected;
    while (auto *item = grid->takeAt(0)) delete item;
    QMap<int, QStringList> members;
    for (const auto &key : order) {
      const int priority = categories.value(key, 5);
      members[priority == 1 ? 0 : priority == 4 ? 3 : priority] << key;
    }
    const QMap<int, QString> titles{{0, categories.values().contains(0) ? "System & mounted devices" : "Mounted devices"},
        {2, "Removable devices"}, {3, "Wine, Proton & Steam prefixes"}, {5, "Unmounted devices"}};
    for (auto it = sections.begin(); it != sections.end(); ++it) {
      auto &section = it.value();
      while (auto *item = section.items->takeAt(0)) delete item;
      const int sectionWidth = paired && it.key() == 0 ? tileWidth : paired && it.key() == 2 ? width - tileWidth - columnGap : width;
      // Mounted disks always stack below the system disk. Other sections wrap.
      const int count = list || (fixed && it.key() == 0) ? 1 : qMax(1, (sectionWidth + columnGap) / (span + columnGap));
      section.items->setAlignment(fixed ? Qt::AlignTop | Qt::AlignLeft : Qt::AlignTop);
      for (int c = 0; c < qMax(section.items->columnCount(), count); ++c) {
        section.items->setColumnStretch(c, !fixed && c < count ? 1 : 0);
        section.items->setColumnMinimumWidth(c, fixed && c < count ? tileWidth : 0);
      }
      int index = 0;
      for (const auto &key : members[it.key()]) {
        auto *frame = groups[key].frame; frame->setProperty("driveCategory", categories[key]);
        section.items->addWidget(frame, index / count, index % count, Qt::AlignTop); frame->show(); ++index;
      }
      section.heading->setText(titles[it.key()]);
      section.heading->setProperty("fixedColumns", fixed ? qMin(count, members[it.key()].size()) : 0);
      section.heading->update(); section.body->setVisible(!members[it.key()].isEmpty());
    }
    int row = 0;
    if (paired) {
      grid->addWidget(sections[0].body, row, 0, Qt::AlignTop);
      grid->addWidget(sections[2].body, row++, 1, Qt::AlignTop);
    } else {
      for (int category : {0, 2}) if (!members[category].isEmpty()) grid->addWidget(sections[category].body, row++, 0, 1, 2, Qt::AlignTop);
    }
    for (int category : {3, 5}) if (!members[category].isEmpty()) grid->addWidget(sections[category].body, row++, 0, 1, 2, Qt::AlignTop);
    grid->setColumnMinimumWidth(0, paired ? tileWidth : 0); grid->setColumnMinimumWidth(1, 0);
    grid->setColumnStretch(0, paired ? 0 : 1); grid->setColumnStretch(1, paired ? 1 : 0);
    columns = next; removableColumns = nextRemovable; sideBySide = paired; topologyChanged = false;
    selectDevice(selectedBeforeLayout);
    if (focused && isAncestorOf(focused) && focused->isVisible()) focused->setFocus(Qt::OtherFocusReason);
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
    if (originalButton) originalButton->setIcon(Fusion::symbolicIcon("view-shelf"));
    if (listButton) listButton->setIcon(Fusion::symbolicIcon("view-list"));
    if (body) QTimer::singleShot(0, this, [this] { refresh(); });
  }
}
