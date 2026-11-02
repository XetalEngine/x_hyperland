#include "transfers.h"
#include <KIO/CopyJob>
#include <KIO/DropJob>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegate>
#include <KIO/Paste>
#include <KIO/PasteJob>
#include <KIO/StatJob>
#include <KIO/WidgetsAskUserActionHandler>
#include <KJobWidgets>
#include <KProtocolInfo>
#include <KUrlMimeData>
#include <QApplication>
#include <QClipboard>
#include <QFileInfo>
#include <QDropEvent>
#include <QFutureWatcher>
#include <QMenu>
#include <QMimeData>
#include <QMimeDatabase>
#include <QPointer>
#include <QTimer>
#include <QtConcurrent>

namespace {
// Keep KIO's single transfer, clipboard updates, Undo and JobView progress.
// Only the name-conflict decision changes: keep both with a numbered name.
class NumberedCopies : public KIO::WidgetsAskUserActionHandler {
public:
  explicit NumberedCopies(bool moving) : moving(moving) {}
  void askUserRename(KJob *job, const QString &, const QUrl &src,
                     const QUrl &dest, KIO::RenameDialog_Options options,
                     KIO::filesize_t, KIO::filesize_t, const QDateTime &,
                     const QDateTime &, const QDateTime &,
                     const QDateTime &) override {
    if (moving && Fusion::ordinaryFileUrl(src).matches(Fusion::ordinaryFileUrl(dest), QUrl::StripTrailingSlash)) {
      QTimer::singleShot(0, job, [this, job] {
        emit askUserRenameResult(KIO::Result_Skip, {}, job);
      });
      return;
    }
    QString name = src.adjusted(QUrl::StripTrailingSlash).fileName();
    const bool directory = src.isLocalFile()
                               ? QFileInfo(src.toLocalFile()).isDir()
                               : options.testFlag(KIO::RenameDialog_SourceIsDirectory);
    QString suffix;
    if (!directory) {
      suffix = QMimeDatabase().suffixForFileName(name);
      if (suffix.isEmpty())
        suffix = QFileInfo(name).suffix();
      // A dotfile without an extension keeps its complete name.
      if (!suffix.isEmpty() && name.size() > suffix.size() + 1) {
        suffix.prepend('.');
        name.chop(suffix.size());
      } else
        suffix.clear();
    }
    findName(job, dest.adjusted(QUrl::RemoveFilename), name, suffix, 1);
  }

private:
  bool moving;
  void findName(QPointer<KJob> job, const QUrl &directory,
                const QString &stem, const QString &suffix, quint64 number) {
    if (!job)
      return;
    QUrl candidate = directory;
    candidate.setPath(directory.path() +
                      (directory.path().endsWith('/') ? "" : "/") + stem +
                      "_copy" + QString::number(number) + suffix);
    auto *probe = KIO::stat(candidate, KIO::StatJob::DestinationSide,
                            KIO::StatBasic, KIO::HideProgressInfo);
    connect(job, &KJob::finished, probe, [probe] { probe->kill(); });
    connect(probe, &KJob::result, this,
            [this, job, directory, stem, suffix, number, candidate](KJob *result) {
      if (!job)
        return;
      if (!result->error())
        findName(job, directory, stem, suffix, number + 1);
      else if (result->error() == KIO::ERR_DOES_NOT_EXIST)
        emit askUserRenameResult(KIO::Result_Rename, candidate, job);
      else {
        // Permission/network failures must not be mistaken for a free name.
        if (result->uiDelegate())
          result->uiDelegate()->showErrorMessage();
        emit askUserRenameResult(KIO::Result_Cancel, {}, job);
      }
    });
  }
};
class TransferDelegate : public KIO::JobUiDelegate {
public:
  TransferDelegate(QWidget *window, bool moving, bool administrator = false)
      : JobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window,
                      {new NumberedCopies(moving)}), administrator(administrator) {}
  KIO::ClipboardUpdater *createClipboardUpdater(KIO::Job *job, ClipboardUpdaterMode mode) override {
    return administrator ? nullptr : JobUiDelegate::createClipboardUpdater(job, mode);
  }
  void updateUrlInClipboard(const QUrl &source, const QUrl &destination) override {
    if (!administrator) JobUiDelegate::updateUrlInClipboard(source, destination);
  }
private:
  bool administrator;
};

class TransferJob : public KJob {
public:
  TransferJob(const QList<QUrl> &sources, const QUrl &destination,
              Fusion::TransferOperation operation, QWidget *window, bool deferred = false)
      : sources(sources), destination(destination), operation(operation), window(window) {
    setProperty("fusionTransfer", true);
    setCapabilities(Killable | Suspendable);
    if (!deferred) QTimer::singleShot(0, this, [this] { start(); });
  }
  ~TransferJob() override { cancelled->store(true); }
  void start() override {
    if (started || cancelled->load()) return;
    started = true;
    emit infoMessage(this, "Checking file access…");
    auto *watcher = new QFutureWatcher<Fusion::TransferAccess>(this);
    connect(watcher, &QFutureWatcher<Fusion::TransferAccess>::finished, this, [this, watcher] {
      const auto plan = watcher->result();
      watcher->deleteLater();
      if (!cancelled->load()) begin(plan);
    });
    watcher->setFuture(QtConcurrent::run(Fusion::transferAccess, sources, destination, operation, cancelled));
  }
  void choose(Fusion::TransferOperation choice) { operation = choice; start(); }
  void cancelChoice() { if (!started) finish(KIO::ERR_USER_CANCELED, {}); }

protected:
  bool doKill() override {
    cancelled->store(true);
    finished = true;
    if (active) active->kill(KJob::Quietly);
    return true;
  }
  bool doSuspend() override { return active && active->suspend(); }
  bool doResume() override { return active && active->resume(); }

private:
  QList<QUrl> sources;
  QUrl destination;
  Fusion::TransferOperation operation;
  QPointer<QWidget> window;
  QPointer<KJob> active;
  std::shared_ptr<std::atomic_bool> cancelled = std::make_shared<std::atomic_bool>(false);
  bool started = false;
  bool finished = false;
  QHash<QUrl, QUrl> moved;
  QList<QUrl> originalClipboard;
  bool originalCut = false;

  void rememberMove(const QUrl &from, const QUrl &to) {
    const auto original = Fusion::ordinaryFileUrl(from);
    for (const auto &source : sources)
      if (Fusion::ordinaryFileUrl(source).matches(original, QUrl::StripTrailingSlash))
        moved.insert(source, Fusion::ordinaryFileUrl(to));
  }
  void updateClipboard() {
    if (moved.isEmpty() || originalClipboard != sources) return;
    auto *clipboard = QApplication::clipboard();
    if (!clipboard->mimeData()) return;
    if (KUrlMimeData::urlsFromMimeData(clipboard->mimeData(), KUrlMimeData::PreferLocalUrls) != originalClipboard ||
        KIO::isClipboardDataCut(clipboard->mimeData()) != originalCut) return;
    auto urls = originalClipboard;
    for (auto &url : urls) if (moved.contains(url)) url = moved.value(url);
    auto *mime = new QMimeData;
    mime->setUrls(urls);
    KIO::setClipboardDataCut(mime, originalCut && moved.size() != sources.size());
    clipboard->setMimeData(mime);
  }
  void begin(const Fusion::TransferAccess &plan) {
    if (plan.administrator && !KProtocolInfo::isKnownProtocol("admin")) {
      finish(KIO::ERR_WORKER_DEFINED, "Administrator file operations require the kio-admin package. Install it using Control Panel → Packages, then retry.");
      return;
    }
    const bool moving = operation == Fusion::TransferOperation::Move;
    if (plan.administrator)
      emit infoMessage(this, "Authenticate to access the selected protected files or folder.");
    if (const auto *mime = QApplication::clipboard()->mimeData()) {
      originalClipboard = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
      originalCut = KIO::isClipboardDataCut(mime);
    }
    KIO::CopyJob *copy = moving ? KIO::move(plan.sources, plan.destination)
        : operation == Fusion::TransferOperation::Link ? KIO::link(plan.sources, plan.destination)
        : KIO::copy(plan.sources, plan.destination);
    active = copy;
    copy->setUiDelegate(new TransferDelegate(window, moving, plan.administrator && moving));
    KJobWidgets::setWindow(copy, window);
    KIO::FileUndoManager::self()->recordCopyJob(copy);
    connect(copy, &KJob::infoMessage, this, [this](KJob *, const QString &text) { emit infoMessage(this, text); });
    if (plan.administrator && moving) {
      // KIO sees admin: URLs; the user's clipboard must retain usable file:
      // URLs and the actual numbered destination, without clobbering new data.
      connect(copy, &KIO::CopyJob::copyingDone, this,
              [this](KIO::Job *, const QUrl &from, const QUrl &to) { rememberMove(from, to); });
      connect(copy, &KIO::CopyJob::copyingLinkDone, this,
              [this](KIO::Job *, const QUrl &from, const QString &, const QUrl &to) { rememberMove(from, to); });
    }
    connect(copy, &KJob::result, this, [this, moving, admin = plan.administrator](KJob *result) {
      if (!result->error() && admin && moving) updateClipboard();
      finish(result->error(), result->errorString());
    });
  }
  void finish(int error, const QString &message) {
    if (finished) return;
    finished = true;
    setError(error);
    setErrorText(message);
    emitResult();
  }
};
}

KJob *Fusion::pasteFiles(const QUrl &destination, QWidget *window) {
  const auto *mime = QApplication::clipboard()->mimeData();
  if (!mime) return nullptr;
  const auto urls = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
  if (urls.isEmpty()) return KIO::paste(mime, destination);
  return transferFiles(urls, destination, KIO::isClipboardDataCut(mime) ? TransferOperation::Move : TransferOperation::Copy, window);
}

KJob *Fusion::transferFiles(const QList<QUrl> &sources, const QUrl &destination,
                            TransferOperation operation, QWidget *window) {
  return new TransferJob(sources, destination, operation, window);
}

KJob *Fusion::dropFiles(const QDropEvent *event, const QUrl &destination,
                       QWidget *window, const QPoint &position) {
  const auto *mime = event->mimeData();
  const auto urls = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
  // Ark extraction and bookmarks have their own KIO drop protocols.
  if (urls.isEmpty() || mime->hasFormat("application/x-kde-ark-dndextract-service") ||
      mime->hasFormat("application/x-xbel")) return KIO::drop(event, destination);
  const auto modifiers = event->modifiers();
  if (modifiers & (Qt::ControlModifier | Qt::ShiftModifier)) {
    const auto operation = modifiers.testFlag(Qt::ControlModifier)
        ? (modifiers.testFlag(Qt::ShiftModifier) ? TransferOperation::Link : TransferOperation::Copy)
        : TransferOperation::Move;
    const auto action = operation == TransferOperation::Move ? Qt::MoveAction
        : operation == TransferOperation::Link ? Qt::LinkAction : Qt::CopyAction;
    if (!event->possibleActions().testFlag(action)) return KIO::drop(event, destination);
    return transferFiles(urls, destination, operation, window);
  }
  auto *job = new TransferJob(urls, destination, TransferOperation::Copy, window, true);
  auto *menu = new QMenu(window);
  menu->setAttribute(Qt::WA_DeleteOnClose);
  const auto possible = event->possibleActions();
  for (const auto &choice : {std::make_tuple("Move here", "edit-cut", Qt::MoveAction, TransferOperation::Move),
                             std::make_tuple("Copy here", "edit-copy", Qt::CopyAction, TransferOperation::Copy),
                             std::make_tuple("Link here", "emblem-symbolic-link", Qt::LinkAction, TransferOperation::Link)}) {
    if (!possible.testFlag(std::get<2>(choice))) continue;
    auto *action = menu->addAction(QIcon::fromTheme(std::get<1>(choice)), std::get<0>(choice));
    QObject::connect(action, &QAction::triggered, job, [job, operation = std::get<3>(choice)] { job->choose(operation); });
  }
  menu->addSeparator();
  menu->addAction("Cancel");
  QObject::connect(menu, &QMenu::aboutToHide, job, [job] { QTimer::singleShot(0, job, [job] { job->cancelChoice(); }); });
  QObject::connect(menu, &QObject::destroyed, job, [job] { job->cancelChoice(); });
  QTimer::singleShot(0, menu, [menu, position] { menu->popup(position); });
  return job;
}
