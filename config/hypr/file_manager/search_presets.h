#pragma once
#include <QtCore>

namespace FusionSearch {
QJsonObject defaults();
bool extensions(const QString &text, QStringList *values, QString *error);
QString extensionPatterns(const QStringList &values);
QString extensionText(const QString &patterns);
bool settings(const QJsonObject &input, QJsonObject *normalized,
              QString *error);
} // namespace FusionSearch

class SearchPresets : public QObject {
  Q_OBJECT
public:
  explicit SearchPresets(const QString &directory, QObject *parent = nullptr);
  QString directory() const { return folder; }
  QStringList files() const { return entries; }
  QString pathForName(const QString &name) const;
  bool ensureDirectory(QString *error);
  bool save(const QString &name, const QJsonObject &settings, bool overwrite,
            QString *error);
  static bool load(const QString &path, QJsonObject *settings, QString *error);
  void refresh();
signals:
  void changed();

private:
  QString folder;
  QStringList entries;
  QFileSystemWatcher watcher;
  QTimer poll;
};
