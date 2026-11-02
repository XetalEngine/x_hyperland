#include "grub_editor.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QtWidgets>

namespace {
QLabel *label(const QString &text, QWidget *parent, const char *name = "") {
  auto *value = new QLabel(text, parent);
  value->setTextFormat(Qt::PlainText);
  value->setWordWrap(true);
  value->setObjectName(name);
  return value;
}
QString capacity(double size) {
  return QLocale().formattedDataSize(qint64(size), 1, QLocale::DataSizeIecFormat);
}
QString mountPoints(const QJsonValue &value) {
  QStringList points;
  for (const auto &point : value.toArray()) if (!point.toString().isEmpty()) points << point.toString();
  return points.join(", ");
}
QString driveStatus(const QJsonObject &drive) {
  if (drive["current_system"].toBool()) return "Current system";
  return mountPoints(drive["mountpoints"]).isEmpty() ? "Not mounted" : "Mounted";
}
QJsonObject itemData(QListWidget *list) {
  return list->currentItem() ? list->currentItem()->data(Qt::UserRole).toJsonObject() : QJsonObject();
}
}

GrubEditor::GrubEditor(const QString &helper, QWidget *parent) : QWidget(parent), helper(helper) {
  setObjectName("grubEditorTab");
  auto *layout = new QVBoxLayout(this);
  layout->setSizeConstraint(QLayout::SetMinimumSize);
  layout->setSpacing(14);
  auto *heading = new QHBoxLayout;
  heading->addWidget(label("GRUB Boot Editor", this, "panelTitle"), 1);
  mode = label("", this, "muted"); heading->addWidget(mode);
  layout->addLayout(heading);
  layout->addWidget(label("Your drives. One boot menu.\nChoose a drive, name its system, and add it to GRUB.", this));

  choicesLayout = new QBoxLayout(QBoxLayout::TopToBottom);
  choicesLayout->setContentsMargins(0, 0, 0, 0); choicesLayout->setSpacing(14);
  layout->addLayout(choicesLayout);
  auto *driveBox = new QGroupBox("1  Choose a drive", this);
  auto *driveLayout = new QVBoxLayout(driveBox);
  driveLayout->setSizeConstraint(QLayout::SetMinimumSize);
  auto *driveRow = new QHBoxLayout;
  driveCount = label("All drives · mounted and unmounted", driveBox, "grubDriveCount");
  driveCount->setWordWrap(false);
  driveRow->addWidget(driveCount, 1);
  refresh = new QPushButton("Refresh drives", driveBox); refresh->setObjectName("grubRefresh");
  refresh->setIcon(QIcon::fromTheme("view-refresh")); driveRow->addWidget(refresh);
  driveLayout->addLayout(driveRow);
  drives = new QTreeWidget(driveBox); drives->setObjectName("grubDrives");
  drives->setHeaderLabels({"Drive", "Device", "Capacity", "Status"});
  drives->setRootIsDecorated(false); drives->setUniformRowHeights(true);
  drives->setAlternatingRowColors(true); drives->setSelectionMode(QAbstractItemView::SingleSelection);
  drives->setSelectionBehavior(QAbstractItemView::SelectRows);
  drives->setEditTriggers(QAbstractItemView::NoEditTriggers);
  drives->setMinimumHeight(140); drives->setMaximumHeight(270);
  drives->header()->setSectionResizeMode(0, QHeaderView::Stretch);
  for (int column = 1; column < 4; ++column) drives->header()->setSectionResizeMode(column, QHeaderView::ResizeToContents);
  drives->setContextMenuPolicy(Qt::CustomContextMenu);
  driveLayout->addWidget(drives);
  auto *driveActions = new QHBoxLayout;
  properties = new QPushButton("Properties…", driveBox); properties->setObjectName("grubProperties");
  properties->setIcon(QIcon::fromTheme("document-properties")); driveActions->addWidget(properties);
  driveActions->addStretch(1);
  detect = new QPushButton("Detect bootable systems", driveBox); detect->setObjectName("grubDetect");
  detect->setIcon(QIcon::fromTheme("system-search")); driveActions->addWidget(detect);
  driveLayout->addLayout(driveActions);
  choicesLayout->addWidget(driveBox, 1);

  auto *systemBox = new QGroupBox("2  Boot partition to add", this);
  auto *systemLayout = new QVBoxLayout(systemBox);
  systemLayout->setSizeConstraint(QLayout::SetMinimumSize);
  systems = new QListWidget(systemBox); systems->setObjectName("grubSystems");
  systems->setMinimumHeight(78); systems->setMaximumHeight(150);
  systemLayout->addWidget(systems);
  selection = label("Select a drive above to find Windows or Linux.", systemBox, "grubSelection");
  systemLayout->addWidget(selection);
  notes = label("", systemBox, "muted"); notes->hide(); systemLayout->addWidget(notes);
  auto *nameRow = new QHBoxLayout;
  nameRow->addWidget(label("Name in GRUB", systemBox));
  name = new QLineEdit(systemBox); name->setObjectName("grubName"); name->setMaxLength(100);
  name->setPlaceholderText("For example: Windows 11 or My Linux");
  nameRow->addWidget(name, 1);
  add = new QPushButton("Add to GRUB", systemBox); add->setObjectName("grubAdd");
  add->setProperty("primary", true); add->setIcon(QIcon::fromTheme("list-add"));
  nameRow->addWidget(add);
  systemLayout->addLayout(nameRow);
  systemLayout->addStretch(1);
  choicesLayout->addWidget(systemBox, 1);

  progress = new QProgressBar(this); progress->setRange(0, 0);
  progress->setTextVisible(false); progress->setFixedHeight(6); progress->hide(); layout->addWidget(progress);
  status = label("Choose the drive you want to add. Administrator authentication is requested when needed.", this, "grubStatus");
  status->setTextInteractionFlags(Qt::TextSelectableByMouse); layout->addWidget(status);

  auto *savedBox = new QGroupBox("Entries added with this editor", this);
  auto *savedLayout = new QVBoxLayout(savedBox);
  entries = new QListWidget(savedBox); entries->setObjectName("grubEntries");
  entries->setMinimumHeight(70); savedLayout->addWidget(entries, 1);
  saved = label("Your existing GRUB entries are kept.", savedBox, "grubSaved");
  saved->setWordWrap(false); savedLayout->addWidget(saved);
  auto *savedActions = new QHBoxLayout;
  load = new QPushButton("Load saved entries", savedBox); load->setObjectName("grubLoad");
  rename = new QPushButton("Rename…", savedBox); rename->setObjectName("grubRename");
  remove = new QPushButton("Remove from menu…", savedBox); remove->setObjectName("grubRemove");
  undo = new QPushButton("Undo last change", savedBox); undo->setObjectName("grubUndo");
  savedActions->addWidget(load); savedActions->addWidget(rename); savedActions->addWidget(remove);
  savedActions->addStretch(); savedActions->addWidget(undo);
  savedLayout->addLayout(savedActions); layout->addWidget(savedBox, 1);
  layout->addWidget(label("Each change is backed up and checked before saving. Your current GRUB theme and default system are kept.", this, "muted"));

  reader = new QProcess(this); worker = new QProcess(this);
  connect(refresh, &QPushButton::clicked, this, &GrubEditor::refreshDrives);
  connect(drives, &QTreeWidget::currentItemChanged, this, &GrubEditor::chooseDrive);
  connect(drives, &QTreeWidget::itemActivated, this, &GrubEditor::scanDrive);
  connect(detect, &QPushButton::clicked, this, &GrubEditor::scanDrive);
  connect(properties, &QPushButton::clicked, this, [this] { showDriveProperties(drive()); });
  connect(drives, &QTreeWidget::customContextMenuRequested, this, [this](const QPoint &point) {
    auto *row = drives->itemAt(point); if (!row) return;
    const auto metadata = row->data(0, Qt::UserRole).toJsonObject();
    QMenu menu(this);
    auto *action = menu.addAction(QIcon::fromTheme("document-properties"), "Properties…");
    if (menu.exec(drives->viewport()->mapToGlobal(point)) == action) showDriveProperties(metadata);
  });
  connect(systems, &QListWidget::currentRowChanged, this, &GrubEditor::chooseSystem);
  connect(entries, &QListWidget::currentRowChanged, this, &GrubEditor::updateActions);
  connect(name, &QLineEdit::textChanged, this, &GrubEditor::updateActions);
  connect(load, &QPushButton::clicked, this, [this] { request({{"action", "refresh"}}); });
  connect(add, &QPushButton::clicked, this, [this] {
    const auto target = system(); if (!target.value("available").toBool()) return;
    request({{"action", "add"}, {"drive", target["drive"]}, {"drive_token", target["drive_token"]},
             {"candidate", target["id"]}, {"loader_hash", target["loader_hash"]}, {"name", name->text().trimmed()}});
  });
  connect(rename, &QPushButton::clicked, this, [this] {
    const auto item = entry(); if (item.isEmpty()) return;
    bool ok = false;
    const auto title = QInputDialog::getText(this, "Rename boot entry", "Name in GRUB", QLineEdit::Normal,
                                            item["name"].toString(), &ok);
    if (ok && !title.trimmed().isEmpty()) request({{"action", "rename"}, {"id", item["id"]}, {"name", title}});
  });
  connect(remove, &QPushButton::clicked, this, [this] {
    const auto item = entry(); if (item.isEmpty()) return;
    if (QMessageBox::question(this, "Remove boot entry?", "Remove “"+item["name"].toString()+
        "” from the GRUB menu?\nThe system and its drive stay intact.", QMessageBox::Yes | QMessageBox::Cancel,
        QMessageBox::Cancel) == QMessageBox::Yes)
      request({{"action", "remove"}, {"id", item["id"]}});
  });
  connect(undo, &QPushButton::clicked, this, [this] {
    if (QMessageBox::question(this, "Undo last GRUB change?", "Restore the boot menu from before your last saved change?",
        QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) == QMessageBox::Yes)
      request({{"action", "undo"}});
  });
  connect(reader, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
    const auto data = QJsonDocument::fromJson(reader->readAllStandardOutput()).object();
    if (!code && data.contains("drives")) result(data);
    else status->setText(data.value("error").toString("Could not read drives. Try Refresh drives."));
    setBusy(false);
  });
  connect(reader, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { status->setText("Could not start drive detection."); setBusy(false); }
  });
  connect(worker, &QProcess::started, this, [this] {
    worker->write(QJsonDocument(pending).toJson(QJsonDocument::Compact)+'\n'); pending = {};
  });
  connect(worker, &QProcess::readyReadStandardOutput, this, &GrubEditor::readWorker);
  connect(worker, &QProcess::readyReadStandardError, this, [this] { errors += worker->readAllStandardError(); errors = errors.right(4096); });
  connect(worker, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
    readWorker();
    if (busy) {
      status->setText(code == 126 ? "Administrator authentication was cancelled. Select the drive again to retry." :
                       "The GRUB helper stopped. "+QString::fromUtf8(errors).trimmed());
      setBusy(false);
    }
  });
  connect(worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { status->setText("Could not open administrator authentication."); setBusy(false); }
  });
  updateActions();
}

GrubEditor::~GrubEditor() {
  worker->closeWriteChannel();
  if (!busy && worker->state() != QProcess::NotRunning) worker->waitForFinished(1000);
  if (reader->state() != QProcess::NotRunning) { reader->kill(); reader->waitForFinished(1000); }
}
void GrubEditor::showEvent(QShowEvent *event) {
  QWidget::showEvent(event);
  if (!loaded) { loaded = true; refreshDrives(); }
}
void GrubEditor::resizeEvent(QResizeEvent *event) {
  QWidget::resizeEvent(event);
  choicesLayout->setDirection(width() >= 1100 ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);
}
QJsonObject GrubEditor::system() const { return itemData(systems); }
QJsonObject GrubEditor::entry() const { return itemData(entries); }
QJsonObject GrubEditor::drive() const {
  return drives->currentItem() ? drives->currentItem()->data(0, Qt::UserRole).toJsonObject() : QJsonObject();
}
void GrubEditor::setBusy(bool value) { busy = value; progress->setVisible(value); updateActions(); }
void GrubEditor::updateActions() {
  drives->setEnabled(!busy); refresh->setEnabled(!busy);
  detect->setEnabled(!busy && supported && !drive().isEmpty());
  properties->setEnabled(!drive().isEmpty());
  systems->setEnabled(!busy); name->setEnabled(!busy && system().value("available").toBool());
  add->setEnabled(!busy && supported && system().value("available").toBool() && !name->text().trimmed().isEmpty() && !revision.isEmpty());
  load->setEnabled(!busy && supported); rename->setEnabled(!busy && !entry().isEmpty());
  remove->setEnabled(!busy && !entry().isEmpty()); undo->setEnabled(!busy && canUndo);
  bool existing = false;
  for (int i = 0; i < entries->count(); ++i)
    if (entries->item(i)->data(Qt::UserRole).toJsonObject()["id"] == system()["id"]) existing = true;
  add->setText(existing ? "Save name" : "Add to GRUB");
}
void GrubEditor::refreshDrives() {
  if (busy) return;
  systems->clear(); name->clear(); notes->hide();
  operation = "refresh"; status->setText("Finding drives…"); setBusy(true);
  if (worker->state() == QProcess::Running) {
    worker->write(QJsonDocument(QJsonObject{{"action", "refresh"}}).toJson(QJsonDocument::Compact)+'\n');
  } else reader->start("python3", {helper, "status"});
}
void GrubEditor::chooseDrive() {
  if (busy) return;
  systems->clear(); name->clear(); notes->hide();
  selection->setText(drive().isEmpty() ? "Select a drive above to find Windows or Linux." :
      "Select Detect bootable systems to inspect this drive’s partitions.");
  updateActions();
}
void GrubEditor::scanDrive() {
  if (busy || !supported || drive().isEmpty()) return;
  const auto selected = drive();
  systems->clear(); name->clear(); notes->hide();
  selection->setText("Finding bootable systems on this drive…");
  request({{"action", "scan"}, {"drive", selected["path"]}, {"drive_token", selected["token"]}});
}
void GrubEditor::showDriveProperties(const QJsonObject &metadata) {
  if (metadata.isEmpty()) return;
  QDialog dialog(this); dialog.setObjectName("grubDriveProperties");
  dialog.setProperty("xetalWindowSized", true);
  dialog.setWindowTitle("Drive properties · "+metadata["model"].toString());
  auto *layout = new QVBoxLayout(&dialog); layout->setSpacing(14);
  auto *hero = new QFrame(&dialog); hero->setObjectName("defaultsHero");
  auto *heroLayout = new QHBoxLayout(hero); heroLayout->setContentsMargins(20, 16, 20, 16);
  auto *icon = new QLabel(hero);
  icon->setPixmap(QIcon::fromTheme("drive-harddisk").pixmap(56, 56)); heroLayout->addWidget(icon);
  auto *identity = new QVBoxLayout;
  identity->addWidget(label(metadata["model"].toString(), hero, "panelTitle"));
  identity->addWidget(label(metadata["path"].toString()+" · "+driveStatus(metadata)+" · "+
      QString::number(metadata["partitions"].toInt())+" partitions", hero, "muted"));
  heroLayout->addLayout(identity, 1);
  heroLayout->addWidget(label(capacity(metadata["size"].toDouble()), hero, "panelTitle"));
  layout->addWidget(hero);
  auto *details = new QGridLayout;
  const QList<QPair<QString, QString>> fields = {
      {"Device path", metadata["path"].toString()}, {"Connection", metadata["connection"].toString().toUpper()},
      {"Disk ID", metadata["disk_id"].toString()}, {"Partition table", metadata["partition_table"].toString().toUpper()},
      {"Serial number", metadata["serial"].toString()}, {"WWN", metadata["wwn"].toString()},
      {"Mount points", mountPoints(metadata["mountpoints"])}, {"Access", metadata["read_only"].toBool() ? "Read-only" : "Read/write"},
      {"Capacity in bytes", QLocale().toString(qint64(metadata["size"].toDouble()))},
      {"Removable", metadata["removable"].toBool() ? "Yes" : "No"}};
  for (int i = 0; i < fields.size(); ++i) {
    const int row = i/2, column = (i%2)*2;
    details->addWidget(label(fields[i].first, &dialog, "muted"), row, column);
    auto *value = label(fields[i].second.isEmpty() ? "—" : fields[i].second, &dialog);
    value->setTextInteractionFlags(Qt::TextSelectableByMouse); details->addWidget(value, row, column+1);
  }
  details->setColumnStretch(1, 1); details->setColumnStretch(3, 1);
  details->setHorizontalSpacing(18); details->setVerticalSpacing(10); layout->addLayout(details);
  layout->addWidget(label("Partitions & volumes", &dialog, "panelTitle"));
  auto *volumes = new QTreeWidget(&dialog); volumes->setObjectName("grubVolumeDetails");
  volumes->setHeaderLabels({"Device", "Device path", "Size", "Type", "File system", "Label", "Mount point", "Status", "Disk ID", "UUID", "Partition UUID", "Partition type"});
  volumes->setRootIsDecorated(false); volumes->setAlternatingRowColors(true);
  volumes->setSelectionBehavior(QAbstractItemView::SelectRows);
  volumes->setEditTriggers(QAbstractItemView::NoEditTriggers);
  volumes->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
  for (const auto &value : metadata["volumes"].toArray()) {
    const auto volume = value.toObject();
    const auto mount = mountPoints(volume["mountpoints"]);
    const QStringList values = {QFileInfo(volume["path"].toString()).fileName(), volume["path"].toString(),
        capacity(volume["size"].toDouble()), volume["type"].toString(), volume["fstype"].toString(),
        volume["label"].toString(), mount, mount.isEmpty() ? "Not mounted" : "Mounted", metadata["disk_id"].toString(),
        volume["uuid"].toString(), volume["partuuid"].toString(), volume["parttype"].toString()};
    auto *row = new QTreeWidgetItem(volumes);
    row->setIcon(0, QIcon::fromTheme("drive-harddisk"));
    for (int i = 0; i < values.size(); ++i) {
      row->setText(i, values[i].isEmpty() ? "—" : values[i]); row->setToolTip(i, values[i]);
    }
  }
  volumes->header()->setSectionResizeMode(QHeaderView::ResizeToContents);
  volumes->setMinimumHeight(110); layout->addWidget(volumes, 1);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, &dialog);
  auto *copy = buttons->addButton("Copy details", QDialogButtonBox::ActionRole);
  copy->setIcon(QIcon::fromTheme("edit-copy"));
  connect(copy, &QPushButton::clicked, &dialog, [metadata] {
    QApplication::clipboard()->setText(QString::fromUtf8(QJsonDocument(metadata).toJson(QJsonDocument::Indented)));
  });
  connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  layout->addWidget(buttons);
  const auto available = screen()->availableGeometry().size();
  dialog.resize(qMin(1100, available.width()-60), qMin(600, available.height()-60));
  dialog.exec();
}
void GrubEditor::chooseSystem() {
  const auto target = system();
  name->setText(target["title"].toString());
  selection->setText(target.isEmpty() ? "Select a drive above to find Windows or Linux." :
    target.value("available").toBool() ? target["title"].toString()+" is ready to add. You can change its menu name below."+
        "\n"+target["partition"].toString()+" · "+target["loader"].toString()+
        (target["detail"].toString().isEmpty() ? QString() : "\n"+target["detail"].toString()) : target["reason"].toString());
  updateActions();
}
void GrubEditor::request(const QJsonObject &data) {
  if (busy) return;
  pending = data; pending["revision"] = revision;
  operation = data["action"].toString();
  status->setText(operation == "scan" ? "Detecting the system. Authenticate if prompted…" : "Working on your boot menu…");
  setBusy(true);
  if (worker->state() == QProcess::Running) {
    worker->write(QJsonDocument(pending).toJson(QJsonDocument::Compact)+'\n'); pending = {};
  } else { output.clear(); errors.clear(); worker->start("python3", {helper, "connect"}); }
}
void GrubEditor::readWorker() {
  output += worker->readAllStandardOutput();
  while (output.contains('\n')) {
    const int end = output.indexOf('\n');
    const auto data = QJsonDocument::fromJson(output.left(end)).object(); output.remove(0, end+1);
    if (data.contains("progress")) status->setText(data["progress"].toString());
    else if (data.contains("result")) { result(data["result"].toObject()); setBusy(false); }
    else if (data.contains("error")) {
      status->setText(data["error"].toString());
      setBusy(false);
    }
  }
}
void GrubEditor::result(const QJsonObject &data) {
  if (data.contains("supported")) supported = data["supported"].toBool();
  if (data.contains("mode")) mode->setText(data["mode"] == "uefi" ?
      "UEFI" + QString(data["secure_boot"].toBool() ? " · Secure Boot" : "") : "Legacy BIOS");
  if (data.contains("drives")) {
    const auto previous = drive();
    const QSignalBlocker guard(drives); drives->clear();
    for (const auto &value : data["drives"].toArray()) {
      const auto metadata = value.toObject();
      auto *row = new QTreeWidgetItem(drives, {metadata["model"].toString(), metadata["path"].toString(),
          capacity(metadata["size"].toDouble()), driveStatus(metadata)});
      row->setIcon(0, QIcon::fromTheme(metadata["removable"].toBool() ? "drive-removable-media" : "drive-harddisk"));
      row->setData(0, Qt::UserRole, metadata);
      row->setToolTip(0, metadata["path"].toString()+"\nSerial: "+metadata["serial"].toString());
      if (metadata["token"] == previous["token"]) drives->setCurrentItem(row);
    }
    driveCount->setText(QString("%1 drives · mounted and unmounted").arg(drives->topLevelItemCount()));
    const int rowHeight = drives->topLevelItemCount() ? drives->sizeHintForRow(0) : 24;
    drives->setMinimumHeight(qBound(140, drives->header()->sizeHint().height()+
        rowHeight*drives->topLevelItemCount()+8, 270));
    if (!drives->currentItem()) selection->setText("Select a drive above to find Windows or Linux.");
    else if (operation == "refresh") selection->setText("Select Detect bootable systems to inspect this drive’s partitions.");
  }
  if (data.contains("revision")) revision = data["revision"].toString();
  if (data.contains("can_undo")) canUndo = data["can_undo"].toBool();
  if (data.contains("entries")) {
    entries->clear();
    for (const auto &value : data["entries"].toArray()) {
      const auto item = value.toObject();
      auto *row = new QListWidgetItem(QIcon::fromTheme(item["title"].toString().startsWith("Windows") ? "computer" : "distributor-logo"), item["name"].toString(), entries);
      row->setData(Qt::UserRole, item); row->setToolTip(item["title"].toString()+" · "+item["drive"].toString());
    }
    if (entries->count()) entries->setCurrentRow(0);
    saved->setText(entries->count() ? QString("%1 saved %2 · Existing entries are kept.").arg(entries->count()).arg(entries->count() == 1 ? "entry" : "entries") : "No entries added with this editor yet. Existing GRUB entries are kept.");
    load->setVisible(revision.isEmpty());
  }
  if (data.contains("candidates")) {
    systems->clear();
    int first = -1;
    for (const auto &value : data["candidates"].toArray()) {
      const auto target = value.toObject();
      const auto method = target["kind"] == "config" ? "GRUB menu" :
          target["kind"] == "legacy-windows" ? "BIOS bootloader" : "UEFI bootloader";
      auto *row = new QListWidgetItem(QIcon::fromTheme(target["title"].toString().startsWith("Windows") ? "computer" : "distributor-logo"),
          target["title"].toString()+"  ·  "+method+"  ·  "+QFileInfo(target["partition"].toString()).fileName(), systems);
      row->setData(Qt::UserRole, target);
      row->setToolTip(target.value("available").toBool() ? target["loader"].toString() : target["reason"].toString());
      if (target.value("available").toBool() && first < 0) first = systems->count()-1;
    }
    if (systems->count()) systems->setCurrentRow(first < 0 ? 0 : first);
    else selection->setText("No supported bootloader was detected on this drive.");
    QStringList messages;
    for (const auto &note : data["notes"].toArray()) messages.append(note.toString());
    notes->setText(messages.join('\n')); notes->setVisible(!messages.isEmpty());
    status->setText(first >= 0 ? "Detected. Choose the name you want in GRUB, then Add to GRUB." : "Choose another drive or check the detection details above.");
  } else status->setText(data.value("message").toString("Choose a drive to add its system to GRUB."));
  if (data.contains("backup")) saved->setToolTip("Backup: "+data["backup"].toString());
}
