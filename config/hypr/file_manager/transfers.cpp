#include "transfers.h"
#include "transfer_view.h"
#include "native_transfer.h"
#include "transfer_issues.h"
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
#include <KProtocolManager>
#include <KUrlMimeData>
#include <QApplication>
#include <QClipboard>
#include <QCheckBox>
#include <QCommandLinkButton>
#include <QFileInfo>
#include <QDir>
#include <QDropEvent>
#include <QFutureWatcher>
#include <QMessageBox>
#include <QMimeData>
#include <QMimeDatabase>
#include <QPointer>
#include <QPushButton>
#include <QTimer>
#include <QVBoxLayout>
#include <QLabel>
#include <QJsonArray>
#include <QtConcurrent>
#include <algorithm>
#include <optional>

namespace {
// Share conflict choices between native local transfers and remote KIO jobs.
// Same-folder duplicates get numbered names. Other conflicts require a choice,
// shared across both files and folders for this transfer only.
class TransferConflicts : public KIO::WidgetsAskUserActionHandler {
public:
  explicit TransferConflicts(QWidget *window, bool moving, Fusion::TransferView *view)
      : window(window), moving(moving), view(view) {}
  void askUserRename(KJob *job, const QString &, const QUrl &src,
                     const QUrl &dest, KIO::RenameDialog_Options options,
                     KIO::filesize_t, KIO::filesize_t, const QDateTime &,
                     const QDateTime &, const QDateTime &,
                     const QDateTime &) override {
    const auto source = Fusion::ordinaryFileUrl(src).adjusted(QUrl::NormalizePathSegments);
    const auto destination = Fusion::ordinaryFileUrl(dest).adjusted(QUrl::NormalizePathSegments);
    const auto sourceParent = source.isLocalFile() ? QFileInfo(source.toLocalFile()).absoluteDir().canonicalPath() : QString();
    const bool same = source.matches(destination, QUrl::StripTrailingSlash) ||
        (!sourceParent.isEmpty() && source.fileName() == destination.fileName() && destination.isLocalFile() &&
         sourceParent ==
         QFileInfo(destination.toLocalFile()).absoluteDir().canonicalPath());
    if (!same) {
      askConflict(job, src, dest, options);
      return;
    }
    if (moving) {
      reply(job, KIO::Result_Skip);
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
  QPointer<QWidget> window;
  bool moving;
  QPointer<Fusion::TransferView> view;
  bool individual = false;
  KIO::RenameDialog_Result all = KIO::Result_Cancel;
  void reply(KJob *job, KIO::RenameDialog_Result result) {
    QTimer::singleShot(0, job, [this, job, result] { emit askUserRenameResult(result, {}, job); });
  }
  void watchQuestion(KJob *job, QDialog *question) {
    auto answered = std::make_shared<bool>(false);
    connect(question, &QDialog::finished, this, [answered] { *answered = true; });
    connect(question, &QObject::destroyed, this, [this, pending = QPointer<KJob>(job), answered] {
      if (pending && !*answered) reply(pending, KIO::Result_Cancel);
    });
    connect(job, &KJob::finished, question, &QObject::deleteLater);
  }
  void askConflict(KJob *job, const QUrl &src, const QUrl &dest, KIO::RenameDialog_Options options) {
    const bool canOverwrite = options.testFlag(KIO::RenameDialog_Overwrite) &&
        !options.testFlag(KIO::RenameDialog_OverwriteItself);
    // KIO's direct move/rename path omits SourceIsDirectory. It only allows
    // overwriting a destination directory when the source is also a directory.
    const bool directory = options.testFlag(KIO::RenameDialog_DestIsDirectory) && canOverwrite;
    // Matching directories are containers, not file conflicts. Always enter
    // them so "Skip these files" still transfers new descendants at any depth.
    // KIO asks again for each conflicting file; this does not authorize replacing it.
    if (directory && canOverwrite) {
      reply(job, KIO::Result_Overwrite);
      return;
    }
    if (all == KIO::Result_Skip || (all == KIO::Result_Overwrite && canOverwrite)) {
      reply(job, all);
      return;
    }
    if (!individual && canOverwrite) {
      askSummary(job, src, dest, options);
      return;
    }
    const auto pending = QPointer<KJob>(job);
    auto local = [this, pending, src, dest, canOverwrite] {
      if (pending) showIndividual(pending, src, dest, canOverwrite);
    };
    if (!view) { local(); return; }
    view->ask({{"kind", "file"}, {"source", Fusion::ordinaryFileUrl(src).toDisplayString()},
               {"destination", Fusion::ordinaryFileUrl(dest).toDisplayString()}, {"replace_allowed", canOverwrite}},
        [this, pending, canOverwrite](const QVariantMap &answer) {
          if (!pending) return;
          const auto choice = answer.value("choice").toString();
          const auto result = choice == "replace" && canOverwrite ? KIO::Result_Overwrite
              : choice == "skip" ? KIO::Result_Skip : KIO::Result_Cancel;
          if (answer.value("all").toBool() && result != KIO::Result_Cancel) all = result;
          reply(pending, result);
        }, local);
  }
  void showIndividual(KJob *job, const QUrl &src, const QUrl &dest, bool canOverwrite) {
    auto *question = new QMessageBox(QMessageBox::Warning, "Replace or skip this file",
        QString("\u201c%1\u201d already exists in the destination. %2")
            .arg(dest.adjusted(QUrl::StripTrailingSlash).fileName(),
                 canOverwrite ? "Replace it?" : "This file and folder conflict cannot be overwritten. Skip this item?"),
        QMessageBox::No | QMessageBox::Cancel, window);
    question->setTextFormat(Qt::PlainText);
    question->setObjectName("transferConflictQuestion");
    question->button(QMessageBox::No)->setText("Skip this file");
    if (canOverwrite) {
      question->addButton(QMessageBox::Yes)->setText("Replace this file");
      question->setInformativeText("Replacing overwrites the destination file. Skipping keeps it and continues with the remaining files.");
    }
    question->setDetailedText("From: " + Fusion::ordinaryFileUrl(src).toDisplayString() +
                             "\nTo: " + Fusion::ordinaryFileUrl(dest).toDisplayString());
    auto *applyAll = new QCheckBox("Do this for all conflicts in this transfer, including subfolders", question);
    applyAll->setObjectName("applyToAllConflicts");question->setCheckBox(applyAll);
    question->setDefaultButton(QMessageBox::Cancel);question->setEscapeButton(QMessageBox::Cancel);
    question->setAttribute(Qt::WA_DeleteOnClose);
    watchQuestion(job, question);
    connect(question, &QDialog::finished, this, [this, pending = QPointer<KJob>(job), applyAll, canOverwrite](int answer) {
      if (!pending) return;
      const auto result = answer == QMessageBox::Yes && canOverwrite ? KIO::Result_Overwrite
          : answer == QMessageBox::No ? KIO::Result_Skip : KIO::Result_Cancel;
      if (applyAll->isChecked() && result != KIO::Result_Cancel) all = result;
      reply(pending, result);
    });
    question->open();
  }
  void askSummary(KJob *job, const QUrl &src, const QUrl &dest, KIO::RenameDialog_Options options) {
    const auto pending = QPointer<KJob>(job);
    auto local = [this, pending, src, dest, options] { if (pending) showSummary(pending, src, dest, options); };
    if (!view) { local(); return; }
    view->ask({{"kind", "conflicts"}, {"source", Fusion::ordinaryFileUrl(src).toDisplayString()},
               {"destination", Fusion::ordinaryFileUrl(dest).toDisplayString()}, {"replace_allowed", true}},
        [this, pending, src, dest, options](const QVariantMap &answer) {
          if (!pending) return;
          const auto choice = answer.value("choice").toString();
          if (choice == "individual") { individual = true; askConflict(pending, src, dest, options); }
          else if (choice == "replace" || choice == "skip") {
            all = choice == "replace" ? KIO::Result_Overwrite : KIO::Result_Skip;
            reply(pending, all);
          } else reply(pending, KIO::Result_Cancel);
        }, local);
  }
  void showSummary(KJob *job, const QUrl &src, const QUrl &dest, KIO::RenameDialog_Options options) {
    auto *dialog=new QDialog(window);dialog->setWindowTitle("Replace or skip files");
    dialog->setObjectName("transferConflictSummary");dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->setMinimumWidth(480);
    auto *layout=new QVBoxLayout(dialog);layout->setContentsMargins(24,20,24,20);layout->setSpacing(12);
    auto *heading=new QLabel("The destination has files with the same names.");
    auto font=heading->font();font.setPointSize(font.pointSize()+2);font.setBold(true);heading->setFont(font);
    heading->setWordWrap(true);layout->addWidget(heading);
    auto *context=new QLabel((moving?"Moving to: ":"Copying to: ")+
        Fusion::ordinaryFileUrl(dest.adjusted(QUrl::RemoveFilename)).toDisplayString(QUrl::PreferLocalFile));
    context->setTextFormat(Qt::PlainText);context->setWordWrap(true);layout->addWidget(context);
    const auto add=[&](const QString &name,const QString &title,const QString &description,int result) {
      auto *button=new QCommandLinkButton(title,description,dialog);button->setObjectName(name);
      button->setAutoDefault(false);layout->addWidget(button);
      connect(button,&QAbstractButton::clicked,dialog,[dialog,result]{dialog->done(result);});
    };
    add("replaceConflicts","Replace the files in the destination",
        "Overwrite matching files throughout this transfer, including subfolders.",1);
    add("skipConflicts","Skip these files",
        "Keep existing files. Still transfer all new files, including those in matching folders.",2);
    add("individualConflicts","Let me decide for each file",
        "Choose which matching files to replace and which to skip.",3);
    auto *cancel=new QPushButton("Cancel",dialog);cancel->setDefault(true);
    layout->addWidget(cancel,0,Qt::AlignRight);connect(cancel,&QPushButton::clicked,dialog,&QDialog::reject);
    watchQuestion(job, dialog);
    connect(dialog,&QDialog::finished,this,[this,pending=QPointer<KJob>(job),src,dest,options](int answer) {
      if (!pending) return;
      if (answer==3) { individual=true;askConflict(pending,src,dest,options); }
      else if (answer==1 || answer==2) {
        all=answer==1?KIO::Result_Overwrite:KIO::Result_Skip;
        reply(pending,all);
      } else reply(pending,KIO::Result_Cancel);
    });
    dialog->open();
  }
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
  TransferDelegate(QWidget *window, bool moving, Fusion::TransferView *view, bool administrator = false)
      : JobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window,
                      {new TransferConflicts(window, moving, view)}), administrator(administrator) {}
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
              Fusion::TransferOperation operation, QWidget *window, bool deferred = false,
              std::function<void(const QUrl &)> destinationChanged = {})
      : sources(sources), destination(destination), operation(operation), window(window), destinationChanged(std::move(destinationChanged)) {
    setProperty("fusionTransfer", true);
    setCapabilities(Killable | Suspendable);
    view = new Fusion::TransferView(this, {{"title", operation == Fusion::TransferOperation::Move ? "Moving files"
        : operation == Fusion::TransferOperation::Link ? "Linking files" : "Copying files"},
        {"descriptionValue1", sources.isEmpty() ? QString() : Fusion::ordinaryFileUrl(sources.first()).adjusted(QUrl::RemoveFilename).toDisplayString()},
        {"descriptionValue2", Fusion::ordinaryFileUrl(destination).toDisplayString()}});
    if (!deferred) QTimer::singleShot(0, this, [this] { start(); });
  }
  ~TransferJob() override { cancelled->store(true); }
  void start() override {
    if (started || cancelled->load()) return;
    started = true;
    const auto local = [](const QUrl &url) { return Fusion::ordinaryFileUrl(url).isLocalFile(); };
    if (!undoJournal.isEmpty() || (operation != Fusion::TransferOperation::Link && local(destination) &&
        std::all_of(sources.begin(), sources.end(), local))) {
      if (isSuspended()) pendingNative = true;
      else beginNative();
      return;
    }
    emit infoMessage(this, "Checking file access…");
    auto *watcher = new QFutureWatcher<Fusion::TransferAccess>(this);
    connect(watcher, &QFutureWatcher<Fusion::TransferAccess>::finished, this, [this, watcher] {
      const auto plan = watcher->result();
      watcher->deleteLater();
      if (!cancelled->load()) {
        if (isSuspended()) pausedPlan = plan;
        else begin(plan);
      }
    });
    watcher->setFuture(QtConcurrent::run(Fusion::transferAccess, sources, destination, operation, cancelled));
  }
  void choose(Fusion::TransferOperation choice) { operation = choice; start(); }
  void undo(const QString &journal) { undoJournal = journal; start(); }
  void cancelChoice() { if (!started) finish(KIO::ERR_USER_CANCELED, {}); }
  void askDuplicate(std::function<void()> fallback) {
    view->ask({{"kind", "duplicate"}, {"destination", Fusion::ordinaryFileUrl(destination).toDisplayString()}},
        [this](const QVariantMap &answer) {
          if (answer.value("choice").toString() == "copy") choose(Fusion::TransferOperation::Copy);
          else cancelChoice();
        }, std::move(fallback));
  }

protected:
  bool doKill() override {
    cancelled->store(true);
    if (auto *native = qobject_cast<Fusion::NativeTransfer *>(active.data())) {
      native->kill(KJob::EmitResult);
      return false;
    }
    finished = true;
    if (active) active->kill(KJob::Quietly);
    return true;
  }
  bool doSuspend() override { return active ? active->suspend() : !finished; }
  bool doResume() override {
    if (active) return active->resume();
    if (pendingNative) {
      pendingNative = false;
      QTimer::singleShot(0, this, [this] { if (!finished && !cancelled->load()) beginNative(); });
    }
    if (pausedPlan) {
      const auto plan = *pausedPlan; pausedPlan.reset();
      QTimer::singleShot(0, this, [this, plan] {
        if (finished || cancelled->load()) return;
        if (isSuspended()) pausedPlan = plan;
        else begin(plan);
      });
    }
    return !finished;
  }

private:
  QList<QUrl> sources;
  QUrl destination;
  Fusion::TransferOperation operation;
  QPointer<QWidget> window;
  std::function<void(const QUrl &)> destinationChanged;
  QPointer<KJob> active;
  QPointer<Fusion::TransferView> view;
  std::optional<Fusion::TransferAccess> pausedPlan;
  std::shared_ptr<std::atomic_bool> cancelled = std::make_shared<std::atomic_bool>(false);
  bool started = false;
  bool finished = false;
  QHash<QUrl, QUrl> moved;
  QList<QUrl> originalClipboard;
  bool originalCut = false;
  bool pendingNative = false;
  QString undoJournal;

  void beginNative() {
    if (isSuspended()) { pendingNative = true; return; }
    const bool moving = operation == Fusion::TransferOperation::Move;
    QJsonArray paths;
    for (const auto &source : sources) paths.append(Fusion::ordinaryFileUrl(source).toLocalFile());
    auto *copy = new Fusion::NativeTransfer({{"sources", paths},
        {"destination", Fusion::ordinaryFileUrl(destination).toLocalFile()},
        {"operation", undoJournal.isEmpty() ? (moving ? "move" : "copy") : "undo"}, {"undoJournal", undoJournal}});
    active = copy;
    auto *issues = new Fusion::TransferIssues(copy, window, view);
    connect(view, &Fusion::TransferView::reviewRequested, issues, &Fusion::TransferIssues::reveal);
    if (const auto *mime = QApplication::clipboard()->mimeData()) {
      originalClipboard = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
      originalCut = KIO::isClipboardDataCut(mime);
    }
    view->update({{"totalsKnown", false}, {"phase", "Copying"},
                  {"title", undoJournal.isEmpty() ? (moving ? "Moving files" : "Copying files") : "Undoing transfer"}});
    auto *questions = new TransferConflicts(window, moving, view);
    questions->setParent(copy);
    connect(copy, &Fusion::NativeTransfer::question, questions,
        [questions, copy](const QUrl &from, const QUrl &to, bool replace) {
          questions->askUserRename(copy, {}, from, to, replace ? KIO::RenameDialog_Overwrite : KIO::RenameDialog_Options{}, 0, 0, {}, {}, {}, {});
        });
    connect(questions, &KIO::WidgetsAskUserActionHandler::askUserRenameResult, copy,
        [copy](KIO::RenameDialog_Result result, const QUrl &, KJob *) {
          copy->answer(result == KIO::Result_Overwrite ? "replace" : result == KIO::Result_Skip ? "skip" : "cancel");
        });
    connect(copy, &Fusion::NativeTransfer::progress, view, &Fusion::TransferView::update);
    connect(copy, &KJob::infoMessage, this, [this](KJob *, const QString &text) { emit infoMessage(this, text); });
    connect(copy, &KJob::totalAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong amount) { setTotalAmount(unit, amount); });
    connect(copy, &KJob::processedAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong amount) { setProcessedAmount(unit, amount); });
    connect(copy, &KJob::percentChanged, this, [this](KJob *, unsigned long value) { setPercent(value); });
    connect(copy, &KJob::speed, this, [this](KJob *, unsigned long value) { emitSpeed(value); });
    connect(copy, &Fusion::NativeTransfer::moved, this, [this](const QUrl &from, const QUrl &to) { rememberMove(from, to); });
    connect(copy, &Fusion::NativeTransfer::destinationReady, this, [this](const QUrl &to) {
      if (destinationChanged) destinationChanged(to);
    });
    connect(copy, &KJob::result, this, [this, copy, moving](KJob *result) {
      updateClipboard();
      if (!result->error()) {
        if (undoJournal.isEmpty()) Fusion::TransferHistory::self()->record(copy->journal(), moving);
        else Fusion::TransferHistory::self()->consumed(undoJournal);
      }
      if (destinationChanged) destinationChanged(Fusion::ordinaryFileUrl(destination));
      finish(result->error(), result->errorString());
    });
    copy->start();
  }

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
    KIO::CopyJob *copy = moving ? KIO::move(plan.sources, plan.destination, KIO::HideProgressInfo)
        : operation == Fusion::TransferOperation::Link ? KIO::link(plan.sources, plan.destination, KIO::HideProgressInfo)
        : KIO::copy(plan.sources, plan.destination, KIO::HideProgressInfo);
    active = copy;
    if (destinationChanged) {
      auto report = [this](const QUrl &url) { destinationChanged(Fusion::ordinaryFileUrl(url)); };
      connect(copy, &KIO::CopyJob::creatingDir, this, [report](KIO::Job *, const QUrl &to) { report(to); });
      connect(copy, &KIO::CopyJob::renamed, this, [report](KIO::Job *, const QUrl &, const QUrl &to) { report(to); });
      connect(copy, &KIO::CopyJob::copyingDone, this, [report](KIO::Job *, const QUrl &, const QUrl &to) { report(to); });
      connect(copy, &KIO::CopyJob::copyingLinkDone, this,
              [report](KIO::Job *, const QUrl &, const QString &, const QUrl &to) { report(to); });
    }
    copy->setUiDelegate(new TransferDelegate(window, moving, view, plan.administrator && moving));
    KJobWidgets::setWindow(copy, window);
    KIO::FileUndoManager::self()->recordCopyJob(copy);
    connect(copy, &KJob::infoMessage, this, [this](KJob *, const QString &text) { emit infoMessage(this, text); });
    connect(copy, &KJob::description, this, [this](KJob *, const QString &title,
        const QPair<QString, QString> &first, const QPair<QString, QString> &second) { emit description(this, title, first, second); });
    connect(copy, &KJob::totalAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong value) { setTotalAmount(unit, value); });
    connect(copy, &KJob::processedAmountChanged, this, [this](KJob *, KJob::Unit unit, qulonglong value) { setProcessedAmount(unit, value); });
    connect(copy, &KJob::percentChanged, this, [this](KJob *, unsigned long value) { setPercent(value); });
    connect(copy, &KJob::speed, this, [this](KJob *, unsigned long value) { emitSpeed(value); });
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

QList<QUrl> Fusion::clipboardFiles(const QMimeData *mime) {
  if (!mime) return {};
  if (!mime->hasUrls() && !mime->hasFormat("application/x-kde4-urilist") &&
      !mime->hasFormat("x-special/gnome-copied-files")) return {};
  auto urls = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
  if (urls.isEmpty() && mime->hasFormat("x-special/gnome-copied-files")) {
    auto lines = QString::fromUtf8(mime->data("x-special/gnome-copied-files")).split('\n', Qt::SkipEmptyParts);
    if (lines.isEmpty() || (lines.first().trimmed() != "copy" && lines.first().trimmed() != "cut")) return {};
    lines.removeFirst();
    for (const auto &line : lines) urls << QUrl(line.trimmed(), QUrl::StrictMode);
  }
  // Text, browser links and virtual locations aren't a file clipboard. Remote
  // file-manager URLs remain supported; nothing is stat'ed on the UI thread.
  const QStringList protocols{"file", "admin", "trash", "nfs", "smb", "sftp", "fish", "ftp", "ftps", "webdav", "webdavs", "dav", "davs", "mtp", "afc"};
  for (const auto &url : urls)
    if (!url.isValid() || !protocols.contains(url.scheme()) || url.path().contains(QChar::Null) ||
        (url.scheme() == "trash" && (url.path().isEmpty() || url.path() == "/")) ||
        (url.isLocalFile() && !QDir::isAbsolutePath(url.toLocalFile()))) return {};
  return urls;
}
bool Fusion::canPasteFiles(const QMimeData *mime) { return !clipboardFiles(mime).isEmpty(); }

KJob *Fusion::pasteFiles(const QUrl &destination, QWidget *window) {
  const auto *mime = QApplication::clipboard()->mimeData();
  if (!mime) return nullptr;
  const auto urls = clipboardFiles(mime);
  if (urls.isEmpty() || !fileDropDestination(destination)) return nullptr;
  const bool cut = KIO::isClipboardDataCut(mime) || mime->data("x-special/gnome-copied-files").split('\n').value(0).trimmed() == "cut";
  return transferFiles(urls, destination, cut ? TransferOperation::Move : TransferOperation::Copy, window);
}

KJob *Fusion::transferFiles(const QList<QUrl> &sources, const QUrl &destination,
                            TransferOperation operation, QWidget *window,
                            std::function<void(const QUrl &)> destinationChanged) {
  return new TransferJob(sources, destination, operation, window, false, std::move(destinationChanged));
}

KJob *Fusion::undoTransfer(QWidget *window) {
  const auto journal = TransferHistory::self()->pending();
  if (journal.isEmpty()) {
    KIO::FileUndoManager::self()->uiInterface()->setParentWidget(window);
    KIO::FileUndoManager::self()->undo();
    return nullptr;
  }
  auto *job = new TransferJob({}, {}, TransferOperation::Move, window, true);
  job->undo(journal);
  return job;
}

namespace {
bool arkDrop(const QMimeData *mime) {
  return mime && mime->hasFormat("application/x-kde-ark-dndextract-service") &&
      mime->hasFormat("application/x-kde-ark-dndextract-path");
}
bool sameDirectory(const QUrl &source, const QUrl &destination) {
  const auto parent = Fusion::ordinaryFileUrl(source).adjusted(QUrl::StripTrailingSlash).adjusted(QUrl::RemoveFilename | QUrl::NormalizePathSegments);
  const auto target = Fusion::ordinaryFileUrl(destination).adjusted(QUrl::NormalizePathSegments);
  if (parent.matches(target, QUrl::StripTrailingSlash)) return true;
  if (!parent.isLocalFile() || !target.isLocalFile()) return false;
  const auto canonical = QFileInfo(parent.toLocalFile()).canonicalFilePath();
  return !canonical.isEmpty() && canonical == QFileInfo(target.toLocalFile()).canonicalFilePath();
}
}

bool Fusion::acceptsFileDrop(const QMimeData *mime) {
  return mime && (mime->hasUrls() || arkDrop(mime));
}

Qt::DropAction Fusion::fileDropOperation(const QMimeData *mime, Qt::KeyboardModifiers modifiers,
                                        Qt::DropActions possible) {
  if (!acceptsFileDrop(mime)) return Qt::IgnoreAction;
  const bool control = modifiers.testFlag(Qt::ControlModifier);
  const bool shift = modifiers.testFlag(Qt::ShiftModifier);
  if (control && shift && !arkDrop(mime))
    return possible.testFlag(Qt::LinkAction) || possible.testFlag(Qt::CopyAction)
        ? Qt::LinkAction : Qt::IgnoreAction;
  const auto requested = arkDrop(mime) ? Qt::CopyAction
      : control ? Qt::CopyAction : Qt::MoveAction;
  if (arkDrop(mime) && shift) return Qt::IgnoreAction;
  if (possible.testFlag(requested)) return requested;
  // Archives and read-only sources can offer only copying. Never turn a
  // requested Ctrl-copy into a move when a source does not support copying.
  return !shift && requested == Qt::MoveAction && possible.testFlag(Qt::CopyAction)
      ? Qt::CopyAction : Qt::IgnoreAction;
}

Qt::DropAction Fusion::fileDropAction(const QMimeData *mime, Qt::KeyboardModifiers modifiers,
                                     Qt::DropActions possible) {
  const auto operation = fileDropOperation(mime, modifiers, possible);
  // Wayland has no wire-level Link action. Exchange URLs as Copy (the source
  // must survive), and perform the shortcut operation in the destination.
  return operation == Qt::LinkAction && !possible.testFlag(Qt::LinkAction)
      ? Qt::CopyAction : operation;
}

bool Fusion::fileDropDestination(const QUrl &destination) {
  if (!destination.isValid() || destination.isEmpty()) return false;
  if (destination.isLocalFile()) return QFileInfo(destination.toLocalFile()).isDir();
  const auto scheme = destination.scheme();
  return scheme != "computer" && scheme != "trash" && scheme != "network" &&
      KProtocolManager::supportsWriting(destination);
}

KJob *Fusion::dropFiles(const QDropEvent *event, const QUrl &destination,
                       QWidget *window, const QPoint &) {
  if (!fileDropDestination(destination)) return nullptr;
  const auto *mime = event->mimeData();
  const auto action = fileDropOperation(mime, event->modifiers(), event->possibleActions());
  if (action == Qt::IgnoreAction) return nullptr;
  const auto urls = KUrlMimeData::urlsFromMimeData(mime, KUrlMimeData::PreferLocalUrls);
  // Ark advertises an extraction service, not file URLs. Keep its own
  // asynchronous extraction (including passwords and conflict handling).
  if (arkDrop(mime) || urls.isEmpty() ||
      mime->hasFormat("application/x-xbel")) return KIO::drop(event, destination);
  if (action == Qt::LinkAction)
    return transferFiles(urls, destination, TransferOperation::Link, window);
  const bool duplicate = std::any_of(urls.begin(), urls.end(), [&](const QUrl &url) { return sameDirectory(url, destination); });
  if (!duplicate)
    return transferFiles(urls, destination, action == Qt::MoveAction ? TransferOperation::Move : TransferOperation::Copy, window);
  auto *job = new TransferJob(urls, destination, TransferOperation::Copy, window, true);
  const auto owner = QPointer<QWidget>(window);
  job->askDuplicate([job, owner, urls] {
  auto *question = new QMessageBox(QMessageBox::Question, "Already in this folder",
      urls.size() == 1 ? "This file or folder already exists here. Copy it anyway?"
                       : "Some of these files or folders already exist here. Copy the selection anyway?",
      QMessageBox::Yes | QMessageBox::Cancel, owner);
  question->setObjectName("duplicateDropQuestion");
  question->setInformativeText("Copies get names ending in _copy1, _copy2, and so on. Existing files are kept.");
  question->setDefaultButton(QMessageBox::Cancel);question->setAttribute(Qt::WA_DeleteOnClose);
  QObject::connect(question, &QDialog::finished, job, [job](int result) {
    if (result == QMessageBox::Yes) job->choose(TransferOperation::Copy);
    else job->cancelChoice();
  });
  QObject::connect(question, &QObject::destroyed, job, [job] { job->cancelChoice(); });
  QTimer::singleShot(0, question, [question] { question->open(); });
  });
  return job;
}
