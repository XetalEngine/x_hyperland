#include "runtime_log_guard.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QtWidgets>

namespace {
QString sizeText(double bytes) {
  return QString::number(bytes / (1024. * 1024.), 'f', 1) + " MiB";
}
QLabel *plain(const QString &text, QWidget *parent) {
  auto *label = new QLabel(text, parent);
  label->setTextFormat(Qt::PlainText); label->setWordWrap(true);
  return label;
}
}

RuntimeLogGuard::RuntimeLogGuard(const QString &helper, QWidget *parent)
    : QGroupBox("Hyprland log guard", parent), helper(helper) {
  setObjectName("runtimeLogGuard");
  auto *layout = new QVBoxLayout(this);
  auto *row = new QHBoxLayout;
  enabled = new QCheckBox("Protect session runtime space", this);
  enabled->setObjectName("logGuardEnabled"); enabled->setEnabled(false);
  row->addWidget(enabled, 1);
  check = new QPushButton("Check logs now", this);
  check->setObjectName("logGuardCheck"); check->setEnabled(false);
  check->setIcon(QIcon::fromTheme("view-refresh")); row->addWidget(check);
  layout->addLayout(row);
  layout->addWidget(plain("Every minute, clear Hyprland and Hyper Fusion session logs larger than 64 MiB. "
                         "This helps keep temporary space available for opening apps. "
                         "Cleared log contents are discarded; logging continues normally.", this));
  summary = plain("Reading protection status…", this);
  summary->setObjectName("logGuardStatus"); layout->addWidget(summary);
  layout->addSpacing(12);
  disableFiles = new QCheckBox("Disable session logs to file", this);
  disableFiles->setObjectName("sessionFileLogsDisabled"); disableFiles->setEnabled(false);
  layout->addWidget(disableFiles);
  layout->addWidget(plain("Applies at your next Hyprland login. Stops normal Hyprland file logging and "
                         "Hyper Fusion helper logs. Existing log files are kept.", this));
  loggingStatus = plain("", this);
  loggingStatus->setObjectName("sessionFileLogsStatus"); layout->addWidget(loggingStatus);
  message = plain("", this); message->setObjectName("logGuardMessage");
  message->hide(); layout->addWidget(message);
  process = new QProcess(this);
  refresh = new QTimer(this); refresh->setInterval(5000);
  timeout = new QTimer(this); timeout->setSingleShot(true); timeout->setInterval(5000);
  connect(refresh, &QTimer::timeout, this, [this] { request("--status"); });
  connect(timeout, &QTimer::timeout, process, &QProcess::kill);
  connect(enabled, &QCheckBox::clicked, this, [this](bool choice) { request(choice ? "--enable" : "--disable"); });
  connect(disableFiles, &QCheckBox::clicked, this, [this](bool choice) {
    request(choice ? "--disable-file-logs" : "--enable-file-logs");
  });
  connect(check, &QPushButton::clicked, this, [this] { request("--once"); });
  connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this](int code, QProcess::ExitStatus) { finish(code); });
  connect(process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) finish(-1);
  });
}

RuntimeLogGuard::~RuntimeLogGuard() {
  if (process->state() != QProcess::NotRunning) { process->kill(); process->waitForFinished(1000); }
}
void RuntimeLogGuard::showEvent(QShowEvent *event) {
  QGroupBox::showEvent(event); request("--status"); refresh->start();
}
void RuntimeLogGuard::hideEvent(QHideEvent *event) {
  refresh->stop(); QGroupBox::hideEvent(event);
}
void RuntimeLogGuard::request(const QString &command) {
  if (process->state() != QProcess::NotRunning) return;
  action = command;
  enabled->setEnabled(false); check->setEnabled(false); disableFiles->setEnabled(false);
  process->start("python3", {helper, command}); process->closeWriteChannel(); timeout->start();
}
void RuntimeLogGuard::finish(int code) {
  timeout->stop();
  const auto data = QJsonDocument::fromJson(process->readAllStandardOutput()).object();
  process->readAllStandardError();
  if (code || !data.contains("enabled")) {
    const QSignalBlocker blocked(enabled); enabled->setChecked(previousEnabled);
    disableFiles->setChecked(previousDisableFiles); disableFiles->setEnabled(true);
    message->setText(data.value("error").toString("Could not read or change log protection. Try again."));
    message->show(); enabled->setEnabled(true); check->setEnabled(true); return;
  }
  previousEnabled = data["enabled"].toBool();
  enabled->setChecked(previousEnabled); enabled->setEnabled(true);
  previousDisableFiles = data["file_logs_disabled"].toBool();
  disableFiles->setChecked(previousDisableFiles); disableFiles->setEnabled(true);
  if (data["logging_pending"].toBool())
    loggingStatus->setText(previousDisableFiles ? "File logging will be disabled at your next Hyprland login." :
        "Normal file logging will resume at your next Hyprland login.");
  else if (data["active"].toBool())
    loggingStatus->setText(data["session_file_logs_disabled"].toBool() ? "File logging disabled for this session." :
        "This session uses normal file logging.");
  else loggingStatus->setText(previousDisableFiles ? "File logging will be disabled at your next Hyprland login." :
        "Normal file logging is selected.");
  const auto loggingError = data["logging_error"].toString();
  if (!loggingError.isEmpty()) loggingStatus->setText(loggingError + " Hyper Fusion helper logs are disabled.");
  check->setEnabled(data["active"].toBool());
  const auto state = !previousEnabled ? "Paused" : data["running"].toBool() ? "Protecting this session" : "Enabled · starts at Hyprland login";
  QString text = state;
  if (data["active"].toBool()) text += " · Logs: " + sizeText(data["used"].toDouble()) +
      " · Runtime space free: " + sizeText(data["runtime_free"].toDouble());
  summary->setText(text);
  if (action == "--once") {
    const auto result = data["checked"].toObject();
    const int count = result["cleared"].toArray().size();
    message->setText(count ? QString("Cleared %1 oversized %2 and freed %3.")
        .arg(count).arg(count == 1 ? "log" : "logs").arg(sizeText(result["freed"].toDouble())) : "Checked. All managed logs are below the limit.");
    if (!result["errors"].toArray().isEmpty()) message->setText("Some logs could not be checked. " + result["errors"].toArray()[0].toString());
    message->show();
  } else if (action == "--disable-file-logs" || action == "--enable-file-logs") {
    message->setText("Saved. The file logging preference applies at the next Hyprland login."); message->show();
  } else if (action != "--status") {
    message->setText(previousEnabled ? "Protection enabled for this session and future Hyprland logins." :
        "Automatic cleanup paused. You can still check logs manually."); message->show();
  }
}
