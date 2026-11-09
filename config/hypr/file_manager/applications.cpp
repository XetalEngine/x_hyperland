#include "applications.h"
#include "core.h"
#include <KJob>
#include <KIO/Global>
#include <KIO/JobUiDelegateFactory>
#include <KIO/ApplicationLauncherJob>
#include <KService>

namespace {
class ApplicationJob : public KJob {
public:
  ApplicationJob(QJsonObject request, QWidget *window) : request(request), window(window) {
    for (const auto &value : request.value("urls").toArray())
      administratorFiles |= QUrl(value.toString()).scheme() == "admin";
    setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window));
    connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
      if (error == QProcess::FailedToStart) finish(process.errorString());
    });
    connect(&process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus exit) {
      const auto result = QJsonDocument::fromJson(process.readAllStandardOutput()).object();
      if (code != 0 || exit != QProcess::NormalExit || !result.value("ok").toBool()) {
        finish(result.value("error").toString("The application could not be started."));
      } else if (administratorFiles) launchAuthenticated(result);
      else finish({});
    });
    QTimer::singleShot(0, this, [this] { start(); });
  }
  void start() override {
    // GIO does not implement KIO's admin: protocol. Resolve the selected app
    // and save any requested default normally, then let KIO handle its URLs.
    if (administratorFiles) request["prepare_only"] = true;
    process.start("python3", {Fusion::root() + "/file_manager/applications.py", "launch"});
    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();
  }
private:
  QProcess process;
  QJsonObject request;
  QPointer<QWidget> window;
  bool administratorFiles = false;
  bool done = false;
  void launchAuthenticated(const QJsonObject &result) {
    const auto desktop = result.value("desktop_file").toString();
    KService::Ptr service;
    if (!desktop.isEmpty()) service = KService::Ptr(new KService(desktop));
    else {
      service = KService::Ptr(new KService(result.value("name").toString(),
          result.value("command").toString(), "application-x-executable"));
      service->setTerminal(request.value("terminal").toBool());
    }
    if (!service->isValid()) { finish("The chosen application is unavailable. Choose Open with… and try again."); return; }
    auto *job = new KIO::ApplicationLauncherJob(service, this);
    QList<QUrl> urls;
    for (const auto &value : request.value("urls").toArray()) urls << QUrl(value.toString());
    job->setUrls(urls);
    job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window));
    connect(job, &KJob::result, this, [this](KJob *result) {
      if (result->error() == KIO::ERR_USER_CANCELED) { done = true; setError(result->error()); emitResult(); }
      else finish(result->error() ? result->errorString() : QString());
    });
    job->start();
  }
  void finish(const QString &error) {
    if (done) return;
    done = true;
    if (!error.isEmpty()) { setError(KIO::ERR_WORKER_DEFINED); setErrorText(error); }
    emitResult();
  }
};
}

Fusion::ApplicationDialog::ApplicationDialog(const KFileItemList &items, QWidget *parent) : QDialog(parent) {
  setObjectName("applicationChooser");
  setWindowTitle("Open with");
  resize(620, 650);
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(24, 22, 24, 20);
  layout->setSpacing(12);
  auto *title = new QLabel("Choose an application");
  title->setObjectName("settingsHeading");
  layout->addWidget(title);
  auto *description = new QLabel(items.size() == 1 ? "Open “" + items.first().name() + "” with:" : QString("Open %1 selected files with:").arg(items.size()));
  description->setWordWrap(true);
  description->setTextFormat(Qt::PlainText);
  layout->addWidget(description);
  search = new QLineEdit;
  search->setObjectName("applicationSearch");
  search->setPlaceholderText("Search installed applications…");
  search->setClearButtonEnabled(true);
  layout->addWidget(search);
  apps = new QListWidget;
  apps->setObjectName("applicationList");
  apps->setIconSize({32, 32});
  apps->setSpacing(3);
  layout->addWidget(apps, 1);
  status = new QLabel("Loading installed applications…");
  status->setObjectName("muted");
  status->setWordWrap(true);
  layout->addWidget(status);
  auto *customLabel = new QLabel("Or choose a program / enter a command");
  layout->addWidget(customLabel);
  auto *customRow = new QHBoxLayout;
  command = new QLineEdit;
  command->setObjectName("applicationCommand");
  command->setPlaceholderText("Program and arguments…");
  customRow->addWidget(command, 1);
  auto *browse = new QPushButton("Browse…");
  customRow->addWidget(browse);
  layout->addLayout(customRow);
  terminal = new QCheckBox("Run custom command in a terminal");
  layout->addWidget(terminal);
  mime = items.isEmpty() ? QString() : items.first().mimetype();
  for (const auto &item : items) if (item.mimetype() != mime) mime.clear();
  remember = new QCheckBox("Use as the default for this file type");
  remember->setObjectName("rememberApplication");
  remember->setEnabled(false);
  if (mime.isEmpty()) remember->setToolTip("Select files of the same type to save a default.");
  else remember->setText("Use as the default for " + QMimeDatabase().mimeTypeForName(mime).comment() + " files");
  layout->addWidget(remember);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Open | QDialogButtonBox::Cancel);
  open = buttons->button(QDialogButtonBox::Open);
  open->setObjectName("openApplication");
  open->setEnabled(false);
  layout->addWidget(buttons);
  connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
  connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
  connect(search, &QLineEdit::textChanged, this, &ApplicationDialog::filter);
  connect(command, &QLineEdit::textChanged, this, [this] { updateChoice(); });
  connect(apps, &QListWidget::currentItemChanged, this, [this] { updateChoice(); });
  connect(apps, &QListWidget::itemDoubleClicked, this, [this] { command->clear(); if (open->isEnabled()) accept(); });
  connect(browse, &QPushButton::clicked, this, [this] {
    const auto path = QFileDialog::getOpenFileName(this, "Choose a program", "/usr/bin");
    if (!path.isEmpty()) { auto quoted = path; quoted.replace('\\', "\\\\").replace('"', "\\\"").replace('`', "\\`").replace('$', "\\$"); command->setText('"' + quoted + '"'); }
  });
  connect(&loader, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) status->setText("Application discovery could not start: " + loader.errorString());
  });
  connect(&loader, &QProcess::finished, this, [this](int code) {
    const auto data = QJsonDocument::fromJson(loader.readAllStandardOutput()).object();
    if (code || !data.contains("apps")) { status->setText(data.value("error").toString("Could not read installed applications.")); return; }
    entries = data.value("apps").toArray();
    revision = data.value("revision").toString();
    remember->setEnabled(!mime.isEmpty() && !revision.isEmpty());
    filter();
  });
  QJsonArray mimes;
  for (const auto &item : items) if (!mimes.contains(item.mimetype())) mimes.append(item.mimetype());
  loader.start("python3", {Fusion::root() + "/file_manager/applications.py", "choices"});
  loader.write(QJsonDocument(QJsonObject{{"mimes", mimes}}).toJson(QJsonDocument::Compact));
  loader.closeWriteChannel();
  search->setFocus();
}
void Fusion::ApplicationDialog::filter() {
  const auto selected = apps->currentItem() ? apps->currentItem()->data(Qt::UserRole).toString() : QString();
  apps->clear();
  for (const auto &value : entries) {
    const auto entry = value.toObject();
    const auto haystack = entry.value("name").toString() + ' ' + entry.value("description").toString() + ' ' + entry.value("executable").toString() + ' ' + entry.value("id").toString();
    if (!haystack.contains(search->text().trimmed(), Qt::CaseInsensitive)) continue;
    auto label = entry.value("name").toString();
    if (entry.value("preferred").toBool()) label += "  ·  Default";
    else if (entry.value("recommended").toBool()) label += "  ·  Recommended";
    auto *item = new QListWidgetItem(Fusion::icon(entry.value("icon").toString(), "application-x-executable"), label, apps);
    item->setData(Qt::UserRole, entry.value("id").toString());
    item->setToolTip(entry.value("description").toString());
    item->setSizeHint({0, 46});
    if (entry.value("id").toString() == selected) apps->setCurrentItem(item);
  }
  if (!apps->currentItem() && apps->count()) apps->setCurrentRow(0);
  status->setText(apps->count() ? QString("%1 installed applications · defaults and recommendations first").arg(apps->count()) : "No matching apps. Choose a program below or try another search.");
  updateChoice();
}
void Fusion::ApplicationDialog::updateChoice() {
  open->setEnabled(!command->text().trimmed().isEmpty() || apps->currentItem());
  terminal->setEnabled(!command->text().trimmed().isEmpty());
}
QJsonObject Fusion::ApplicationDialog::request() const {
  QJsonObject result{{"mime", mime}, {"revision", revision}, {"remember", remember->isEnabled() && remember->isChecked()}};
  if (!command->text().trimmed().isEmpty()) { result["command"] = command->text().trimmed(); result["terminal"] = terminal->isChecked(); }
  else if (apps->currentItem()) result["app"] = apps->currentItem()->data(Qt::UserRole).toString();
  return result;
}
KJob *Fusion::launchApplication(QJsonObject request, QWidget *parent) { return new ApplicationJob(request, parent); }
