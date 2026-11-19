#include "drive_properties.h"
#include "core.h"
#include "menu_icons.h"

namespace {
QColor usedColor() {
  const auto accent = qApp->property("fusionAccent").value<QColor>();
  return accent.isValid() ? accent : qApp->palette().color(QPalette::Highlight);
}
QColor freeColor() {
  QColor color = qApp->palette().color(QPalette::WindowText);
  color.setAlpha(70);
  return color;
}
QColor reservedColor() { return QColor("#d9aa57"); }
QString exactBytes(quint64 bytes) {
  return QLocale().toString(bytes) + " bytes";
}
struct StorageUsage {
  bool known;
  quint64 total, available, occupied, held;
};
StorageUsage storageUsage(const Volume &volume, bool connected = true) {
  const bool known = connected && !volume.prefix() && volume.mounted() && volume.total > 0;
  const quint64 total = volume.prefix() ? 0 : known ? volume.total : volume.size;
  const quint64 available = qMin(volume.available, total);
  const quint64 unoccupied = qBound(
      available, volume.spaceKnown ? volume.freeBytes : available, total);
  return {known, total, available, total - unoccupied, unoccupied - available};
}
QLabel *label(const QString &text, const QString &name = {}) {
  auto *result = new QLabel(text);
  result->setObjectName(name);
  result->setTextFormat(Qt::PlainText);
  result->setWordWrap(true);
  result->setTextInteractionFlags(Qt::TextSelectableByMouse);
  return result;
}
class Swatch : public QWidget {
public:
  explicit Swatch(int role) : role(role) { setFixedSize(10, 10); }

protected:
  void paintEvent(QPaintEvent *) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(Qt::NoPen);
    p.setBrush(role == 0   ? usedColor()
               : role == 1 ? freeColor()
                           : reservedColor());
    p.drawRoundedRect(rect(), 3, 3);
  }

private:
  int role;
};
} // namespace

class StorageChart : public QWidget {
public:
  explicit StorageChart(QWidget *parent = nullptr) : QWidget(parent) {
    setObjectName("storageChart");
    setAccessibleName("Storage usage");
    setFixedSize(176, 176);
  }
  void setUsage(bool available, quint64 capacity, quint64 used,
                quint64 reserved) {
    known = available;
    total = capacity;
    occupied = used;
    held = reserved;
    setAccessibleDescription(
        known ? QString("%1 used of %2")
                    .arg(exactBytes(occupied), exactBytes(total))
              : "Usage unavailable");
    update();
  }

protected:
  void paintEvent(QPaintEvent *) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    const int side = qMin(width(), height()) - 30;
    const QRectF ring((width() - side) / 2.0, (height() - side) / 2.0, side,
                      side);
    QColor halo = usedColor();
    halo.setAlpha(22);
    QRadialGradient glow(rect().center(), width() / 2.0);
    glow.setColorAt(0, halo);
    halo.setAlpha(0);
    glow.setColorAt(1, halo);
    p.setPen(Qt::NoPen);
    p.setBrush(glow);
    p.drawEllipse(rect());
    p.setBrush(Qt::NoBrush);
    p.setPen(QPen(freeColor(), 12));
    p.drawEllipse(ring);
    if (known && total) {
      const int usedArc = qRound(5760.0 * occupied / total);
      const int reservedArc = qRound(5760.0 * held / total);
      QLinearGradient accent(ring.topLeft(), ring.bottomRight());
      accent.setColorAt(0, usedColor().lighter(125));
      accent.setColorAt(1, usedColor());
      p.setPen(QPen(QBrush(accent), 12, Qt::SolidLine, Qt::FlatCap));
      p.drawArc(ring, 90 * 16, -usedArc);
      if (held) {
        p.setPen(QPen(reservedColor(), 12, Qt::SolidLine, Qt::FlatCap));
        p.drawArc(ring, 90 * 16 - usedArc, -reservedArc);
      }
    }
    p.setPen(palette().color(QPalette::WindowText));
    QFont number = font();
    number.setPointSize(width() < 176 ? 22 : 27);
    number.setBold(true);
    p.setFont(number);
    const QString percentage =
        known && total
            ? QLocale().toString(100.0 * occupied / total, 'f', 0) + "%"
            : "—";
    p.drawText(QRectF(0, height() / 2.0 - 30, width(), 44), Qt::AlignCenter,
               percentage);
    QFont caption = font();
    caption.setPointSize(8);
    p.setFont(caption);
    p.setPen(palette().color(QPalette::PlaceholderText));
    p.drawText(QRectF(0, height() / 2.0 + 15, width(), 26), Qt::AlignCenter,
               known ? "SPACE USED" : "Unavailable");
  }

private:
  bool known = false;
  quint64 total = 0, occupied = 0, held = 0;
};

DrivePreview::DrivePreview(QWidget *parent) : QScrollArea(parent) {
  setObjectName("drivePreview");
  setAccessibleName("Drive preview");
  setFrameShape(QFrame::NoFrame);
  setWidgetResizable(true);
  setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  auto *body = new QWidget;
  body->setObjectName("drivePreviewBody");
  auto *layout = new QVBoxLayout(body);
  layout->setContentsMargins(14, 16, 14, 16);
  layout->setSpacing(14);
  layout->addWidget(label("DRIVE PREVIEW", "drivePreviewEyebrow"));
  empty = label("Select a drive to see its details.", "drivePreviewEmpty");
  layout->addWidget(empty);
  details = new QWidget;
  auto *content = new QVBoxLayout(details);
  content->setContentsMargins(0, 0, 0, 0);
  content->setSpacing(12);
  auto *header = new QHBoxLayout;
  header->setSpacing(10);
  art = new QLabel;
  art->setFixedSize(32, 36);
  art->setAlignment(Qt::AlignCenter);
  header->addWidget(art, 0, Qt::AlignTop);
  auto *titles = new QVBoxLayout;
  titles->setSpacing(4);
  heading = label({}, "drivePreviewName");
  heading->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
  status = label({}, "drivePreviewStatus");
  status->setProperty("muted", true);
  status->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
  titles->addWidget(heading);
  titles->addWidget(status);
  header->addLayout(titles, 1);
  content->addLayout(header);
  auto *storage = new QFrame;
  storage->setObjectName("drivePreviewStorage");
  auto *storageLayout = new QVBoxLayout(storage);
  storageLayout->setContentsMargins(10, 8, 10, 10);
  storageLayout->setSpacing(7);
  chart = new StorageChart;
  chart->setFixedSize(144, 144);
  storageLayout->addWidget(chart, 0, Qt::AlignHCenter);
  const QStringList captions{"Used", "Free", "Reserved", "Capacity"};
  const QStringList keys{"used", "free", "reserved", "capacity"};
  for (int i = 0; i < keys.size(); ++i) {
    auto *row = new QWidget;
    auto *line = new QHBoxLayout(row);
    line->setContentsMargins(0, 0, 0, 0);
    line->setSpacing(6);
    if (i < 3) line->addWidget(new Swatch(i));
    auto *caption = label(captions[i]);
    caption->setProperty("muted", true);
    line->addWidget(caption);
    auto *value = label({}, "drivePreview_" + keys[i]);
    value->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    value->setWordWrap(false);
    line->addWidget(value, 1);
    metrics.insert(keys[i], value);
    storageLayout->addWidget(row);
  }
  content->addWidget(storage);
  hint = label({}, "drivePreviewHint");
  hint->setProperty("muted", true);
  content->addWidget(hint);
  const QList<QPair<QString, QString>> info{
      {"model", "Model"}, {"filesystem", "File system"},
      {"transport", "Connection"}, {"device", "Device"},
      {"physical", "Physical disk"}, {"diskSize", "Disk capacity"},
      {"partitionLabel", "Partition label"}, {"location", "Location"},
      {"access", "Access"}};
  for (const auto &[key, caption] : info) {
    auto *row = new QWidget;
    auto *line = new QVBoxLayout(row);
    line->setContentsMargins(0, 0, 0, 0);
    line->setSpacing(2);
    auto *title = label(caption);
    title->setProperty("drivePreviewCaption", true);
    auto *value = label({}, "drivePreview_" + key);
    value->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    line->addWidget(title);
    line->addWidget(value);
    fields.insert(key, value);
    content->addWidget(row);
  }
  auto *properties = new QPushButton("Full properties…");
  properties->setObjectName("drivePreviewProperties");
  properties->setCursor(Qt::PointingHandCursor);
  connect(properties, &QPushButton::clicked, this, [this] {
    if (!volume.device.isEmpty()) emit propertiesRequested(volume);
  });
  content->addWidget(properties);
  layout->addWidget(details);
  layout->addStretch();
  setWidget(body);
  body->setAutoFillBackground(false);
  viewport()->setObjectName("drivePreviewViewport");
  viewport()->setAutoFillBackground(false);
  setVolume({});
}

void DrivePreview::setVolume(const Volume &next) {
  const bool changed = volume.device != next.device || volume.uuid != next.uuid;
  volume = next;
  const bool selected = !volume.device.isEmpty();
  empty->setVisible(!selected);
  details->setVisible(selected);
  heading->setText(volume.name.isEmpty() ? QFileInfo(volume.device).fileName() : volume.name);
  heading->setToolTip(heading->text());
  updateIcon();
  if (changed) verticalScrollBar()->setValue(0);
  if (!selected) return;

  const bool noMedia = volume.optical() && !volume.size && volume.filesystem.isEmpty();
  const bool swap = volume.filesystem == "swap";
  const QString kind = volume.mount == "/" ? "System drive"
      : volume.optical() ? "Optical drive"
      : volume.removableMedia() ? "Removable drive" : "Internal drive";
  status->setText(volume.prefix() ? (volume.type == "steam-prefix" ? "Steam prefix" : "Wine / Proton prefix")
      : swap ? "Swap" : noMedia ? "No media · " + kind
      : volume.locked() ? "Encrypted · locked"
      : (volume.mounted() ? "Mounted · " : "Not mounted · ") + kind);

  const auto [known, total, available, occupied, held] = storageUsage(volume);
  chart->setUsage(known, total, occupied, held);
  chart->setVisible(known);
  auto metric = [&](const QString &key, quint64 bytes, bool visible) {
    auto *value = metrics[key];
    value->setText(visible ? QLocale().formattedDataSize(bytes) : QString());
    value->setToolTip(visible ? exactBytes(bytes) : QString());
    value->parentWidget()->setVisible(visible);
  };
  metric("used", occupied, known);
  metric("free", available, known);
  metric("reserved", held, known && held > 0);
  metric("capacity", total, total > 0);
  chart->parentWidget()->setVisible(total > 0);
  hint->setText(known ? (held ? "Reserved space is kept by the file system." : QString())
      : volume.prefix() || swap ? QString()
      : noMedia ? "Insert a disc to see its capacity."
      : volume.locked() ? "Unlock and mount to see space usage."
      : volume.mounted() ? "Space usage is unavailable."
      : volume.mountable() ? "Mount to see used and free space."
      : "Space usage is unavailable.");
  hint->setVisible(!hint->text().isEmpty());
  auto field = [&](const QString &key, const QString &text) {
    auto *value = fields[key];
    value->setText(text);
    value->setToolTip(text);
    value->parentWidget()->setVisible(!text.isEmpty());
  };
  field("model", volume.prefix() ? QString() : volume.driveModel);
  field("filesystem", volume.prefix() ? QString() : volume.filesystem);
  field("transport", volume.transport.compare("nvme", Qt::CaseInsensitive) == 0 ? "NVMe" : volume.transport.toUpper());
  field("device", volume.prefix() ? QString() : volume.device);
  field("physical", !volume.prefix() && volume.driveKey() != volume.device ? volume.driveKey() : QString());
  field("diskSize", !volume.prefix() && volume.driveSize > volume.size ? QLocale().formattedDataSize(volume.driveSize) : QString());
  field("partitionLabel", volume.partitionLabel);
  field("location", volume.mount);
  field("access", volume.readOnly ? "Read only" : volume.mounted() ? "Read/write" : QString());
}

void DrivePreview::updateIcon() {
  if (art) art->setPixmap(Fusion::symbolicIcon(volume.mount == "/" ? "drive-linux" : volume.symbol()).pixmap(32, 32));
}
void DrivePreview::changeEvent(QEvent *event) {
  QScrollArea::changeEvent(event);
  if (event->type() == QEvent::PaletteChange || event->type() == QEvent::StyleChange)
    updateIcon();
}

DriveProperties::DriveProperties(const Volume &initial, Drives *drives,
                                 QWidget *parent)
    : QDialog(parent), volume(initial) {
  setObjectName("driveProperties");
  setWindowTitle("Drive properties");
  setWindowIcon(Fusion::icon(volume.usb() ? "drive-removable-media-usb"
                                          : "drive-harddisk"));
  setMinimumWidth(520);
  resize(560, 620);
  setSizeGripEnabled(true);
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(20, 18, 20, 16);
  layout->setSpacing(10);
  auto *header = new QHBoxLayout;
  auto *art = new QLabel;
  art->setObjectName("volumeArtwork");
  art->setAlignment(Qt::AlignCenter);
  art->setPixmap(windowIcon().pixmap(48, 48));
  art->setFixedSize(58, 58);
  header->addWidget(art);
  header->setSpacing(14);
  auto *titles = new QVBoxLayout;
  titles->setSpacing(4);
  heading = label({}, "volumeHeading");
  status = label({}, "volumeStatus");
  titles->addWidget(heading);
  titles->addWidget(status);
  header->addLayout(titles, 1);
  layout->addLayout(header);
  auto *storage = new QFrame;
  storage->setObjectName("storageSummary");
  auto *storageLayout = new QVBoxLayout(storage);
  storageLayout->setContentsMargins(16, 12, 16, 12);
  storageLayout->setSpacing(8);
  auto *usage = new QHBoxLayout;
  usage->setSpacing(20);
  chart = new StorageChart;
  usage->addWidget(chart, 0, Qt::AlignVCenter);
  auto *metrics = new QVBoxLayout;
  metrics->setSpacing(7);
  auto metric = [&](const QString &title, const QString &key, int color,
                    QLabel *&value, QLabel *&exact) {
    auto *row = new QWidget;
    auto *rowLayout = new QVBoxLayout(row);
    rowLayout->setContentsMargins(0, 0, 0, 0);
    rowLayout->setSpacing(1);
    auto *caption = new QHBoxLayout;
    caption->setSpacing(7);
    if (color >= 0)
      caption->addWidget(new Swatch(color));
    caption->addWidget(label(title, "muted"), 1);
    rowLayout->addLayout(caption);
    value = label({}, key + "Value");
    value->setProperty("storageValue", true);
    value->setWordWrap(false);
    exact = label({}, key + "Bytes");
    exact->setWordWrap(false);
    exact->setProperty("muted", true);
    exact->setProperty("exactBytes", true);
    rowLayout->addWidget(value);
    rowLayout->addWidget(exact);
    metrics->addWidget(row);
    return row;
  };
  metric("Used space", "used", 0, used, usedBytes);
  metric("Free space", "free", 1, free, freeBytes);
  reservedRow =
      metric("Reserved space", "reserved", 2, reserved, reservedBytes);
  usage->addLayout(metrics, 1);
  storageLayout->addLayout(usage);
  auto *capacityRow = new QFrame;
  capacityRow->setObjectName("capacityRow");
  auto *capacityLayout = new QHBoxLayout(capacityRow);
  capacityLayout->setContentsMargins(2, 10, 2, 0);
  capacityLayout->addWidget(label("Total capacity", "muted"));
  capacityLayout->addStretch();
  auto *capacityNumbers = new QHBoxLayout;
  capacityNumbers->setSpacing(10);
  capacity = label({}, "capacityValue");
  capacity->setProperty("storageValue", true);
  capacity->setWordWrap(false);
  capacityBytes = label({}, "capacityBytes");
  capacityBytes->setWordWrap(false);
  capacityBytes->setProperty("muted", true);
  capacityBytes->setProperty("exactBytes", true);
  capacity->setAlignment(Qt::AlignRight);
  capacityBytes->setAlignment(Qt::AlignRight);
  capacityNumbers->addWidget(capacity);
  capacityNumbers->addWidget(capacityBytes);
  capacityLayout->addLayout(capacityNumbers);
  storageLayout->addWidget(capacityRow);
  layout->addWidget(storage);
  usageHint = label({}, "usageHint");
  layout->addWidget(usageHint);
  auto *details = new QFrame;
  details->setObjectName("volumeDetails");
  auto *info = new QFormLayout(details);
  info->setContentsMargins(14, 10, 14, 10);
  info->setVerticalSpacing(4);
  info->setHorizontalSpacing(18);
  info->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
  auto field = [&](const QString &caption, const QString &name) {
    auto *value = label({}, name);
    info->addRow(label(caption, "muted"), value);
    return value;
  };
  filesystem = field("File system", "volumeFilesystem");
  device = field("Device", "volumeDevice");
  physical = field("Physical drive", "volumePhysical");
  mount = field("Location", "volumeLocation");
  access = field("Access", "volumeAccess");
  uuid = field("UUID", "volumeUuid");
  layout->addWidget(details);
  auto *cleaner = new QPushButton;
  cleaner->setObjectName("systemCleaner");
  cleaner->setMinimumHeight(54);
  cleaner->setAccessibleName("Open System Cleaner in Control Panel");
  cleaner->setToolTip("Open Control Panel → System Cleaner");
  cleaner->setCursor(Qt::PointingHandCursor);
  auto *cleanerLayout = new QHBoxLayout(cleaner);
  cleanerLayout->setContentsMargins(12, 9, 12, 9);
  cleanerLayout->setSpacing(10);
  auto *cleanerArt = new QLabel;
  cleanerArt->setPixmap(
      Fusion::icon("sweeper", "edit-clear-history").pixmap(28, 28));
  cleanerLayout->addWidget(cleanerArt);
  auto *cleanerText = new QVBoxLayout;
  cleanerText->setSpacing(1);
  cleanerText->addWidget(label("System Cleaner", "cleanerTitle"));
  cleanerText->addWidget(
      label("Free up space in Control Panel", "cleanerDescription"));
  cleanerLayout->addLayout(cleanerText, 1);
  cleanerLayout->addWidget(label("→", "cleanerArrow"));
  for (auto *child : cleaner->findChildren<QLabel *>()) {
    child->setAttribute(Qt::WA_TransparentForMouseEvents);
    child->setTextInteractionFlags(Qt::NoTextInteraction);
  }
  connect(cleaner, &QPushButton::clicked, this, [this] {
    if (!QProcess::startDetached(Fusion::root() + "/scripts/control-panel.sh",
                                 {"--section", "cleaner"}))
      QMessageBox::warning(
          this, "System Cleaner",
          "Could not open Control Panel. Please try again from the Apps menu.");
  });
  layout->addWidget(cleaner);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close);
  open = buttons->addButton("Open folder", QDialogButtonBox::ActionRole);
  open->setObjectName("openVolume");
  auto *copy = buttons->addButton("Copy details", QDialogButtonBox::ActionRole);
  connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
  connect(copy, &QPushButton::clicked, this,
          [this] { QApplication::clipboard()->setText(summary()); });
  connect(open, &QPushButton::clicked, this,
          [this, drives] { drives->operate(volume, "open", this); });
  layout->addWidget(buttons);
  connect(drives, &Drives::changed, this, [this, drives] {
    const auto found = std::find_if(
        drives->volumes.cbegin(), drives->volumes.cend(),
        [this](const Volume &v) {
          return v.device == volume.device && v.uuid == volume.uuid;
        });
    connected = found != drives->volumes.cend();
    if (connected)
      volume = *found;
    refresh();
  });
  refresh();
}

void DriveProperties::refresh() {
  heading->setText(volume.name);
  status->setText(!connected        ? "Disconnected"
                  : volume.locked() ? "Encrypted · locked"
                  : volume.mounted()
                      ? (volume.usb() ? "Mounted · Removable drive"
                                      : "Mounted · Internal drive")
                  : volume.usb() ? "Not mounted · Removable drive"
                                 : "Not mounted · Internal drive");
  const auto [known, total, available, occupied, held] = storageUsage(volume, connected);
  chart->setUsage(known, total, occupied, held);
  auto display = [](QLabel *value, QLabel *exact, quint64 bytes, bool valid) {
    value->setText(valid ? QLocale().formattedDataSize(bytes) : "—");
    exact->setText(valid ? exactBytes(bytes) : "Unavailable");
  };
  display(used, usedBytes, occupied, known);
  display(free, freeBytes, available, known);
  display(reserved, reservedBytes, held, known);
  display(capacity, capacityBytes, total, total > 0);
  reservedRow->setVisible(known && held > 0);
  usageHint->setText(
      !connected ? "This volume is no longer connected."
      : !known
          ? volume.mounted() ? "Space usage is temporarily unavailable."
            : volume.locked()
                ? "Unlock and mount this volume to read used and free space."
                : "Mount this volume to read used and free space."
      : held > 0 ? "Reserved space is kept by the filesystem and is "
                   "unavailable for files."
                 : QString());
  usageHint->setVisible(!usageHint->text().isEmpty());
  device->setText(volume.device);
  physical->setText(volume.driveModel.isEmpty()
                        ? volume.driveKey()
                        : volume.driveModel + " · " + volume.driveKey());
  filesystem->setText(volume.filesystem.isEmpty() ? "Unformatted / unknown"
                                                  : volume.filesystem);
  mount->setText(!connected         ? "Disconnected"
                 : volume.mounted() ? volume.mount
                                    : "Not mounted");
  access->setText(volume.readOnly ? "Read only" : "Read/write");
  uuid->setText(volume.uuid.isEmpty() ? "—" : volume.uuid);
  open->setVisible(connected && volume.mounted());
}

QString DriveProperties::summary() const {
  QStringList lines{heading->text(),
                    status->text(),
                    {},
                    "Used: " + used->text() + " (" + usedBytes->text() + ")",
                    "Free: " + free->text() + " (" + freeBytes->text() + ")",
                    "Capacity: " + capacity->text() + " (" +
                        capacityBytes->text() + ")",
                    "File system: " + filesystem->text(),
                    "Device: " + device->text(),
                    "Physical drive: " + physical->text(),
                    "Location: " + mount->text(),
                    "Access: " + access->text(),
                    "UUID: " + uuid->text()};
  if (reservedRow->isVisible())
    lines << "Reserved: " + reserved->text() + " (" + reservedBytes->text() +
                 ")";
  return lines.join('\n');
}
