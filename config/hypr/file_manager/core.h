#pragma once
#include <QIcon>
#include <QtCore>

namespace Fusion {
QString root();
QUrl computerUrl();
bool isComputer(const QUrl &url);
QUrl userUrl(const QString &text, const QUrl &base = QUrl());
QString displayPath(const QUrl &url);
QString title(const QUrl &url);
QIcon icon(const QString &name, const QString &fallback = "folder");
QList<QVariantMap> defaultPlaces();
QList<QVariantMap> menuDefaults();
QStringList expandCommand(const QString &command, const QList<QUrl> &urls);
bool validName(const QString &name);
QString executionKind(const QUrl &url);
bool executeOnOpen(const QUrl &url);
QList<QVariantMap> executionMenu(QList<QVariantMap> entries, const QList<QUrl> &urls);
QStringList executionCommand(const QUrl &url);

class Preferences {
public:
  explicit Preferences(const QString &path = {});
  QSettings settings;
  QList<QVariantMap> places() const;
  void setPlaces(const QList<QVariantMap> &places);
  QList<QVariantMap> menu(const QString &scope = "menu") const;
  void setMenu(const QList<QVariantMap> &entries, const QString &scope = "menu");
  QVariantMap folderView(const QUrl &url) const;
  void setFolderView(const QUrl &url, const QVariantMap &view);
  QString folderViewScope = "folderViews";
  int defaultPreviewWidth = 270;
};
} // namespace Fusion
