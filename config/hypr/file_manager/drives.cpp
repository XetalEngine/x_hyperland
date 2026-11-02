#include "drives.h"
#include "../control_panel/backend/volume_commands.h"
#include "core.h"
#include "drive_properties.h"
#include <QStorageInfo>

QList<Volume> Drives::parse(const QByteArray &data) {
  const auto document = QJsonDocument::fromJson(data);
  QList<Volume> result;
  QHash<QString, int> seen;
  struct PhysicalDisk {
    QString device, model, transport;
    quint64 size = 0;
  };
  std::function<void(QJsonObject, bool, PhysicalDisk)> visit =
      [&](QJsonObject item, bool parentRemovable, PhysicalDisk disk) {
        const auto children = item["children"].toArray();
        const QString type = item["type"].toString(),
                      filesystem = item["fstype"].toString();
        const bool removable =
            item["rm"].toBool() || item["rm"].toInt() == 1 || parentRemovable;
        QString device = item["path"].toString();
        if (device.isEmpty())
          device = "/dev/" + item["name"].toString();
        if (type == "disk") {
          disk = {device, item["model"].toString().trimmed(),
                  item["tran"].toString(),
                  item["size"].toVariant().toULongLong()};
        }
        QStringList mounts;
        for (auto mount : item["mountpoints"].toArray())
          if (!mount.toString().isEmpty() && mount.toString() != "[SWAP]")
            mounts << mount.toString();
        if (mounts.isEmpty() && item["mountpoint"].isString() &&
            item["mountpoint"].toString() != "[SWAP]")
          mounts << item["mountpoint"].toString();
        if (type != "loop" && type != "zram" &&
            (children.isEmpty() || !filesystem.isEmpty())) {
          Volume volume;
          volume.device = device;
          volume.name = item["label"].toString();
          if (volume.name.isEmpty())
            volume.name = mounts.contains("/")
                              ? "Linux system"
                              : QFileInfo(volume.device).fileName();
          volume.filesystem = filesystem;
          volume.mount = mounts.contains("/") ? "/" : mounts.value(0);
          volume.type = type;
          volume.uuid = item["uuid"].toString();
          volume.size = item["size"].toVariant().toULongLong();
          volume.removable = removable;
          volume.readOnly = item["ro"].toBool() || item["ro"].toInt() == 1;
          volume.driveDevice = disk.device;
          if (volume.driveDevice.isEmpty()) {
            const auto parent = item["pkname"].toString();
            volume.driveDevice = parent.isEmpty()         ? device
                                 : parent.startsWith('/') ? parent
                                                          : "/dev/" + parent;
          }
          volume.driveModel = disk.model;
          volume.transport = disk.transport;
          volume.driveSize = disk.size;
          if (!seen.contains(volume.device) &&
              volume.device.startsWith("/dev/")) {
            seen.insert(volume.device, result.size());
            result << volume;
          } else if (seen.contains(volume.device)) {
            auto &existing = result[seen.value(volume.device)];
            if (existing.driveDevice != volume.driveDevice) {
              // Shared RAID/LVM nodes have multiple backing disks; keep their
              // logical device together rather than claiming one physical
              // parent.
              existing.driveDevice = existing.device;
              existing.driveModel = "Multiple backing disks";
              existing.driveSize = existing.size;
              existing.transport.clear();
            }
          }
        }
        for (auto child : children)
          visit(child.toObject(), removable, disk);
      };
  for (auto item : document.object()["blockdevices"].toArray())
    visit(item.toObject(), false, {});
  std::stable_sort(result.begin(), result.end(),
                   [](const Volume &a, const Volume &b) {
                     if ((a.mount == "/") != (b.mount == "/"))
                       return a.mount == "/";
                     return QString::localeAwareCompare(a.name, b.name) < 0;
                   });
  return result;
}
Drives::Drives(QObject *parent, bool automatic) : QObject(parent) {
  scanningEnabled = automatic;
  connect(
      &scan, &QProcess::finished, this,
      [this](int code, QProcess::ExitStatus status) {
        const auto data = scan.readAllStandardOutput();
        if (code || status != QProcess::NormalExit ||
            !QJsonDocument::fromJson(data).object().contains("blockdevices")) {
          emit message(
              "Drive discovery failed. " +
              QString::fromUtf8(scan.readAllStandardError()).trimmed());
          return;
        }
        volumes = parse(data);
        for (auto &volume : volumes)
          if (volume.mounted()) {
            QStorageInfo storage(volume.mount);
            if (storage.isValid() && storage.isReady()) {
              volume.total = qMax<qint64>(0, storage.bytesTotal());
              volume.available = qMax<qint64>(0, storage.bytesAvailable());
              volume.freeBytes = qMax<qint64>(0, storage.bytesFree());
              volume.spaceKnown = true;
            }
          }
        emit changed();
        if (refreshAgain && !busy()) {
          refreshAgain = false;
          refresh();
          return;
        }
        if (!busy() && !openAfterMount.isEmpty()) {
          const QString requested = std::exchange(openAfterMount, QString());
          for (const auto &volume : volumes)
            if (volume.device == requested && volume.mounted())
              emit browse(QUrl::fromLocalFile(volume.mount));
        }
      });
  connect(&scan, &QProcess::errorOccurred, this, [this] {
    emit message("Cannot list drives: " + scan.errorString());
  });
  connect(&operation, &QProcess::finished, this,
          [this](int code, QProcess::ExitStatus status) {
            const QString output =
                QString::fromUtf8(operation.readAllStandardError()).trimmed();
            if (code || status != QProcess::NormalExit) {
              openAfterMount.clear();
              emit message(output.isEmpty() ? "Drive operation failed."
                                            : output);
            } else
              emit message("Drive operation completed.");
            refresh();
          });
  connect(&operation, &QProcess::errorOccurred, this, [this] {
    openAfterMount.clear();
    emit message("Cannot start drive operation: " + operation.errorString());
  });
  connect(&timer, &QTimer::timeout, this, &Drives::refresh);
  timer.setInterval(5000);
  if (automatic) {
    timer.start();
    QTimer::singleShot(0, this, &Drives::refresh);
  }
}
void Drives::refresh() {
  if (!scanningEnabled)
    return;
  if (busy())
    return;
  if (scan.state() != QProcess::NotRunning) {
    refreshAgain = true;
    return;
  }
  scan.start("lsblk", {"--json", "--bytes", "--output",
                       "PATH,NAME,TYPE,FSTYPE,LABEL,SIZE,MOUNTPOINTS,RO,RM,"
                       "UUID,PKNAME,MODEL,TRAN"});
}
Drives::~Drives() {
  timer.stop();
  for (auto *process : {&scan, &operation}) {
    disconnect(process, nullptr, this, nullptr);
    if (process->state() != QProcess::NotRunning) {
      process->kill();
      process->waitForFinished(1000);
    }
  }
}
void Drives::operate(const Volume &snapshot, const QString &action,
                     QWidget *parent) {
  if (busy()) {
    emit message("A drive operation is already running.");
    return;
  }
  // Resolve against the latest inventory. An unplugged/replaced device must
  // never inherit a stale menu's operation.
  const auto found =
      std::find_if(volumes.cbegin(), volumes.cend(), [&](const Volume &v) {
        return v.device == snapshot.device && v.uuid == snapshot.uuid;
      });
  if (found == volumes.cend()) {
    emit message(
        "This drive changed or was disconnected. Refresh and try again.");
    refresh();
    return;
  }
  const Volume volume = *found;
  if (action == "open" && volume.mounted()) {
    const auto location = mountedLocation(volume);
    if (!location.isEmpty())
      emit browse(location);
    return;
  }
  if ((action == "mount" || action == "force" || action == "open") &&
      !volume.mountable()) {
    emit message("This volume cannot be mounted here. Use Control Panel for "
                 "encrypted or unformatted devices.");
    return;
  }
  if (action == "force" &&
      QMessageBox::question(
          parent, "Force mount",
          "Try the filesystem's force option for “" + volume.name +
              "”?\n\nUse normal Mount first. Force mounting can bypass "
              "filesystem checks; it does not repair the filesystem.",
          QMessageBox::Yes | QMessageBox::Cancel,
          QMessageBox::Cancel) != QMessageBox::Yes)
    return;
  QStringList args;
  if (action == "unmount") {
    if (!volume.mounted() || volume.mount == "/" || volume.mount == "/home" ||
        volume.mount == "/boot" || volume.mount.startsWith("/boot/"))
      return;
    args = FusionVolumes::unmount(volume.device);
  } else if (action == "mount" || action == "force" || action == "open") {
    if (volume.mounted())
      return;
    args = FusionVolumes::mount(volume.device, action == "force");
    if (action == "open")
      openAfterMount = volume.device;
  } else if (action == "eject" && volume.usb() && !volume.mounted()) {
    args = {"power-off", "-b", volume.device};
  } else
    return;
  emit message("Working on “" + volume.name + "”…");
  operation.start("udisksctl", args);
}
void Drives::menu(const Volume &volume, const QPoint &position,
                  QWidget *parent) {
  QMenu menu(parent);
  menu.setObjectName("volumeContextMenu");
  auto *open = menu.addAction(Fusion::icon("document-open"),
                              volume.mounted() ? "Open" : "Mount and open");
  open->setEnabled(volume.mounted() || volume.mountable());
  emit populateFileMenu(&menu, volume);
  menu.addSeparator();
  auto *mount = menu.addAction(Fusion::icon("media-mount"), "Mount");
  mount->setEnabled(!volume.mounted() && volume.mountable());
  auto *unmount = menu.addAction(Fusion::icon("media-eject"), "Unmount");
  unmount->setEnabled(volume.mounted() && volume.mount != "/" &&
                      volume.mount != "/home" &&
                      !volume.mount.startsWith("/boot"));
  auto *force = menu.addAction("Force mount…");
  force->setEnabled(mount->isEnabled());
  auto *eject = volume.usb() ? menu.addAction(Fusion::icon("media-eject"),
                                              "Safely remove drive")
                             : nullptr;
  if (eject) {
    eject->setEnabled(!volume.mounted());
    eject->setToolTip("Unmount this drive's volumes before removing it.");
  }
  menu.addSeparator();
  auto *copy = menu.addAction("Copy device path");
  auto *properties =
      menu.addAction(Fusion::icon("document-properties"), "Properties…");
  const auto *chosen = menu.exec(position);
  if (chosen == open)
    operate(volume, "open", parent);
  else if (chosen == mount)
    operate(volume, "mount", parent);
  else if (chosen == unmount)
    operate(volume, "unmount", parent);
  else if (chosen == force)
    operate(volume, "force", parent);
  else if (eject && chosen == eject)
    operate(volume, "eject", parent);
  else if (chosen == copy)
    QApplication::clipboard()->setText(volume.device);
  else if (chosen == properties)
    showProperties(volume, parent);
}
QUrl Drives::mountedLocation(const Volume &snapshot) {
  const auto found =
      std::find_if(volumes.cbegin(), volumes.cend(), [&](const Volume &v) {
        return v.device == snapshot.device && v.uuid == snapshot.uuid &&
               v.mount == snapshot.mount;
      });
  if (found == volumes.cend() || !found->mounted()) {
    emit message("Mount this volume before accessing its files.");
    return {};
  }
  QStorageInfo storage(found->mount);
  const auto actual =
      QFileInfo(QString::fromLocal8Bit(storage.device())).canonicalFilePath();
  const auto expected = QFileInfo(found->device).canonicalFilePath();
  if (!storage.isReady() || actual.isEmpty() || expected.isEmpty() ||
      actual != expected) {
    emit message("This drive's mount changed. Refresh and try again.");
    refresh();
    return {};
  }
  return QUrl::fromLocalFile(found->mount);
}
void Drives::showProperties(const Volume &volume, QWidget *parent) {
  auto *dialog = new DriveProperties(volume, this, parent);
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->show();
}
DriveDelegate::DriveDelegate(QWidget *parent) : QStyledItemDelegate(parent) {
  // Paint with a real themed widget, so the shared theme owns card geometry.
  // New themes (or live theme changes) need no special cases in the delegate.
  cardStyle = new QGroupBox(parent);
  cardStyle->setObjectName("drivePartitionCard");
  cardStyle->hide();
}
void DriveDelegate::paint(QPainter *p, const QStyleOptionViewItem &o,
                          const QModelIndex &index) const {
  const auto volume = index.data(Qt::UserRole).value<Volume>();
  p->save();
  p->setRenderHint(QPainter::Antialiasing);
  QRect box = o.rect.adjusted(5, 5, -5, -5);
  const bool selected = o.state & QStyle::State_Selected;
  cardStyle->ensurePolished();
  QStyleOptionGroupBox frame;
  frame.initFrom(cardStyle);
  frame.rect = box;
  frame.state = o.state;
  frame.subControls = QStyle::SC_GroupBoxFrame;
  frame.lineWidth = 1;
  cardStyle->style()->drawComplexControl(QStyle::CC_GroupBox, &frame, p, cardStyle);
  Fusion::icon(volume.usb() ? "drive-removable-media-usb" : "drive-harddisk")
      .paint(p, box.adjusted(14, 20, 0, 0).topLeft().x(), box.y() + 22, 54, 54);
  const QColor text =
      o.palette.color(selected ? QPalette::HighlightedText : QPalette::Text);
  QRect content = box.adjusted(82, 12, -14, -10);
  p->setPen(text);
  QFont bold = o.font;
  bold.setBold(true);
  p->setFont(bold);
  p->drawText(content.adjusted(0, 0, 0, -50), Qt::AlignLeft | Qt::AlignVCenter,
              QFontMetrics(bold).elidedText(volume.name, Qt::ElideRight,
                                            content.width()));
  p->setFont(o.font);
  const QString description = volume.mounted()  ? volume.mount
                              : volume.locked() ? "Encrypted · locked"
                              : volume.filesystem.isEmpty() ? "No filesystem"
                                                            : "Not mounted";
  QColor muted = text;
  muted.setAlpha(190);
  p->setPen(muted);
  p->drawText(content.adjusted(0, 24, 0, -29), Qt::AlignLeft | Qt::AlignVCenter,
              QFontMetrics(o.font).elidedText(description, Qt::ElideMiddle,
                                              content.width()));
  if (volume.mounted() && volume.total) {
    const QRectF bar(content.x(), content.y() + 51, content.width(), 6);
    p->setPen(Qt::NoPen);
    QColor track = text;
    track.setAlpha(35);
    p->setBrush(track);
    p->drawRoundedRect(bar, 3, 3);
    const qreal used =
        1.0 - qMin<qreal>(1, qreal(volume.available) / volume.total);
    QColor accent = qApp->property("fusionAccent").value<QColor>();
    if (!accent.isValid())
      accent = o.palette.color(QPalette::Accent);
    if (used > .9)
      accent = QColor("#ff6868");
    if (used > 0) {
      QRectF fill = bar;
      fill.setWidth(qMax<qreal>(2, bar.width() * used));
      // Keep the luminous accent even when the card is selected. Highlight
      // is the deliberately subdued selection surface in our desktop themes.
      for (int spread = 3; spread > 0; --spread) {
        QColor halo = accent;
        halo.setAlpha(10 + (3 - spread) * 9);
        p->setBrush(halo);
        p->drawRoundedRect(fill.adjusted(-spread, -spread, spread, spread),
                           3 + spread, 3 + spread);
      }
      QLinearGradient light(fill.topLeft(), fill.bottomLeft());
      light.setColorAt(0, accent.lighter(135));
      light.setColorAt(.45, accent);
      light.setColorAt(1, accent.darker(110));
      p->setBrush(light);
      p->drawRoundedRect(fill, 3, 3);
    }
    p->setPen(muted);
    p->drawText(content.adjusted(0, 61, 0, 4), Qt::AlignLeft | Qt::AlignTop,
                QLocale().formattedDataSize(volume.available) + " free of " +
                    QLocale().formattedDataSize(volume.total));
  } else {
    p->setPen(muted);
    p->drawText(
        content.adjusted(0, 54, 0, 0), Qt::AlignLeft | Qt::AlignTop,
        QLocale().formattedDataSize(volume.size) +
            (volume.filesystem.isEmpty() ? "" : " · " + volume.filesystem));
  }
  p->restore();
}
