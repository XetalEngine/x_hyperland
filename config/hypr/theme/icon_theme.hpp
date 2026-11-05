#pragma once
// The same profile-local library as icon_themes/model.py. No KDE/global writes.
#include <QDir>
#include <QFile>
#include <QIcon>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>
#include <QStringList>

namespace XetalIcons {
inline QJsonObject read(const QString &path) {
  QFile file(path);
  return file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject{};
}
inline QString name(const QString &root) {
  const auto state=read(root+"/theme/state.json");
  const auto mode=state.value("mode").toString("dark");
  const auto key=state.value("design").toString("hollowgrove")+":"+mode;
  return read(root+"/theme/icons.json").value("resolved").toObject().value("themes").toObject()
      .value(key).toString(mode=="light" ? "Papirus-Light" : "Papirus-Dark");
}
inline QStringList paths(const QString &root) {
  QStringList result{root+"/icon_themes/.build/icons",root+"/icon_themes/packs",root+"/icon_themes/imported"};
  result << QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)+"/icons" << QDir::homePath()+"/.icons";
  for (const auto &path:QStandardPaths::standardLocations(QStandardPaths::GenericDataLocation)) result << path+"/icons";
  result << "/usr/local/share/icons" << "/usr/share/icons";
  result.removeDuplicates();return result;
}
inline void apply(const QString &root) {
  QIcon::setThemeSearchPaths(paths(root));QIcon::setFallbackThemeName("hicolor");QIcon::setThemeName(name(root));
}
}
