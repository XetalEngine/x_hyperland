#include "ventoy_page.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QtWidgets>

namespace {
QLabel *label(const QString &text, QWidget *parent) {
  auto *item = new QLabel(text, parent);
  item->setWordWrap(true);
  item->setTextFormat(Qt::PlainText);
  return item;
}
QString capacity(double value) {
  const double gib = value / (1024. * 1024. * 1024.);
  return gib >= 1024 ? QString::number(gib / 1024., 'f', 2) + " TiB"
                     : QString::number(gib, 'f', 1) + " GiB";
}
QString diskName(const QJsonObject &disk) {
  return QString("%1 · %2 · %3").arg(disk["model"].toString(), capacity(disk["size"].toDouble()), disk["path"].toString());
}
}

VentoyPage::VentoyPage(const QString &profileRoot, QWidget *parent)
    : QWidget(parent), root(profileRoot), helper(root + "/control_panel/ventoy.py") {
  setObjectName("ventoyTab");
  auto *layout = new QVBoxLayout(this);
  layout->setSpacing(14);
  auto *title = label("One USB. Many bootable images.", this);
  title->setObjectName("panelTitle");
  layout->addWidget(title);
  layout->addWidget(label("Create a Ventoy USB once, then copy ISO files onto it in Fusion Files. Choose an image from Ventoy’s menu when you boot the USB.", this));
  bundle = label("Checking the bundled offline engine…", this);
  bundle->setObjectName("ventoyBundle");
  layout->addWidget(bundle);

  auto *deviceBox = new QGroupBox("USB disk", this);
  auto *deviceLayout = new QVBoxLayout(deviceBox);
  auto *deviceRow = new QHBoxLayout;
  disks = new QComboBox(deviceBox);
  disks->setObjectName("ventoyDisks");
  disks->setMinimumContentsLength(24);
  disks->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
  disks->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  disks->setAccessibleName("USB disk to prepare");
  refreshButton = new QPushButton(QIcon::fromTheme("view-refresh"), "Refresh", deviceBox);
  refreshButton->setObjectName("ventoyRefresh");
  deviceRow->addWidget(disks, 1);
  deviceRow->addWidget(refreshButton);
  deviceLayout->addLayout(deviceRow);
  details = label("Connect a USB disk to get started. Internal drives are excluded.", deviceBox);
  details->setObjectName("ventoyDetails");
  details->setTextInteractionFlags(Qt::TextSelectableByMouse);
  deviceLayout->addWidget(details);
  layout->addWidget(deviceBox);

  auto *options = new QGroupBox("New USB options", this);
  auto *form = new QFormLayout(options);
  form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
  form->setRowWrapPolicy(QFormLayout::WrapLongRows);
  style = new QComboBox(options);
  style->setObjectName("ventoyStyle");
  style->addItem("MBR · broad BIOS and UEFI compatibility", "mbr");
  style->addItem("GPT · modern systems and disks larger than 2 TiB", "gpt");
  secure = new QCheckBox("Include Secure Boot support", options);
  secure->setObjectName("ventoySecureBoot");
  secure->setChecked(true);
  form->addRow("Partition style", style);
  form->addRow(QString(), secure);
  form->addRow(label("Updates preserve the disk’s partition style and Secure Boot setting. Some PCs require Ventoy’s key to be enrolled at first boot.", options));
  layout->addWidget(options);

  auto *actions = new QHBoxLayout;
  createButton = new QPushButton(QIcon::fromTheme("drive-removable-media"), "Create Ventoy USB…", this);
  createButton->setObjectName("ventoyCreate");
  createButton->setProperty("primary", true);
  updateButton = new QPushButton(QIcon::fromTheme("system-software-update"), "Update Ventoy…", this);
  updateButton->setObjectName("ventoyUpdate");
  openButton = new QPushButton(QIcon::fromTheme("folder-open"), "Open in Fusion Files", this);
  openButton->setObjectName("ventoyOpen");
  actions->addWidget(createButton);
  actions->addWidget(updateButton);
  actions->addWidget(openButton);
  actions->addStretch();
  layout->addLayout(actions);
  layout->addWidget(label("Creating a new Ventoy USB erases the entire selected disk. Updating an existing Ventoy USB keeps its ISO files.", this));

  status = label("Select a USB disk. Nothing is written until you confirm and authenticate.", this);
  status->setObjectName("ventoyStatus");
  status->setTextInteractionFlags(Qt::TextSelectableByMouse);
  layout->addWidget(status);
  progress = new QProgressBar(this);
  progress->setObjectName("ventoyProgress");
  progress->setRange(0, 0);
  progress->setTextVisible(false);
  progress->hide();
  layout->addWidget(progress);
  auto *logRow = new QHBoxLayout;
  logRow->addWidget(label("Operation log", this));
  logRow->addStretch();
  saveButton = new QPushButton("Save log…", this);
  saveButton->setEnabled(false);
  logRow->addWidget(saveButton);
  layout->addLayout(logRow);
  log = new QPlainTextEdit(this);
  log->setObjectName("ventoyLog");
  log->setReadOnly(true);
  log->setMaximumBlockCount(3000);
  log->setPlaceholderText("Progress and results appear here. Your USB files stay in Fusion Files.");
  log->setMinimumHeight(100);
  layout->addWidget(log, 1);

  scanProcess = new QProcess(this);
  worker = new QProcess(this);
  refreshTimer = new QTimer(this);
  refreshTimer->setInterval(5000);
  scanTimeout = new QTimer(this);
  scanTimeout->setSingleShot(true);
  connect(refreshTimer, &QTimer::timeout, this, &VentoyPage::refresh);
  connect(scanTimeout, &QTimer::timeout, this, [this] { scanProcess->kill(); });
  connect(refreshButton, &QPushButton::clicked, this, &VentoyPage::refresh);
  connect(disks, qOverload<int>(&QComboBox::currentIndexChanged), this, &VentoyPage::selectionChanged);
  connect(createButton, &QPushButton::clicked, this, [this] { confirm("install"); });
  connect(updateButton, &QPushButton::clicked, this, [this] { confirm("update"); });
  connect(openButton, &QPushButton::clicked, this, [this] { start("open", selected()); });
  connect(saveButton, &QPushButton::clicked, this, [this] {
    const auto path = QFileDialog::getSaveFileName(this, "Save Ventoy log", QDir::homePath() + "/ventoy-log.txt", "Text files (*.txt)");
    if (path.isEmpty()) return;
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(log->toPlainText().toUtf8()) < 0 || !file.commit())
      QMessageBox::warning(this, "Ventoy USB", "The log could not be saved: " + file.errorString());
  });
  connect(scanProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this](int code, QProcess::ExitStatus exit) {
    scanTimeout->stop();
    scanning = false;
    auto data = QJsonDocument::fromJson(scanProcess->readAllStandardOutput()).object();
    scanProcess->readAllStandardError();
    if (!code && exit == QProcess::NormalExit && data["ok"].toBool()) display(data);
    else {
      disks->clear();
      details->setText(data["error"].toString("USB discovery failed. Refresh to try again."));
      updateControls();
    }
  });
  connect(scanProcess, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error != QProcess::FailedToStart) return;
    scanning = false;
    scanTimeout->stop();
    disks->clear();
    details->setText("Could not start USB discovery.");
    updateControls();
  });
  connect(worker, &QProcess::readyReadStandardOutput, this, &VentoyPage::readOutput);
  connect(worker, &QProcess::readyReadStandardError, this, [this] {
    errors += worker->readAllStandardError();
    errors = errors.right(4000);
  });
  connect(worker, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this](int code, QProcess::ExitStatus exit) { finish(exit == QProcess::NormalExit ? code : -1); });
  connect(worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) {
      completion = {{"error", "Could not start the Ventoy helper."}};
      finish(-1);
    }
  });
  qApp->installEventFilter(this);
  updateControls();
}

VentoyPage::~VentoyPage() {
  worker->closeWriteChannel();
  if (scanProcess->state() != QProcess::NotRunning) {
    scanProcess->kill();
    scanProcess->waitForFinished(1000);
  }
}
void VentoyPage::showEvent(QShowEvent *event) {
  QWidget::showEvent(event);
  refresh();
  refreshTimer->start();
}
void VentoyPage::hideEvent(QHideEvent *event) {
  refreshTimer->stop();
  QWidget::hideEvent(event);
}
bool VentoyPage::eventFilter(QObject *object, QEvent *event) {
  if (busy && operation != "open" && object == window() && event->type() == QEvent::Close) {
    static_cast<QCloseEvent *>(event)->ignore();
    status->setText("Ventoy is still working. Keep the USB connected and wait for completion before closing Control Panel.");
    return true;
  }
  return QWidget::eventFilter(object, event);
}
QJsonObject VentoyPage::selected() const { return disks->currentData().toJsonObject(); }
void VentoyPage::refresh() {
  if (busy || scanning || confirming) return;
  scanning = true;
  updateControls();
  scanProcess->start("/usr/bin/python3", {"-I", helper, "status"});
  scanProcess->closeWriteChannel();
  scanTimeout->start(25000);
}
void VentoyPage::display(const QJsonObject &data) {
  const auto old = selected()["identity"].toString();
  QSignalBlocker blocker(disks);
  disks->clear();
  const auto problem = data["bundle_error"].toString();
  bundleReady = problem.isEmpty();
  bundle->setText(bundleReady ? QString("Ventoy %1 · Bundled and verified · Ready offline").arg(data["version"].toString()) : problem);
  int restore = -1;
  for (const auto &value : data["disks"].toArray()) {
    const auto disk = value.toObject();
    QString name = diskName(disk);
    if (!disk["blocked"].toString().isEmpty()) name += " · Unavailable";
    else if (disk["ventoy"].toBool()) name += " · Ventoy";
    disks->addItem(QIcon::fromTheme("drive-removable-media"), name, disk);
    if (!old.isEmpty() && disk["identity"].toString() == old) restore = disks->count() - 1;
  }
  // Do not silently select a different disk when the chosen USB is unplugged.
  if (restore >= 0) disks->setCurrentIndex(restore);
  else if (disks->count()) {
    disks->insertItem(0, "Select a USB disk…", QJsonObject());
    disks->setCurrentIndex(0);
  }
  selectionChanged();
}
void VentoyPage::selectionChanged() {
  const auto disk = selected();
  if (disk.isEmpty()) details->setText(disks->count() ? "Choose the USB disk you want to prepare." : "No USB disks found. Connect one and refresh. Internal drives are excluded.");
  else {
    const auto blocked = disk["blocked"].toString();
    auto text = diskName(disk);
    if (!disk["serial"].toString().isEmpty()) text += "\nSerial: " + disk["serial"].toString();
    text += "\n" + (blocked.isEmpty() ? (disk["ventoy"].toBool()
          ? "Ventoy detected. Update its boot files or open the data partition."
          : "Ready to create a new Ventoy USB. All existing partitions and files will be erased.") : blocked);
    details->setText(text);
    if (!disk["ventoy"].toBool() && disk["size"].toDouble() > 2. * 1024 * 1024 * 1024 * 1024) style->setCurrentIndex(1);
  }
  updateControls();
}
void VentoyPage::updateControls() {
  const auto disk = selected();
  const bool ready = !busy && !scanning && !confirming && !disk.isEmpty() && disk["blocked"].toString().isEmpty();
  const bool existing = disk["ventoy"].toBool();
  disks->setEnabled(!busy && !confirming);
  refreshButton->setEnabled(!busy && !scanning && !confirming);
  createButton->setEnabled(ready && bundleReady && !existing);
  updateButton->setEnabled(ready && bundleReady && existing);
  openButton->setEnabled(ready && existing);
  style->setEnabled(!busy && !confirming && !existing);
  secure->setEnabled(!busy && !confirming && !existing);
}
void VentoyPage::confirm(const QString &action) {
  if (busy || scanning || confirming) return;
  const auto disk = selected();
  if (disk.isEmpty() || !disk["blocked"].toString().isEmpty()) return;
  confirming = true;
  updateControls();
  QDialog dialog(this);
  dialog.setObjectName("ventoyConfirmation");
  dialog.setWindowTitle(action == "install" ? "Create Ventoy USB" : "Update Ventoy");
  auto *layout = new QVBoxLayout(&dialog);
  layout->addWidget(label(diskName(disk), &dialog));
  if (!disk["serial"].toString().isEmpty()) layout->addWidget(label("Serial: " + disk["serial"].toString(), &dialog));
  QLineEdit *typed = nullptr;
  QCheckBox *ack = nullptr;
  if (action == "install") {
    layout->addWidget(label("This erases EVERY partition and file on this USB disk.\nType the device path below to confirm: " + disk["path"].toString(), &dialog));
    typed = new QLineEdit(&dialog);
    typed->setObjectName("ventoyConfirmPath");
    typed->setPlaceholderText(disk["path"].toString());
    layout->addWidget(typed);
    ack = new QCheckBox("I have saved anything I need from this disk.", &dialog);
    ack->setObjectName("ventoyConfirmErase");
    layout->addWidget(ack);
    layout->addWidget(label(style->currentText() + (secure->isChecked() ? "\nSecure Boot support enabled" : "\nSecure Boot support disabled"), &dialog));
  } else layout->addWidget(label("Update Ventoy’s boot files using the bundled version. Existing ISO files, partition style and Secure Boot setting are preserved.", &dialog));
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel, &dialog);
  auto *accept = buttons->addButton(action == "install" ? "Erase disk and create Ventoy" : "Update Ventoy", QDialogButtonBox::AcceptRole);
  accept->setObjectName("ventoyConfirmAccept");
  accept->setDefault(false);
  buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
  if (typed) {
    accept->setEnabled(false);
    auto validate = [=] { accept->setEnabled(typed->text() == disk["path"].toString() && ack->isChecked()); };
    connect(typed, &QLineEdit::textChanged, &dialog, validate);
    connect(ack, &QCheckBox::toggled, &dialog, validate);
    typed->setFocus();
  }
  connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  layout->addWidget(buttons);
  dialog.setMinimumWidth(480);
  const bool accepted = dialog.exec() == QDialog::Accepted;
  confirming = false;
  updateControls();
  if (!accepted) return;
  auto request = disk;
  request["style"] = style->currentData().toString();
  request["secure_boot"] = secure->isChecked();
  if (action == "install") request["erase_confirmed"] = disk["path"];
  start(action, request);
}
void VentoyPage::start(const QString &action, const QJsonObject &request) {
  if (busy || request.isEmpty()) return;
  busy = true;
  operation = action;
  pending.clear(); errors.clear(); completion = {};
  progress->show();
  status->setText(action == "open" ? "Opening the USB data partition…" : "Waiting for administrator authentication…");
  log->appendPlainText("\n" + QDateTime::currentDateTime().toString(Qt::ISODate) + " · " + action + " · " + diskName(request));
  saveButton->setEnabled(true);
  updateControls();
  QStringList args{"-I", helper};
  if (action != "open") args << "apply";
  args << action;
  worker->start("/usr/bin/python3", args);
  worker->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n');
  // Keep stdin open: the worker checks that the requesting GUI is still alive
  // after authentication and again before any write starts.
}
void VentoyPage::readOutput() {
  pending += worker->readAllStandardOutput();
  int end;
  while ((end = pending.indexOf('\n')) >= 0) {
    const auto message = QJsonDocument::fromJson(pending.left(end)).object();
    pending.remove(0, end + 1);
    if (message.contains("stage")) {
      status->setText(message["stage"].toString());
      log->appendPlainText(message["stage"].toString());
    }
    if (message.contains("log")) log->appendPlainText(message["log"].toString());
    if (message.contains("ok") || message.contains("error")) completion = message;
  }
  if (pending.size() > 32768) pending.clear();
}
void VentoyPage::finish(int code) {
  if (!busy) return;
  readOutput();
  worker->closeWriteChannel();
  busy = false;
  progress->hide();
  if (!code && completion["ok"].toBool()) {
    if (operation == "open") {
      const auto path = completion["mountpoint"].toString();
      const bool opened = !path.isEmpty() && QProcess::startDetached(root + "/scripts/files.sh", {path});
      status->setText(opened ? "USB opened in Fusion Files. Copy your ISO files into this folder." : "The USB is mounted, but Fusion Files could not be opened.");
    } else status->setText(completion["message"].toString("Ventoy operation completed."));
  } else {
    QString error = completion["error"].toString();
    if (error.isEmpty() && code == 126) error = "Administrator authentication was cancelled. The USB was not changed.";
    if (error.isEmpty()) error = QString::fromUtf8(errors).trimmed().left(1000);
    if (error.isEmpty()) error = "The Ventoy operation did not complete. Review the log and refresh the USB list.";
    status->setText(error);
  }
  log->appendPlainText(status->text());
  updateControls();
  refresh();
}
