#include "transfers.h"
#include <KIO/CopyJob>
#include <KIO/JobUiDelegate>
#include <KIO/PasteJob>
#include <KIO/StatJob>
#include <KIO/WidgetsAskUserActionHandler>
#include <QApplication>
#include <QClipboard>
#include <QFileInfo>
#include <QMimeDatabase>
#include <QPointer>
#include <QTimer>

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
    if (moving && src.matches(dest, QUrl::StripTrailingSlash)) {
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
  TransferDelegate(QWidget *window, bool moving)
      : JobUiDelegate(KJobUiDelegate::AutoHandlingDisabled, window,
                      {new NumberedCopies(moving)}) {}
};
}

KJob *Fusion::pasteFiles(const QUrl &destination, QWidget *window) {
  auto *job = KIO::paste(QApplication::clipboard()->mimeData(), destination);
  const QPointer<QWidget> parent(window);
  QObject::connect(job, &KIO::PasteJob::copyJobStarted, job,
                   [parent](KIO::CopyJob *copy) {
    copy->setUiDelegate(new TransferDelegate(parent, copy->operationMode() == KIO::CopyJob::Move));
  });
  return job;
}
