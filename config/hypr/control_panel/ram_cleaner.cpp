#include "ram_cleaner.h"
#include <QJsonDocument>
#include <QProcess>
#include <QtWidgets>

namespace {
QString sizeText(double bytes) {
  return bytes >= 1024. * 1024. * 1024.
      ? QString::number(bytes / (1024. * 1024. * 1024.), 'f', 1) + " GiB"
      : QString::number(bytes / (1024. * 1024.), 'f', 0) + " MiB";
}
QString changeText(double bytes) {
  return (bytes < 0 ? QStringLiteral("−") : QStringLiteral("+")) + sizeText(qAbs(bytes));
}
QLabel *textLabel(const QString &text, QWidget *parent) {
  auto *label = new QLabel(text, parent);
  label->setWordWrap(true);
  label->setTextFormat(Qt::PlainText);
  return label;
}
}

RamCleaner::RamCleaner(const QString &helper, QWidget *parent)
    : QWidget(parent), helper(helper) {
  setObjectName("ramCleanerTab");
  auto *layout = new QVBoxLayout(this);
  layout->setSpacing(16);
  auto *title = textLabel("RAM Cleaner", this);
  title->setObjectName("panelTitle");
  layout->addWidget(title);
  layout->addWidget(textLabel("Release unused system caches while your apps and virtual machines keep running.", this));

  auto *overview = new QGroupBox("Memory right now", this);
  auto *overviewLayout = new QVBoxLayout(overview);
  auto *cards = new QHBoxLayout;
  auto card = [&](const QString &heading, const QString &name) {
    auto *box = new QFrame(overview);
    box->setObjectName("ramMetric");
    auto *column = new QVBoxLayout(box);
    auto *caption = textLabel(heading, box);
    caption->setObjectName("muted");
    column->addWidget(caption);
    auto *value = new QLabel("—", box);
    value->setObjectName(name);
    value->setProperty("ramValue", true);
    column->addWidget(value);
    cards->addWidget(box, 1);
    return value;
  };
  available = card("Available RAM", "ramAvailable");
  fileCache = card("File cache", "ramFileCache");
  metadataCache = card("Metadata cache", "ramMetadataCache");
  swap = card("Swap in use", "ramSwap");
  overviewLayout->addLayout(cards);
  memoryBar = new QProgressBar(overview);
  memoryBar->setRange(0, 100);
  memoryBar->setValue(0);
  memoryBar->setTextVisible(false);
  memoryBar->setFixedHeight(10);
  overviewLayout->addWidget(memoryBar);
  capacity = textLabel("Reading memory…", overview);
  capacity->setObjectName("muted");
  overviewLayout->addWidget(capacity);
  layout->addWidget(overview);

  auto *modes = new QGroupBox("Cleanup mode", this);
  auto *modeLayout = new QHBoxLayout(modes);
  auto mode = [&](const QString &heading, const QString &detail, const QString &name) {
    auto *box = new QFrame(modes);
    box->setObjectName("ramMode");
    auto *column = new QVBoxLayout(box);
    auto *choice = new QRadioButton(heading, box);
    choice->setObjectName(name);
    connect(choice, &QRadioButton::toggled, box, [box](bool selected) {
      box->setProperty("selected", selected);
      box->style()->unpolish(box);
      box->style()->polish(box);
      box->update();
    });
    column->addWidget(choice);
    auto *description = textLabel(detail, box);
    description->setObjectName("muted");
    column->addWidget(description);
    modeLayout->addWidget(box, 1);
    return choice;
  };
  normal = mode("Normal", "Clear unused file cache. A lighter cleanup that keeps filesystem metadata cached.", "ramNormal");
  aggressive = mode("Aggressive", "Also clear reclaimable filesystem metadata, including cached folder and file information.", "ramAggressive");
  auto *choices = new QButtonGroup(this);
  choices->addButton(normal);
  choices->addButton(aggressive);
  normal->setChecked(true);
  layout->addWidget(modes);
  auto *note = textLabel(
      "Linux already reclaims caches when RAM is needed. Available RAM includes reclaimable cache.\n"
      "Cleanup may briefly slow file access as caches rebuild. It cannot free memory actively used by apps or VMs.", this);
  note->setObjectName("muted");
  layout->addWidget(note);

  auto *actions = new QHBoxLayout;
  clean = new QPushButton("Clean RAM", this);
  clean->setObjectName("ramCleanButton");
  clean->setProperty("primary", true);
  clean->setIcon(QIcon::fromTheme("edit-clear"));
  actions->addWidget(clean);
  auto *auth = textLabel("Administrator authentication is requested when you clean.", this);
  auth->setObjectName("muted");
  actions->addWidget(auth, 1);
  layout->addLayout(actions);
  progress = new QProgressBar(this);
  progress->setRange(0, 0);
  progress->setFixedHeight(6);
  progress->hide();
  layout->addWidget(progress);
  status = textLabel("Manual cleanup only. No apps are closed, no files are deleted, and swap settings stay unchanged.", this);
  status->setObjectName("ramStatus");
  layout->addWidget(status);
  resultBox = new QGroupBox("Last cleanup", this);
  auto *results = new QVBoxLayout(resultBox);
  result = textLabel("", resultBox);
  result->setObjectName("ramResult");
  result->setTextInteractionFlags(Qt::TextSelectableByMouse);
  results->addWidget(result);
  resultBox->hide();
  layout->addWidget(resultBox);
  layout->addStretch();

  statsProcess = new QProcess(this);
  cleanProcess = new QProcess(this);
  refreshTimer = new QTimer(this);
  refreshTimer->setInterval(2500);
  statsTimeout = new QTimer(this);
  statsTimeout->setSingleShot(true);
  statsTimeout->setInterval(5000);
  connect(statsTimeout, &QTimer::timeout, statsProcess, &QProcess::kill);
  connect(refreshTimer, &QTimer::timeout, this, &RamCleaner::refresh);
  connect(statsProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this](int code, QProcess::ExitStatus) {
    statsTimeout->stop();
    auto data = QJsonDocument::fromJson(statsProcess->readAllStandardOutput()).object();
    if (!busy) {
      if (!code && data.contains("total")) display(data);
      else capacity->setText("Memory readings are unavailable. They will refresh automatically.");
    }
    statsProcess->readAllStandardError();
  });
  connect(statsProcess, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) {
      statsTimeout->stop();
      capacity->setText("Could not start the memory reader.");
    }
  });
  connect(clean, &QPushButton::clicked, this, &RamCleaner::startCleanup);
  connect(cleanProcess, &QProcess::readyReadStandardOutput, this, &RamCleaner::readCleanup);
  connect(cleanProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this](int code, QProcess::ExitStatus exit) { finishCleanup(exit == QProcess::NormalExit ? code : -1); });
  connect(cleanProcess, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) {
      completion = {{"error", "Could not start the RAM cleaner helper."}};
      finishCleanup(-1);
    }
  });
}

RamCleaner::~RamCleaner() {
  if (statsProcess->state() != QProcess::NotRunning) {
    statsProcess->kill();
    statsProcess->waitForFinished(1000);
  }
  // The privileged helper checks this pipe before sync and before reclamation.
  cleanProcess->closeWriteChannel();
}
void RamCleaner::showEvent(QShowEvent *event) {
  QWidget::showEvent(event);
  refresh();
  refreshTimer->start();
}
void RamCleaner::hideEvent(QHideEvent *event) {
  refreshTimer->stop();
  QWidget::hideEvent(event);
}
void RamCleaner::refresh() {
  if (busy || statsProcess->state() != QProcess::NotRunning) return;
  statsProcess->start("python3", {helper, "status"});
  statsProcess->closeWriteChannel();
  statsTimeout->start();
}
void RamCleaner::display(const QJsonObject &data) {
  const auto total = data["total"].toDouble();
  const auto avail = data["available"].toDouble();
  available->setText(sizeText(avail));
  fileCache->setText(sizeText(data["file_cache"].toDouble()));
  metadataCache->setText(sizeText(data["metadata_cache"].toDouble()));
  swap->setText(data["swap_total"].toDouble() ? sizeText(data["swap_used"].toDouble()) : "Not configured");
  memoryBar->setValue(total > 0 ? qRound(100. * avail / total) : 0);
  capacity->setText(QString("%1 of %2 available · Updates every few seconds")
                       .arg(sizeText(avail), sizeText(total)));
}
void RamCleaner::startCleanup() {
  if (busy) return;
  busy = true;
  clean->setEnabled(false);
  normal->setEnabled(false);
  aggressive->setEnabled(false);
  progress->show();
  status->setText("Waiting for administrator authentication…");
  completion = {};
  cleanOutput.clear();
  cleanProcess->start("python3", {helper, "clean", aggressive->isChecked() ? "aggressive" : "normal"});
  // Leave stdin open so an abandoned authentication cannot trigger cleanup.
}
void RamCleaner::readCleanup() {
  cleanOutput += cleanProcess->readAllStandardOutput();
  int newline;
  while ((newline = cleanOutput.indexOf('\n')) >= 0) {
    const auto message = QJsonDocument::fromJson(cleanOutput.left(newline)).object();
    cleanOutput.remove(0, newline + 1);
    if (message["stage"] == "sync") status->setText("Finishing pending disk writes… Your apps can keep running.");
    else if (message["stage"] == "reclaim") status->setText("Releasing unused caches…");
    else if (message.contains("ok") || message.contains("error")) completion = message;
  }
}
void RamCleaner::finishCleanup(int code) {
  if (!busy) return;
  readCleanup();
  cleanProcess->closeWriteChannel();
  busy = false;
  clean->setEnabled(true);
  normal->setEnabled(true);
  aggressive->setEnabled(true);
  progress->hide();
  const auto errorOutput = QString::fromUtf8(cleanProcess->readAllStandardError()).trimmed().left(500);
  if (!code && completion["ok"].toBool()) {
    const auto before = completion["before"].toObject();
    const auto after = completion["after"].toObject();
    display(after);
    const auto cacheBefore = before["file_cache"].toDouble() + before["metadata_cache"].toDouble();
    const auto cacheAfter = after["file_cache"].toDouble() + after["metadata_cache"].toDouble();
    result->setText(QString("%1 · %2\nAvailable RAM: %3 → %4 (%5)\n"
                           "File + metadata cache: %6 → %7 (%8)\n"
                           "These are observed changes; running apps can allocate memory and rebuild caches during cleanup.")
        .arg(completion["mode"] == "aggressive" ? "Aggressive" : "Normal", QTime::currentTime().toString("HH:mm:ss"),
             sizeText(before["available"].toDouble()), sizeText(after["available"].toDouble()),
             changeText(after["available"].toDouble() - before["available"].toDouble()),
             sizeText(cacheBefore), sizeText(cacheAfter), changeText(cacheAfter - cacheBefore)));
    resultBox->show();
    status->setText("Cleanup complete. Your apps are still running.");
  } else if (code == 126) {
    status->setText("Authentication cancelled. No cleanup was performed.");
  } else {
    auto reason = completion["error"].toString();
    if (reason.isEmpty()) reason = errorOutput;
    if (reason.isEmpty()) reason = "Administrator authentication was unavailable or the helper stopped.";
    status->setText("Cleanup could not complete: " + reason);
  }
  if (isVisible()) refresh();
}
