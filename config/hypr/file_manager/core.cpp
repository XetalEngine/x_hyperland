#include "core.h"
#include <QApplication>
#include <QPainter>
#include <QPalette>
#include <QStandardPaths>

namespace Fusion {
QString root() {
  const QString configured = qEnvironmentVariable("XETAL_FILES_ROOT");
  return configured.isEmpty()
             ? QDir(QCoreApplication::applicationDirPath() + "/../..")
                   .absolutePath()
             : configured;
}
QUrl computerUrl() { return QUrl("computer:/"); }
bool isComputer(const QUrl &url) { return url.scheme() == "computer"; }
QUrl userUrl(const QString &text, const QUrl &base) {
  if (text.compare("This PC", Qt::CaseInsensitive) == 0 ||
      text.compare("My Computer", Qt::CaseInsensitive) == 0)
    return computerUrl();
  QString input = text;
  if (input == "~")
    input = QDir::homePath();
  else if (input.startsWith("~/"))
    input = QDir::homePath() + input.mid(1);
  if (input.startsWith("//"))
    return QUrl("smb:" + input);
  if (input.startsWith('/'))
    return QUrl::fromLocalFile(QDir::cleanPath(input));
  const QUrl url(input);
  if (!url.scheme().isEmpty())
    return url.adjusted(QUrl::NormalizePathSegments);
  if (base.isLocalFile())
    return QUrl::fromLocalFile(
        QDir(base.toLocalFile()).absoluteFilePath(input));
  if (base.isValid() && !isComputer(base)) {
    QUrl directory = base;
    if (!directory.path().endsWith('/'))
      directory.setPath(directory.path() + '/');
    return directory.resolved(QUrl(input));
  }
  return QUrl::fromLocalFile(QDir::home().absoluteFilePath(input));
}
QString displayPath(const QUrl &url) {
  return url.isLocalFile() ? url.toLocalFile()
                           : url.toDisplayString(QUrl::RemovePassword);
}
QString title(const QUrl &url) {
  if (isComputer(url))
    return "This PC";
  if (url.scheme() == "trash")
    return "Trash";
  if ((url.scheme() == "remote" || url.scheme() == "network") &&
      url.path() == "/")
    return "Network";
  if (url.isLocalFile() && url.toLocalFile() == QDir::homePath())
    return "Home";
  const QString filename = url.adjusted(QUrl::StripTrailingSlash).fileName();
  return filename.isEmpty() ? (url.isLocalFile()      ? "File System"
                               : url.host().isEmpty() ? displayPath(url)
                                                      : url.host())
                            : filename;
}
QIcon icon(const QString &name, const QString &fallback) {
  if (name.isEmpty())
    return {};
  if (name.startsWith('/'))
    return QIcon(name);
  if (name == "fusion-computer")
    return QIcon(root() + "/file_manager/computer.svg");
  if (name == "drive-harddisk")
    return QIcon(root() + "/file_manager/drive.svg");
  if (name == "drive-removable-media-usb")
    return QIcon(root() + "/file_manager/removable.svg");
  const QIcon original = QIcon::fromTheme(name, QIcon::fromTheme(fallback));
  QPixmap pixmap = original.pixmap(48, 48);
  if (name.startsWith("go-") || name.startsWith("edit-") ||
      name.startsWith("view-") || name.startsWith("document-") ||
      name == "application-menu" || name == "tab-new" || name == "folder-new" ||
      name == "bookmark-new" || name == "media-eject") {
    QPainter painter(&pixmap);
    painter.setCompositionMode(QPainter::CompositionMode_SourceIn);
    painter.fillRect(pixmap.rect(),
                     qApp->palette().color(QPalette::WindowText));
  }
  return QIcon(pixmap);
}
QList<QVariantMap> defaultPlaces() {
  QList<QVariantMap> result{
      {{"name", "Home"},
       {"url", QUrl::fromLocalFile(QDir::homePath()).toString()},
       {"icon", "user-home"}}};
  struct Place {
    const char *name;
    QStandardPaths::StandardLocation path;
    const char *icon;
  };
  for (const auto &place :
       {Place{"Desktop", QStandardPaths::DesktopLocation, "user-desktop"},
        {"Documents", QStandardPaths::DocumentsLocation, "folder-documents"},
        {"Downloads", QStandardPaths::DownloadLocation, "folder-download"},
        {"Pictures", QStandardPaths::PicturesLocation, "folder-pictures"},
        {"Music", QStandardPaths::MusicLocation, "folder-music"},
        {"Videos", QStandardPaths::MoviesLocation, "folder-videos"}}) {
    const QString path = QStandardPaths::writableLocation(place.path);
    if (!path.isEmpty() && path != QDir::homePath())
      result.append({{"name", place.name},
                     {"url", QUrl::fromLocalFile(path).toString()},
                     {"icon", place.icon}});
  }
  return result;
}
QList<QVariantMap> menuDefaults() {
  QList<QVariantMap> entries;
  const QList<QStringList> definitions{
      {"execute", "Execute", "system-run"},
      {"open", "Open", "document-open"},
      {"openTab", "Open in new tab", "tab-new"},
      {"openWith", "Open with…", "application-x-executable"},
      {"cut", "Cut", "edit-cut"},
      {"copy", "Copy", "edit-copy"},
      {"paste", "Paste", "edit-paste"},
      {"rename", "Rename…", "edit-rename"},
      {"trash", "Move to Trash", "user-trash"},
      {"delete", "Delete permanently…", "edit-delete"},
      {"newFolder", "New folder…", "folder-new"},
      {"pin", "Pin to quick access", "bookmark-new"},
      {"copyPath", "Copy full path", "edit-copy"},
      {"terminal", "Open terminal here", "utilities-terminal"},
      {"compress", "Compress…", "package-x-generic"},
      {"extract", "Extract archive…", "archive-extract"},
      {"properties", "Properties", "document-properties"}};
  for (const auto &entry : definitions)
    entries.append({{"id", entry[0]},
                    {"name", entry[1]},
                    {"icon", entry[2]},
                    {"enabled", entry[0] != "delete"}});
  return entries;
}
QStringList expandCommand(const QString &command, const QList<QUrl> &urls) {
  QStringList output;
  for (QString part : QProcess::splitCommand(command)) {
    if (part == "%F" || part == "%U") {
      for (const auto &url : urls) {
        if (part == "%F" && !url.isLocalFile())
          return {};
        output << (part == "%F" ? url.toLocalFile() : url.toString());
      }
    } else {
      if (part.contains("%F") || part.contains("%U"))
        return {};
      if (part.contains("%f") && (!urls.size() || !urls.first().isLocalFile()))
        return {};
      if (part.contains("%u") && urls.isEmpty())
        return {};
      // Expand without a shell: filenames containing quotes, $() or semicolons
      // stay data.
      QString expanded;
      int offset = 0;
      auto matches = QRegularExpression("%[fu]").globalMatch(part);
      while (matches.hasNext()) {
        const auto match = matches.next();
        expanded += part.mid(offset, match.capturedStart() - offset);
        expanded += match.captured() == "%f" ? urls.first().toLocalFile()
                                             : urls.first().toString();
        offset = match.capturedEnd();
      }
      output << expanded + part.mid(offset);
    }
  }
  return output;
}
bool validName(const QString &name) {
  return !name.isEmpty() && name != "." && name != ".." &&
         !name.contains('/') && !name.contains(QChar::Null);
}
QStringList executionCommand(const QUrl &url) {
  if (!url.isLocalFile())
    return {};
  const QFileInfo info(url.toLocalFile());
  if (!info.isFile())
    return {};
  const auto type = QMimeDatabase().mimeTypeForFile(info).name();
  QFile script(info.absoluteFilePath());
  QString first;
  if (script.open(QIODevice::ReadOnly))
    first = QString::fromUtf8(script.readLine(4096)).trimmed();
  const bool shell = type == "application/x-shellscript" ||
                     type == "text/x-shellscript" ||
                     QStringList{"sh", "bash", "zsh", "ksh"}.contains(info.suffix()) ||
                     (info.isExecutable() && first.startsWith("#!"));
  if (shell) {
    // Run scripts explicitly in a terminal, keeping output visible. Never
    // change executable permissions or interpolate a filename into a shell.
    QStringList command;
    if (!script.isOpen())
      return {};
    if (first.startsWith("#!"))
      command = QProcess::splitCommand(first.mid(2).trimmed());
    if (command.isEmpty())
      command << (info.suffix() == "zsh" ? "zsh" : info.suffix() == "ksh" ? "ksh" : "bash");
    command << info.absoluteFilePath();
    return QStringList{"kitty", "--hold", "--directory", info.absolutePath(), "-e"} + command;
  }
  if (info.isExecutable() && (type == "application/x-executable" ||
                              type == "application/x-pie-executable" ||
                              type == "application/x-appimage" ||
                              type.startsWith("text/x-")))
    return {info.absoluteFilePath()};
  return {};
}
Preferences::Preferences(const QString &path)
    : settings(path.isEmpty() ? root() + "/file_manager/state/settings.ini"
                              : path,
               QSettings::IniFormat) {}
static QList<QVariantMap> readList(const QSettings &settings,
                                   const QString &key,
                                   const QList<QVariantMap> &fallback) {
  if (!settings.contains(key))
    return fallback;
  const auto document =
      QJsonDocument::fromJson(settings.value(key).toByteArray());
  if (!document.isArray())
    return fallback;
  QList<QVariantMap> result;
  for (const auto &entry : document.array())
    if (entry.isObject())
      result.append(entry.toObject().toVariantMap());
  return result;
}
static void writeList(QSettings &settings, const QString &key,
                      const QList<QVariantMap> &items) {
  QJsonArray array;
  for (const auto &item : items)
    array.append(QJsonObject::fromVariantMap(item));
  settings.setValue(key, QJsonDocument(array).toJson(QJsonDocument::Compact));
  settings.sync();
}
QList<QVariantMap> Preferences::places() const {
  return readList(settings, "places", defaultPlaces());
}
void Preferences::setPlaces(const QList<QVariantMap> &places) {
  writeList(settings, "places", places);
}
QList<QVariantMap> Preferences::menu() const {
  auto entries = readList(settings, "menu", menuDefaults());
  if (std::none_of(entries.cbegin(), entries.cend(), [](const auto &entry) {
        return entry.value("id").toString() == "execute";
      })) {
    auto execute = menuDefaults().first();
    for (const auto &entry : entries)
      if (entry.value("id").toString() == "open")
        execute["enabled"] = entry.value("enabled", true);
    entries.prepend(execute);
  }
  return entries;
}
void Preferences::setMenu(const QList<QVariantMap> &entries) {
  writeList(settings, "menu", entries);
}
} // namespace Fusion
