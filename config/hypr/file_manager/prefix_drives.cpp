#include "prefix_drives.h"

namespace {
QByteArray read(const QString &path) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly) || file.size() > 8 * 1024 * 1024) return {};
  return file.read(8 * 1024 * 1024);
}
QString expand(QString path, const QString &home) {
  if (path == "~") path = home;
  else if (path.startsWith("~/")) path = home + path.mid(1);
  return QDir::isAbsolutePath(path) ? QDir::cleanPath(path) : QString();
}
// Steam's text VDF uses quoted strings with escaped quotes/backslashes.
struct Vdf {
  QMap<QString, QString> values;
  QMap<QString, Vdf> children;
};
Vdf parseVdf(const QByteArray &data) {
  static const QRegularExpression tokens(R"re("((?:\\.|[^"\\])*)"|([{}])|//[^\n]*|([^\s"{}]+))re");
  QStringList items;
  auto matches = tokens.globalMatch(QString::fromUtf8(data));
  while (matches.hasNext()) {
    const auto match = matches.next();
    if (match.captured().startsWith("//")) continue;
    auto token = match.captured(1);
    if (match.captured().startsWith('"')) {
      token.replace("\\\"", "\""); token.replace("\\\\", "\\");
      items << token;
    } else items << (match.captured(2).isEmpty() ? match.captured(3) : match.captured(2));
  }
  qsizetype at = 0;
  std::function<Vdf(int)> block = [&](int depth) {
    Vdf result;
    while (at < items.size()) {
      const auto key = items[at++];
      if (key == "}") break;
      if (at >= items.size() || depth > 20) break;
      const auto value = items[at++];
      if (value == "{") result.children.insert(key, block(depth + 1));
      else if (value != "}") result.values.insert(key, value);
    }
    return result;
  };
  return block(0);
}
}
PrefixDrives::Locations PrefixDrives::Locations::environment() {
  const auto home = QDir::homePath();
  return {home, qEnvironmentVariable("XDG_CONFIG_HOME", home + "/.config"),
      qEnvironmentVariable("XDG_DATA_HOME", home + "/.local/share"),
      qEnvironmentVariable("XETALPROTON_HOME"), qEnvironmentVariable("WINEPREFIX")};
}
QList<Volume> PrefixDrives::discover(const Locations &where) {
  QList<Volume> result; QSet<QString> seen;
  auto add = [&](const QString &raw, QString name, bool steam = false) {
    const auto path = expand(raw, where.home);
    if (path.isEmpty()) return;
    QString drive;
    for (const auto &suffix : {"/pfx/drive_c", "/drive_c"}) {
      const QFileInfo candidate(path + suffix);
      if (candidate.isDir()) { drive = candidate.canonicalFilePath(); break; }
    }
    if (drive.isEmpty() || seen.contains(drive)) return;
    seen.insert(drive);
    if (name.trimmed().isEmpty()) name = QFileInfo(path).fileName();
    Volume volume; volume.device = drive; volume.mount = drive; volume.driveDevice = drive;
    volume.name = name + " (C:)"; volume.driveModel = name;
    volume.type = steam ? "steam-prefix" : "wine-prefix";
    volume.filesystem = steam ? "Steam / Proton" : "Wine / Proton";
    volume.readOnly = !QFileInfo(drive).isWritable();
    result << volume;
  };
  const auto config = where.portable.isEmpty() ? where.config + "/XetalProton/config.json"
      : QDir(where.portable).absoluteFilePath("config/config.json");
  const auto settings = QJsonDocument::fromJson(read(config)).object();
  for (const auto &entry : settings["prefixes"].toArray()) {
    const auto prefix = entry.toObject(); add(prefix["path"].toString(), prefix["name"].toString());
  }
  for (const auto &entry : settings["shortcuts"].toArray()) add(entry.toObject()["prefix"].toString(), {});
  const auto defaults = settings["prefix_proton"].toObject();
  for (auto it = defaults.begin(); it != defaults.end(); ++it) add(it.key(), {});
  add(settings["last_prefix"].toString(), {});
  const auto data = where.portable.isEmpty() ? where.data + "/XetalProton" : QDir(where.portable).absolutePath();
  const auto prefixRoot = expand(settings["prefixes_root"].toString(data + "/prefixes"), where.home);
  if (!prefixRoot.isEmpty()) {
    const auto dirs = QDir(prefixRoot).entryList(QDir::Dirs | QDir::NoDotAndDotDot | QDir::Hidden, QDir::Name);
    for (const auto &name : dirs) add(prefixRoot + '/' + name, name);
  }
  add(where.wine, "Wine"); add(where.home + "/.wine", "Wine");

  QSet<QString> libraries;
  const QStringList steamRoots{where.data + "/Steam", where.home + "/.steam/root", where.home + "/.steam/steam",
      where.home + "/.steam/debian-installation", where.home + "/.var/app/com.valvesoftware.Steam/.local/share/Steam"};
  for (const auto &root : steamRoots) {
    if (!QFileInfo(root + "/steamapps").isDir()) continue;
    libraries.insert(QFileInfo(root).canonicalFilePath());
    for (const auto &suffix : {"/steamapps/libraryfolders.vdf", "/config/libraryfolders.vdf"}) {
      const auto folders = parseVdf(read(root + suffix)).children.value("libraryfolders");
      QStringList paths;
      for (const auto &folder : folders.children) paths << folder.values.value("path");
      // Older Steam clients stored the library paths directly under numeric keys.
      for (auto it = folders.values.begin(); it != folders.values.end(); ++it)
        if (QRegularExpression("^\\d+$").match(it.key()).hasMatch()) paths << it.value();
      for (const auto &path : paths) {
        const auto expanded = expand(path, where.home);
        if (!expanded.isEmpty() && QFileInfo(expanded + "/steamapps").isDir()) libraries.insert(QFileInfo(expanded).canonicalFilePath());
      }
    }
  }
  auto orderedLibraries = libraries.values(); orderedLibraries.sort();
  for (const auto &library : orderedLibraries) {
    const auto apps = library + "/steamapps";
    const auto ids = QDir(apps + "/compatdata").entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
    for (const auto &id : ids) {
      if (!QRegularExpression("^\\d+$").match(id).hasMatch()) continue;
      const auto manifest = parseVdf(read(apps + "/appmanifest_" + id + ".acf")).children.value("AppState");
      add(apps + "/compatdata/" + id, manifest.values.value("name", "Steam app " + id), true);
    }
  }
  std::stable_sort(result.begin(), result.end(), [](const Volume &a, const Volume &b) {
    if (a.type != b.type) return a.type == "wine-prefix";
    const int compare = QString::localeAwareCompare(a.name, b.name);
    return compare ? compare < 0 : a.device < b.device;
  });
  return result;
}
