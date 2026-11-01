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
  return QString::number(size / (size >= 1e12 ? 1e12 : 1e9), 'f', 1) + (size >= 1e12 ? " TB" : " GB");
}
QJsonObject itemData(QListWidget *list) {
  return list->currentItem() ? list->currentItem()->data(Qt::UserRole).toJsonObject() : QJsonObject();
}
}

GrubEditor::GrubEditor(const QString &helper, QWidget *parent) : QWidget(parent), helper(helper) {
  setObjectName("grubEditorTab");
  auto *layout = new QVBoxLayout(this);
  layout->setSpacing(14);
  auto *heading = new QHBoxLayout;
  heading->addWidget(label("GRUB Boot Editor", this, "panelTitle"), 1);
  mode = label("", this, "muted"); heading->addWidget(mode);
  layout->addLayout(heading);
  layout->addWidget(label("Your drives. One boot menu.\nChoose a drive, name its system, and add it to GRUB.", this));

  auto *driveBox = new QGroupBox("1  Choose a drive", this);
  auto *driveLayout = new QVBoxLayout(driveBox);
  auto *driveRow = new QHBoxLayout;
  drives = new QComboBox(driveBox); drives->setObjectName("grubDrives");
  drives->setMinimumContentsLength(28);
  drives->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
  driveRow->addWidget(drives, 1);
  refresh = new QPushButton("Refresh drives", driveBox); refresh->setObjectName("grubRefresh");
  refresh->setIcon(QIcon::fromTheme("view-refresh")); driveRow->addWidget(refresh);
  driveLayout->addLayout(driveRow);
  driveLayout->addWidget(label("Partitions and boot files are detected automatically.", driveBox, "muted"));
  layout->addWidget(driveBox);

  auto *systemBox = new QGroupBox("2  Your system", this);
  auto *systemLayout = new QVBoxLayout(systemBox);
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
  layout->addWidget(systemBox);

  progress = new QProgressBar(this); progress->setRange(0, 0);
  progress->setTextVisible(false); progress->setFixedHeight(6); progress->hide(); layout->addWidget(progress);
  status = label("Choose the drive you want to add. Administrator authentication is requested when needed.", this, "grubStatus");
  status->setTextInteractionFlags(Qt::TextSelectableByMouse); layout->addWidget(status);

  auto *savedBox = new QGroupBox("Entries added with this editor", this);
  auto *savedLayout = new QVBoxLayout(savedBox);
  entries = new QListWidget(savedBox); entries->setObjectName("grubEntries");
  entries->setMinimumHeight(70); savedLayout->addWidget(entries, 1);
  saved = label("Your existing GRUB entries are kept.", savedBox, "grubSaved"); savedLayout->addWidget(saved);
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
  connect(drives, &QComboBox::currentIndexChanged, this, &GrubEditor::chooseDrive);
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
      if (operation == "scan") { const QSignalBlocker guard(drives); drives->setCurrentIndex(0); }
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
QJsonObject GrubEditor::system() const { return itemData(systems); }
QJsonObject GrubEditor::entry() const { return itemData(entries); }
void GrubEditor::setBusy(bool value) { busy = value; progress->setVisible(value); updateActions(); }
void GrubEditor::updateActions() {
  drives->setEnabled(!busy && supported); refresh->setEnabled(!busy);
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
  if (busy || drives->currentIndex() < 1) return;
  const auto drive = drives->currentData().toJsonObject();
  systems->clear(); name->clear(); notes->hide();
  selection->setText("Finding bootable systems on this drive…");
  request({{"action", "scan"}, {"drive", drive["path"]}, {"drive_token", drive["token"]}});
}
void GrubEditor::chooseSystem() {
  const auto target = system();
  name->setText(target["title"].toString());
  selection->setText(target.isEmpty() ? "Select a drive above to find Windows or Linux." :
    target.value("available").toBool() ? target["title"].toString()+" is ready to add. You can change its menu name below."+
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
      if (operation == "scan") { const QSignalBlocker guard(drives); drives->setCurrentIndex(0); }
      setBusy(false);
    }
  }
}
void GrubEditor::result(const QJsonObject &data) {
  if (data.contains("supported")) supported = data["supported"].toBool();
  if (data.contains("mode")) mode->setText(data["mode"] == "uefi" ?
      "UEFI" + QString(data["secure_boot"].toBool() ? " · Secure Boot" : "") : "Legacy BIOS");
  if (data.contains("drives")) {
    const auto previous = operation == "refresh" ? QJsonObject() : drives->currentData().toJsonObject();
    const QSignalBlocker guard(drives); drives->clear(); drives->addItem("Select a drive…");
    for (const auto &value : data["drives"].toArray()) {
      const auto drive = value.toObject();
      drives->addItem(QIcon::fromTheme("drive-harddisk"), drive["model"].toString()+" · "+
          capacity(drive["size"].toDouble())+" · "+QFileInfo(drive["path"].toString()).fileName(), drive);
      drives->setItemData(drives->count()-1, drive["path"].toString()+"\nSerial: "+drive["serial"].toString(), Qt::ToolTipRole);
      if (drive["token"] == previous["token"]) drives->setCurrentIndex(drives->count()-1);
    }
    if (drives->currentIndex() == 0) selection->setText("Select a drive above to find Windows or Linux.");
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
      auto *row = new QListWidgetItem(QIcon::fromTheme(target["title"].toString().startsWith("Windows") ? "computer" : "distributor-logo"), target["title"].toString(), systems);
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
