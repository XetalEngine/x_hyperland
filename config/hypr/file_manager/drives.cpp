#include "drives.h"
#include "../control_panel/backend/volume_commands.h"
#include "core.h"
#include <QStorageInfo>

QList<Volume> Drives::parse(const QByteArray &data) {
  const auto document = QJsonDocument::fromJson(data);
  QList<Volume> result;
  QSet<QString> seen;
  std::function<void(QJsonObject, bool)> visit = [&](QJsonObject item,
                                                     bool parentRemovable) {
    const auto children = item["children"].toArray();
    const QString type = item["type"].toString(),
                  filesystem = item["fstype"].toString();
    const bool removable =
        item["rm"].toBool() || item["rm"].toInt() == 1 || parentRemovable;
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
      volume.device = item["path"].toString();
      if (volume.device.isEmpty())
        volume.device = "/dev/" + item["name"].toString();
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
      if (!seen.contains(volume.device) && volume.device.startsWith("/dev/")) {
        seen.insert(volume.device);
        result << volume;
      }
    }
    for (auto child : children)
      visit(child.toObject(), removable);
  };
  for (auto item : document.object()["blockdevices"].toArray())
    visit(item.toObject(), false);
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
  scan.start("lsblk",
             {"--json", "--bytes", "--output",
              "PATH,NAME,TYPE,FSTYPE,LABEL,SIZE,MOUNTPOINTS,RO,RM,UUID"});
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
    QStorageInfo storage(volume.mount);
    const auto actual =
        QFileInfo(QString::fromLocal8Bit(storage.device())).canonicalFilePath();
    if (!storage.isReady() ||
        actual != QFileInfo(volume.device).canonicalFilePath()) {
      emit message("This drive's mount changed. Refresh and try again.");
      refresh();
      return;
    }
    emit browse(QUrl::fromLocalFile(volume.mount));
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
  } else if (action == "eject" && volume.removable && !volume.mounted()) {
    args = {"power-off", "-b", volume.device};
  } else
    return;
  emit message("Working on “" + volume.name + "”…");
  operation.start("udisksctl", args);
}
void Drives::menu(const Volume &volume, const QPoint &position,
                  QWidget *parent) {
  QMenu menu(parent);
  auto *open = menu.addAction(Fusion::icon("document-open"),
                              volume.mounted() ? "Open" : "Mount and open");
  open->setEnabled(volume.mounted() || volume.mountable());
  auto *mount = menu.addAction(Fusion::icon("media-mount"), "Mount");
  mount->setEnabled(!volume.mounted() && volume.mountable());
  auto *unmount = menu.addAction(Fusion::icon("media-eject"), "Unmount");
  unmount->setEnabled(volume.mounted() && volume.mount != "/" &&
                      volume.mount != "/home" &&
                      !volume.mount.startsWith("/boot"));
  auto *force = menu.addAction("Force mount…");
  force->setEnabled(mount->isEnabled());
  auto *eject = volume.removable ? menu.addAction(Fusion::icon("media-eject"),
                                                  "Safely remove drive")
                                 : nullptr;
  if (eject) {
    eject->setEnabled(!volume.mounted());
    eject->setToolTip("Unmount this drive's volumes before removing it.");
  }
  menu.addSeparator();
  auto *copy = menu.addAction("Copy device path");
  auto *properties = menu.addAction("Drive details");
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
    QMessageBox::information(
        parent, volume.name,
        QString("Device: %1\nFilesystem: %2\nCapacity: %3\nLocation: "
                "%4\nAccess: %5")
            .arg(volume.device,
                 volume.filesystem.isEmpty() ? "Unformatted / unknown"
                                             : volume.filesystem,
                 QLocale().formattedDataSize(volume.size),
                 volume.mounted() ? volume.mount : "Not mounted",
                 volume.readOnly ? "Read only" : "Read/write"));
}
void DriveDelegate::paint(QPainter *p, const QStyleOptionViewItem &o,
                          const QModelIndex &index) const {
  const auto volume = index.data(Qt::UserRole).value<Volume>();
  p->save();
  p->setRenderHint(QPainter::Antialiasing);
  QRect box = o.rect.adjusted(5, 5, -5, -5);
  const bool selected = o.state & QStyle::State_Selected,
             hover = o.state & QStyle::State_MouseOver;
  QColor background =
      o.palette.color(selected ? QPalette::Highlight : QPalette::AlternateBase);
  if (hover && !selected)
    background = background.lighter(110);
  p->setPen(QPen(selected ? o.palette.color(QPalette::Highlight)
                          : o.palette.color(QPalette::Midlight),
                 1));
  p->setBrush(background);
  p->drawRoundedRect(box, 9, 9);
  Fusion::icon(volume.removable ? "drive-removable-media-usb"
                                : "drive-harddisk")
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
    QRect bar(content.x(), content.y() + 51, content.width(), 5);
    p->setPen(Qt::NoPen);
    QColor track = text;
    track.setAlpha(35);
    p->setBrush(track);
    p->drawRoundedRect(bar, 2, 2);
    const qreal used =
        1.0 - qMin<qreal>(1, qreal(volume.available) / volume.total);
    p->setBrush(used > .9  ? QColor("#e66b68")
                : selected ? text
                           : o.palette.color(QPalette::Highlight));
    QRect fill = bar;
    fill.setWidth(qMax(2, int(bar.width() * used)));
    p->drawRoundedRect(fill, 2, 2);
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
