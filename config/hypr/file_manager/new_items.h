#pragma once
#include <QtCore>
#include <functional>
class QWidget;
class QMenu;
class KJob;
namespace KIO { class Job; }

namespace Fusion {
struct NewItem {
  QString id, name, filename, kind, text, source;
  bool enabled = true;
};
struct TemplateCatalog {
  QList<NewItem> entries;
  QByteArray revision;
  QString error;
};
QString templateSettingsPath();
TemplateCatalog loadTemplates(const QString &path = templateSettingsPath());
bool saveTemplates(const TemplateCatalog &catalog, QString *error,
                   const QString &path = templateSettingsPath());
QList<NewItem> newItems();
void configureTemplates(QWidget *parent = nullptr);
KIO::Job *createNewItem(const NewItem &item, const QString &name, const QUrl &directory);
struct NewItemCallbacks {
  std::function<void(KJob *)> track;
  std::function<void(const QUrl &)> target, created;
  std::function<void()> finished;
};
bool promptNewItem(const QString &id, const QUrl &directory, QWidget *parent,
                   QObject *owner, const NewItemCallbacks &callbacks = {});
void addNewMenu(QMenu *menu, const QUrl &directory, QWidget *parent, QObject *owner,
                const NewItemCallbacks &callbacks = {});
}
