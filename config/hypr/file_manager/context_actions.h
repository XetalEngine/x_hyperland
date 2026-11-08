#pragma once
#include "core.h"
#include <KFileItem>
#include <QWidget>
#include <functional>
class QListWidget;
class QMenu;
class KAbstractFileItemActionPlugin;
namespace Fusion {
class MenuEditor : public QWidget {
public:
  MenuEditor(const Preferences &preferences, const QString &scope, QWidget *parent = nullptr);
  QList<QVariantMap> entries() const;
private:
  QListWidget *list;
};
void customizeMenu(Preferences &preferences, QWidget *parent = nullptr, const QString &scope = "menu");
void addArkActions(QMenu *menu, const KFileItemList &items, bool compress, bool extract,
    QObject *owner, QHash<QString, KAbstractFileItemActionPlugin *> &plugins, const QUrl &directory,
    const std::function<void(const QString &)> &message, const std::function<bool()> &guard = {});
void emptyTrash(QWidget *parent = nullptr, const std::function<void()> &finished = {});
}
