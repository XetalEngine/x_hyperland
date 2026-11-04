#pragma once
#include <QtCore>

struct Volume;

// Personal choices use filesystem UUIDs. Attempts and deliberate unmounts
// belong to one Hyprland login and one physical-device connection.
class AutoMountPolicy {
public:
  struct Choice { bool available = false; Qt::CheckState state = Qt::Unchecked; int volumes = 0; };
  explicit AutoMountPolicy(const QString &settings = {}, const QString &session = {});
  bool observe(const QList<Volume> &volumes, QString *error);
  Choice choice(const QString &drive, const QList<Volume> &volumes) const;
  bool setEnabled(const QString &drive, const QList<Volume> &volumes, bool enabled, QString *error);
  bool next(const QList<Volume> &volumes, Volume *target, QString *error);
  bool suppress(const Volume &volume, QString *error);
  static bool eligible(const Volume &volume, const QList<Volume> &volumes);
  static bool systemMount(const QString &path);
private:
  QString settingsPath, sessionPath;
  QJsonObject entries;
  bool reload(QString *error);
  bool edit(const std::function<bool(QJsonObject &)> &change, QString *error);
  bool known(const Volume &volume) const;
  QJsonObject ticket(const Volume &volume) const;
};
