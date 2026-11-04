#include "automount.h"
#include "core.h"
#include "drives.h"

namespace {
bool fail(QString *error, const QString &message) {
  if (error) *error = message;
  return false;
}
bool read(const QString &path, QJsonObject *data, QString *error) {
  if (!QFileInfo::exists(path)) { *data = {}; return true; }
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly)) return fail(error, file.errorString());
  if (file.size() > 1024 * 1024) return fail(error, "Auto mount settings are too large.");
  QJsonParseError parse;
  const auto document = QJsonDocument::fromJson(file.readAll(), &parse);
  if (parse.error != QJsonParseError::NoError || !document.isObject() ||
      document["version"].toInt() != 1 || !document["volumes"].isObject())
    return fail(error, "Could not read Auto mount settings. The existing file was kept.");
  *data = document["volumes"].toObject();
  return true;
}
bool write(const QString &path, const QJsonObject &data, QString *error) {
  QSaveFile file(path);
  if (!file.open(QIODevice::WriteOnly)) return fail(error, file.errorString());
  file.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
  const auto bytes = QJsonDocument(QJsonObject{{"version", 1}, {"volumes", data}}).toJson();
  if (file.write(bytes) != bytes.size() || !file.commit()) return fail(error, file.errorString());
  return true;
}
bool prepare(const QString &path, QString *error) {
  return QDir().mkpath(QFileInfo(path).absolutePath()) || fail(error, "Could not create the Auto mount settings folder.");
}
bool validUuid(const QString &uuid) {
  static const QRegularExpression pattern("^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$");
  return pattern.match(uuid).hasMatch();
}
bool valid(const QJsonObject &entries, QString *error) {
  if (entries.size() > 2048) return fail(error, "Too many saved Auto mount volumes.");
  for (auto it = entries.begin(); it != entries.end(); ++it) {
    const auto value = it->toObject();
    const double revision = value["revision"].toDouble(-1);
    if (!validUuid(it.key()) || !value["filesystem"].isString() || value["filesystem"].toString().isEmpty() ||
        !value["enabled"].isBool() || revision < 0 || revision > 1e12 || revision != qint64(revision))
      return fail(error, "Invalid Auto mount settings. The existing file was kept.");
  }
  return true;
}
QString loginState() {
  const auto runtime = qEnvironmentVariable("XDG_RUNTIME_DIR");
  const auto signature = qEnvironmentVariable("HYPRLAND_INSTANCE_SIGNATURE");
  if (runtime.isEmpty() || signature.isEmpty() || signature.contains('/')) return {};
  const auto instance = runtime + "/hypr/" + signature;
  return QFileInfo::exists(instance + "/.socket.sock") ? instance + "/fusion-automount.json" : QString();
}
}

AutoMountPolicy::AutoMountPolicy(const QString &settings, const QString &session)
    : settingsPath(settings.isEmpty() ? Fusion::root() + "/file_manager/automount.json" : settings),
      sessionPath(session.isEmpty() ? loginState() : session) {}

bool AutoMountPolicy::systemMount(const QString &path) {
  return path == "/" || path == "/home" || path == "/usr" || path == "/var" ||
         path == "/boot" || path.startsWith("/boot/") || path == "/efi" || path.startsWith("/efi/");
}
bool AutoMountPolicy::eligible(const Volume &volume, const QList<Volume> &volumes) {
  if (volume.system || systemMount(volume.mount) || !volume.mountable() || !validUuid(volume.uuid)) return false;
  int same = 0;
  for (const auto &other : volumes) {
    if (other.uuid == volume.uuid) ++same;
    if (other.driveKey() == volume.driveKey() && (other.system || systemMount(other.mount))) return false;
  }
  return same == 1; // Cloned UUIDs must not choose an arbitrary physical drive.
}
bool AutoMountPolicy::known(const Volume &volume) const {
  return entries.contains(volume.uuid) && entries[volume.uuid].toObject()["filesystem"].toString() == volume.filesystem;
}
bool AutoMountPolicy::reload(QString *error) {
  QJsonObject next;
  if (!read(settingsPath, &next, error) || !valid(next, error)) { entries = {}; return false; }
  entries = next; return true;
}
bool AutoMountPolicy::edit(const std::function<bool(QJsonObject &)> &change, QString *error) {
  if (!prepare(settingsPath, error)) return false;
  QLockFile lock(settingsPath + ".lock");
  if (!lock.tryLock(100)) return fail(error, "Auto mount settings are busy. Try again.");
  if (!reload(error)) return false;
  auto next = entries;
  if (change(next) && (!valid(next, error) || !write(settingsPath, next, error))) return false;
  entries = next; return true;
}
bool AutoMountPolicy::observe(const QList<Volume> &volumes, QString *error) {
  if (!reload(error)) return false;
  bool missing = false;
  for (const auto &v : volumes)
    missing |= v.mounted() && v.verifiedMount && eligible(v, volumes) && !known(v);
  if (!missing) return true;
  return edit([&](QJsonObject &next) {
    for (const auto &v : volumes)
      if (v.mounted() && v.verifiedMount && eligible(v, volumes) &&
          next[v.uuid].toObject()["filesystem"].toString() != v.filesystem)
        next[v.uuid] = QJsonObject{{"filesystem", v.filesystem}, {"enabled", false}, {"revision", 0}};
    return true;
  }, error);
}
AutoMountPolicy::Choice AutoMountPolicy::choice(const QString &drive, const QList<Volume> &volumes) const {
  Choice result; int enabled = 0;
  for (const auto &v : volumes)
    if (v.driveKey() == drive && eligible(v, volumes) && known(v)) {
      ++result.volumes;
      enabled += entries[v.uuid].toObject()["enabled"].toBool();
    }
  result.available = result.volumes > 0;
  result.state = !enabled ? Qt::Unchecked : enabled == result.volumes ? Qt::Checked : Qt::PartiallyChecked;
  return result;
}
bool AutoMountPolicy::setEnabled(const QString &drive, const QList<Volume> &volumes, bool enabled, QString *error) {
  bool eligibleFound = false;
  const bool saved = edit([&](QJsonObject &next) {
    for (const auto &v : volumes) {
      if (v.driveKey() != drive || !eligible(v, volumes) || !known(v)) continue;
      auto entry = next[v.uuid].toObject();
      entry["enabled"] = enabled;
      entry["revision"] = entry["revision"].toDouble() + 1;
      next[v.uuid] = entry; eligibleFound = true;
    }
    return eligibleFound;
  }, error);
  return saved && (eligibleFound || fail(error, "Mount this drive successfully before enabling Auto mount."));
}
QJsonObject AutoMountPolicy::ticket(const Volume &v) const {
  return {{"device", v.device}, {"connection", v.connection},
          {"revision", entries[v.uuid].toObject()["revision"]}};
}
bool AutoMountPolicy::suppress(const Volume &volume, QString *error) {
  if (!reload(error)) return false;
  if (sessionPath.isEmpty() || !known(volume) || !entries[volume.uuid].toObject()["enabled"].toBool()) return true;
  if (!prepare(sessionPath, error)) return false;
  QLockFile lock(sessionPath + ".lock");
  if (!lock.tryLock(100)) return fail(error, "Auto mount is busy. Try again.");
  QJsonObject state;
  if (!read(sessionPath, &state, error)) return false;
  state[volume.uuid] = ticket(volume);
  return write(sessionPath, state, error);
}
bool AutoMountPolicy::next(const QList<Volume> &volumes, Volume *target, QString *error) {
  if (sessionPath.isEmpty() || !reload(error) || !prepare(sessionPath, error)) return false;
  QLockFile lock(sessionPath + ".lock");
  if (!lock.tryLock(100)) return fail(error, "Auto mount is busy. Try again.");
  QJsonObject state;
  if (!read(sessionPath, &state, error)) return false;
  const auto before = state;
  QSet<QString> present;
  for (const auto &v : volumes) present.insert(v.uuid);
  for (const auto &key : state.keys()) if (!present.contains(key)) state.remove(key);
  bool selected = false;
  for (const auto &v : volumes) {
    if (!eligible(v, volumes) || !known(v) || !entries[v.uuid].toObject()["enabled"].toBool()) continue;
    const auto current = ticket(v);
    if (v.mounted()) state[v.uuid] = current; // A later manual unmount stays unmounted.
    else if (!selected && state[v.uuid].toObject() != current) {
      *target = v; selected = true;
      state[v.uuid] = current; // Claim before starting; failures never loop.
    }
  }
  return (state == before || write(sessionPath, state, error)) && selected;
}
