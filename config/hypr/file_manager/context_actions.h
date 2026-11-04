#pragma once
#include "core.h"
#include <KFileItem>
#include <functional>
class QMenu;
class QWidget;
class KAbstractFileItemActionPlugin;
namespace Fusion {
void customizeMenu(Preferences &preferences, QWidget *parent = nullptr, const QString &scope = "menu");
void addArkActions(QMenu *menu, const KFileItemList &items, bool compress, bool extract,
    QObject *owner, QHash<QString, KAbstractFileItemActionPlugin *> &plugins, const QUrl &directory,
    const std::function<void(const QString &)> &message, const std::function<bool()> &guard = {});
void emptyTrash(QWidget *parent = nullptr, const std::function<void()> &finished = {});
}
