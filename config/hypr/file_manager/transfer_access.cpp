#include "transfer_access.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <cerrno>
#include <dirent.h>
#include <set>
#include <sys/stat.h>
#include <unistd.h>

namespace {
bool permissionError() { return errno == EACCES || errno == EPERM; }
bool denied(const QString &path, int mode) {
  return ::access(QFile::encodeName(path).constData(), mode) && permissionError();
}
bool cannotRemove(const QString &path, const struct stat &item) {
  const auto parent = QFileInfo(path).absolutePath();
  if (denied(parent, W_OK | X_OK)) return true;
  struct stat info;
  if (::stat(QFile::encodeName(parent).constData(), &info)) return permissionError();
  // Writable sticky directories still restrict removing another user's item.
  return geteuid() != 0 && (info.st_mode & S_ISVTX) &&
         info.st_uid != geteuid() && item.st_uid != geteuid();
}
bool protectedTree(const QString &path, bool removing,
                   const std::shared_ptr<std::atomic_bool> &cancelled) {
  QList<QString> pending{path};
  std::set<std::pair<dev_t, ino_t>> visited;
  while (!pending.isEmpty() && !cancelled->load()) {
    const auto next = pending.takeLast();
    struct stat info;
    if (::lstat(QFile::encodeName(next).constData(), &info)) {
      if (permissionError()) return true;
      continue; // Let KIO report disappeared items and other real errors.
    }
    if (removing && cannotRemove(next, info)) return true;
    if (S_ISLNK(info.st_mode)) continue; // Copy the link, never its target.
    const bool directory = S_ISDIR(info.st_mode);
    if (denied(next, R_OK | (directory ? X_OK : 0))) return true;
    if (!directory || !visited.insert({info.st_dev, info.st_ino}).second) continue;
    DIR *dir = ::opendir(QFile::encodeName(next).constData());
    if (!dir) {
      if (permissionError()) return true;
      continue;
    }
    while (const auto *entry = ::readdir(dir)) {
      if (cancelled->load()) break;
      const QByteArray name(entry->d_name);
      if (name != "." && name != "..") pending << QDir(next).filePath(QFile::decodeName(name));
    }
    ::closedir(dir);
  }
  return false;
}
QUrl administratorUrl(QUrl url) {
  if (url.isLocalFile()) url.setScheme("admin");
  return url;
}
}

QUrl Fusion::ordinaryFileUrl(const QUrl &url) {
  if (url.scheme() == "admin" && url.host().isEmpty()) return QUrl::fromLocalFile(url.path());
  return url;
}

Fusion::TransferAccess Fusion::transferAccess(const QList<QUrl> &sources,
    const QUrl &destination, TransferOperation operation,
    const std::shared_ptr<std::atomic_bool> &cancelled) {
  TransferAccess plan{sources, destination, destination.scheme() == "admin"};
  if (destination.isLocalFile() && denied(destination.toLocalFile(), W_OK | X_OK)) {
    plan.destination = administratorUrl(destination);
    plan.administrator = true;
  }
  struct stat target;
  const bool localTarget = destination.isLocalFile() &&
      !::stat(QFile::encodeName(destination.toLocalFile()).constData(), &target);
  for (qsizetype i = 0; i < sources.size() && !cancelled->load(); ++i) {
    const auto &source = sources[i];
    if (source.scheme() == "admin") plan.administrator = true;
    if (!source.isLocalFile() || operation == TransferOperation::Link) continue;
    const auto path = source.toLocalFile();
    struct stat info;
    bool needsAdmin = false;
    if (::lstat(QFile::encodeName(path).constData(), &info)) {
      needsAdmin = permissionError();
    } else if (operation == TransferOperation::Move && localTarget && info.st_dev == target.st_dev) {
      // A same-filesystem rename needs the parent, not read access to contents.
      needsAdmin = cannotRemove(path, info);
    } else {
      needsAdmin = protectedTree(path, operation == TransferOperation::Move, cancelled);
    }
    if (needsAdmin) {
      plan.sources[i] = administratorUrl(source);
      plan.administrator = true;
    }
  }
  if (plan.administrator && operation == TransferOperation::Move) {
    // Use one protocol for local moves: retain atomic rename and ownership,
    // instead of turning a protected rename into a copy followed by deletion.
    for (auto &source : plan.sources) source = administratorUrl(source);
    plan.destination = administratorUrl(plan.destination);
  }
  return plan;
}
