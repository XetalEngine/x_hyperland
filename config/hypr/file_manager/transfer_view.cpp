#include "transfer_view.h"
#include <KIO/JobTracker>
#include <KJobTrackerInterface>
#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusMessage>
#include <QDBusObjectPath>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QTimer>
#include <limits>
#include <utility>

namespace {
constexpr auto server = "org.kde.JobViewServer";
QString unitName(KJob::Unit unit) {
  return unit == KJob::Bytes ? "Bytes" : unit == KJob::Files ? "Files"
      : unit == KJob::Directories ? "Directories" : QString();
}
void send(const QString &owner, const QString &path, const QString &method, const QVariantList &args) {
  auto message = QDBusMessage::createMethodCall(owner, path, "org.kde.JobViewV3", method);
  message.setArguments(args);
  QDBusConnection::sessionBus().call(message, QDBus::NoBlock);
}
}

Fusion::TransferView::TransferView(KJob *job, const QVariantMap &initial)
    : QObject(QCoreApplication::instance()), job(job), values(initial) {
  connect(job, &KJob::description, this, [this](KJob *, const QString &title,
      const QPair<QString, QString> &first, const QPair<QString, QString> &second) {
    update({{"title", title}, {"descriptionLabel1", first.first}, {"descriptionValue1", first.second},
            {"descriptionLabel2", second.first}, {"descriptionValue2", second.second}});
  });
  connect(job, &KJob::infoMessage, this, [this](KJob *, const QString &text) { update({{"infoMessage", text}}); });
  connect(job, &KJob::percentChanged, this, [this](KJob *, unsigned long percent) { update({{"percent", uint(percent)}}); });
  connect(job, &KJob::totalAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong amount) {
    if (!unitName(unit).isEmpty()) update({{"total" + unitName(unit), QVariant::fromValue(amount)}});
  });
  connect(job, &KJob::processedAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong amount) {
    if (!unitName(unit).isEmpty()) update({{"processed" + unitName(unit), QVariant::fromValue(amount)}});
  });
  connect(job, &KJob::speed, this, [this](KJob *, unsigned long speed) { update({{"speed", QVariant::fromValue(qulonglong(speed))}}); });
  connect(job, &KJob::suspended, this, [this] { update({{"suspended", true}}); });
  connect(job, &KJob::resumed, this, [this] { update({{"suspended", false}}); });
  connect(job, &KJob::finished, this, [this](KJob *result) { finish(result->error(), result->errorString()); });
  connect(job, &QObject::destroyed, this, [this] { if (!finished) finish(KJob::KilledJobError, "The operation ended."); });
  owner = QDBusConnection::sessionBus().interface()->serviceOwner(server).value();
  auto request = QDBusMessage::createMethodCall(owner.isEmpty() ? server : owner, "/JobViewServer", "org.kde.JobViewServerV2", "requestView");
  request.setArguments({"xetal-files", int(job->capabilities()), initial});
  auto *watcher = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(request, 2500), this);
  connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher] {
    const QDBusPendingReply<QDBusObjectPath> result = *watcher;
    watcher->deleteLater();
    ready = true;
    unavailable = result.isError() || result.value().path() == "/";
    if (!unavailable) {
      path = result.value().path();
      // Bind replies and controls to this service instance, not a replacement.
      if (owner.isEmpty()) owner = QDBusConnection::sessionBus().interface()->serviceOwner(server).value();
      auto bus = QDBusConnection::sessionBus();
      bus.connect(owner, path, "org.kde.JobViewV3", "cancelRequested", this, SLOT(cancel()));
      bus.connect(owner, path, "org.kde.JobViewV3", "suspendRequested", this, SLOT(suspend()));
      bus.connect(owner, path, "org.kde.JobViewV3", "resumeRequested", this, SLOT(resume()));
    } else if (this->job && !finished) {
      // Standalone Files outside a Fusion session retains ordinary KIO progress.
      KIO::getJobTracker()->registerJob(this->job);
    }
    if (finished) terminate();
    else { flush(); sendQuestion(); }
  });
}

void Fusion::TransferView::update(const QVariantMap &data) {
  for (auto it = data.begin(); it != data.end(); ++it) values[it.key()] = it.value();
  // Coalesce KIO's amount/percent signals; large copies must not flood D-Bus.
  if (!property("flushQueued").toBool()) {
    setProperty("flushQueued", true);
    QTimer::singleShot(50, this, [this] { setProperty("flushQueued", false); flush(); });
  }
}

void Fusion::TransferView::flush() {
  if (ready && !unavailable && !finished && !values.isEmpty()) {
    send(owner, path, "update", {values}); values.clear();
  }
}

void Fusion::TransferView::ask(const QVariantMap &data, Answer callback, std::function<void()> local) {
  question = data; answer = std::move(callback); fallback = std::move(local);
  sendQuestion();
}

void Fusion::TransferView::sendQuestion() {
  if (!ready || finished || question.isEmpty()) return;
  const auto data = std::exchange(question, {});
  auto callback = std::exchange(answer, {});
  auto local = std::exchange(fallback, {});
  if (unavailable) { local(); return; }
  auto request = QDBusMessage::createMethodCall(owner, path, "org.xetal.FileTransfer1", "ask");
  request.setArguments({data});
  // A person may leave a question open. Never turn a short IPC timeout into a
  // destructive decision or repeat a question in a different window.
  auto *watcher = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(request, std::numeric_limits<int>::max()), this);
  connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher, callback, local] {
    const QDBusPendingReply<QVariantMap> result = *watcher;
    watcher->deleteLater();
    if (finished || !job) return;
    if (result.isError() && (result.error().type() == QDBusError::UnknownMethod ||
                            result.error().type() == QDBusError::UnknownInterface)) local();
    else callback(result.isError() ? QVariantMap{{"choice", "cancel"}} : result.value());
  });
}

void Fusion::TransferView::finish(int code, const QString &text) {
  if (finished) return;
  flush(); finished = true; error = code; errorText = text;
  if (ready) terminate();
}
void Fusion::TransferView::terminate() {
  if (!unavailable) send(owner, path, "terminate", {uint(error ? (error == KJob::KilledJobError ? 1 : 2) : 0), errorText, QVariantMap{}});
  deleteLater();
}
void Fusion::TransferView::cancel() { if (job && !finished) job->kill(KJob::EmitResult); }
void Fusion::TransferView::suspend() { if (job && !finished) { job->suspend(); update({{"suspended", job->isSuspended()}}); } }
void Fusion::TransferView::resume() { if (job && !finished) { job->resume(); update({{"suspended", job->isSuspended()}}); } }
