#include "search_presets.h"
#include <cmath>

namespace {
constexpr qint64 presetLimit = 128 * 1024;
bool fail(QString *error, const QString &message) {
  if (error)
    *error = message;
  return false;
}
} // namespace

namespace FusionSearch {
QJsonObject defaults() {
  return {
      {"root", ""},        {"query", ""},        {"contents", false},
      {"regex", false},    {"case", false},      {"word", false},
      {"recursive", true}, {"hidden", false},    {"follow", false},
      {"binary", false},   {"multiline", false}, {"folders", true},
      {"names", "*"},      {"types", ""},        {"extensions", ""},
      {"exclude", ""},     {"encoding", "auto"}, {"workers", 0},
      {"limit", 20000},    {"min_size", 0},      {"max_size", 64 * 1024 * 1024},
      {"after", 0},        {"before", 0}};
}

bool extensions(const QString &text, QStringList *values, QString *error) {
  values->clear();
  if (text.size() > 8192)
    return fail(error, "The extension list is too long.");
  for (auto value :
       text.split(QRegularExpression("[,;|\\s]+"), Qt::SkipEmptyParts)) {
    if (value.startsWith("*."))
      value.remove(0, 1);
    if (!value.startsWith('.'))
      value.prepend('.');
    if (value.size() < 2 || value.endsWith('.') ||
        value.contains(QRegularExpression("[*/\\\\?\\[\\]\\x00-\\x1f]")))
      return fail(error,
                  "Enter extensions such as .txt, .html or .cpp, separated by "
                  "commas. Leave the box empty for all types.");
    if (!values->contains(value))
      values->append(value);
  }
  if (extensionPatterns(*values).size() > 8192)
    return fail(error, "The extension list is too long.");
  if (error)
    error->clear();
  return true;
}
QString extensionPatterns(const QStringList &values) {
  QStringList patterns;
  for (const auto &value : values)
    patterns << '*' + value;
  return patterns.join(';');
}
QString extensionText(const QString &patterns) {
  QStringList values;
  return extensions(patterns, &values, nullptr) ? values.join(", ") : QString();
}

bool settings(const QJsonObject &input, QJsonObject *normalized,
              QString *error) {
  auto result = defaults();
  for (auto it = result.begin(); it != result.end(); ++it) {
    if (!input.contains(it.key()))
      continue;
    const auto value = input[it.key()];
    if (value.type() != it.value().type())
      return fail(error, "Invalid preset setting: " + it.key());
    if (value.isString() &&
        (value.toString().size() > 8192 || value.toString().contains(QChar(0))))
      return fail(error, "Invalid text in preset setting: " + it.key());
    if (value.isDouble() &&
        (!std::isfinite(value.toDouble()) || value.toDouble() < 0 ||
         std::floor(value.toDouble()) != value.toDouble() ||
         value.toDouble() > double(1LL << 40)))
      return fail(error, "Invalid number in preset setting: " + it.key());
    it.value() = value;
  }
  QStringList values;
  if (!extensions(input.contains("extensions") ? result["extensions"].toString()
                                               : result["types"].toString(),
                  &values, error))
    return false;
  result["extensions"] = values.join(", ");
  result["types"] = extensionPatterns(values);
  if (!QStringList{"auto", "utf-8", "utf-16le", "utf-16be", "windows-1252"}
           .contains(result["encoding"].toString()))
    return fail(error, "Unsupported text encoding in this preset.");
  if (result["workers"].toInt(-1) < 0 || result["workers"].toInt(33) > 32 ||
      result["limit"].toInt(0) < 1 || result["limit"].toInt(100001) > 100000)
    return fail(error,
                "This preset has an invalid worker count or result limit.");
  for (const auto &key : {"min_size", "max_size"})
    if (result[key].toInteger() % 1048576)
      return fail(error, "Preset file sizes must be whole MiB values.");
  if (result["max_size"].toInteger() &&
      result["min_size"].toInteger() > result["max_size"].toInteger())
    return fail(error, "Minimum file size must not exceed maximum file size.");
  if ((result["after"].toInteger() && result["before"].toInteger() &&
       result["after"].toInteger() >= result["before"].toInteger()) ||
      result["after"].toInteger() >
          QDate(9999, 12, 30).startOfDay().toSecsSinceEpoch() ||
      result["before"].toInteger() >
          QDate(9999, 12, 31).startOfDay().toSecsSinceEpoch())
    return fail(error, "Check the preset's modified-date range.");
  *normalized = result;
  if (error)
    error->clear();
  return true;
}
} // namespace FusionSearch

SearchPresets::SearchPresets(const QString &directory, QObject *parent)
    : QObject(parent), folder(QDir(directory).absolutePath()) {
  connect(&watcher, &QFileSystemWatcher::directoryChanged, this,
          &SearchPresets::refresh);
  // A polling fallback also handles deletion/recreation of the entire folder
  // and filesystems that do not deliver local directory notifications.
  connect(&poll, &QTimer::timeout, this, &SearchPresets::refresh);
  poll.start(1000);
  refresh();
}

QString SearchPresets::pathForName(const QString &input) const {
  auto name = input.trimmed();
  if (name.endsWith(".json", Qt::CaseInsensitive))
    name.chop(5);
  name = name.trimmed();
  if (name.isEmpty() || name == "." || name == ".." || name.size() > 120 ||
      name.contains(QRegularExpression("[/\\\\\\x00-\\x1f]")))
    return {};
  return QDir(folder).filePath(name + ".json");
}

bool SearchPresets::ensureDirectory(QString *error) {
  const bool existed = QFileInfo(folder).isDir();
  if (!QDir().mkpath(folder))
    return fail(error, "Could not create the search presets folder.");
  if (!existed && !QFile::setPermissions(folder, QFileDevice::ReadOwner |
                                                     QFileDevice::WriteOwner |
                                                     QFileDevice::ExeOwner))
    return fail(error, "Could not set the search presets folder permissions.");
  refresh();
  return true;
}

bool SearchPresets::save(const QString &name, const QJsonObject &settings,
                         bool overwrite, QString *error) {
  const auto path = pathForName(name);
  if (path.isEmpty())
    return fail(error, "Choose a preset name without slashes or control "
                       "characters (up to 120 characters).");
  QJsonObject normalized;
  if (!FusionSearch::settings(settings, &normalized, error))
    return false;
  if (!ensureDirectory(error))
    return false;
  if (QFileInfo(path).isSymLink())
    return fail(error, "This preset is a symbolic link. Choose a different "
                       "preset name to save.");
  if (QFileInfo::exists(path) && !overwrite)
    return fail(error, "A preset with this name already exists.");
  const auto bytes =
      QJsonDocument(QJsonObject{{"format", "hyperfusion.files.search"},
                                {"version", 1},
                                {"settings", normalized}})
          .toJson(QJsonDocument::Indented);
  if (bytes.size() > presetLimit)
    return fail(error, "This preset is too large.");
  QSaveFile file(path);
  if (!file.open(QIODevice::WriteOnly))
    return fail(error, file.errorString());
  if (!file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner) ||
      file.write(bytes) != bytes.size() || !file.commit())
    return fail(error, file.errorString());
  refresh();
  if (error)
    error->clear();
  return true;
}

bool SearchPresets::load(const QString &path, QJsonObject *settings,
                         QString *error) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly))
    return fail(error, "Could not load this preset: " + file.errorString());
  const auto bytes = file.read(presetLimit + 1);
  if (bytes.size() > presetLimit)
    return fail(error, "This preset is too large.");
  QJsonParseError parse;
  const auto document = QJsonDocument::fromJson(bytes, &parse);
  const auto object = document.object();
  if (parse.error != QJsonParseError::NoError || !document.isObject() ||
      object["format"] != "hyperfusion.files.search" ||
      object["version"] != 1 || !object["settings"].isObject())
    return fail(error,
                "This file is not a supported Fusion Files search preset.");
  return FusionSearch::settings(object["settings"].toObject(), settings, error);
}

void SearchPresets::refresh() {
  QStringList desired;
  auto existing = folder;
  while (!QFileInfo(existing).isDir()) {
    const auto parent = QFileInfo(existing).absolutePath();
    if (parent == existing)
      break;
    existing = parent;
  }
  if (QFileInfo(existing).isDir())
    desired << existing;
  if (existing == folder)
    desired << QFileInfo(folder).absolutePath();
  const auto current = watcher.directories();
  for (const auto &path : current)
    if (!desired.contains(path))
      watcher.removePath(path);
  for (const auto &path : desired)
    if (!current.contains(path))
      watcher.addPath(path);
  QStringList found;
  for (const auto &entry :
       QDir(folder).entryInfoList({"*.json"}, QDir::Files | QDir::Hidden,
                                  QDir::Name | QDir::IgnoreCase))
    found << entry.absoluteFilePath();
  if (found != entries) {
    entries = found;
    emit changed();
  }
}
