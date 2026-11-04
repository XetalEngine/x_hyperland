#include "context_actions.h"
#include <QtWidgets>
#include <KAbstractFileItemActionPlugin>
#include <KFileItemListProperties>
#include <KPluginFactory>
#include <KPluginMetaData>
#include <KIO/EmptyTrashJob>
#include <KIO/JobUiDelegateFactory>
#include <KJobWidgets>
#include <algorithm>
void Fusion::addArkActions(QMenu *menu, const KFileItemList &items, bool compress, bool extract,
    QObject *owner, QHash<QString, KAbstractFileItemActionPlugin *> &arkPlugins, const QUrl &directory,
    const std::function<void(const QString &)> &message, const std::function<bool()> &guard) {
  if (items.isEmpty() || (!compress && !extract))
    return;
  const bool archiveSelected =
      std::any_of(items.cbegin(), items.cend(), [](const KFileItem &item) {
        const auto type = item.mimetype();
        return type.contains("zip") || type.contains("tar") ||
               type.contains("rar") || type.contains("compressed") ||
               type.contains("7z") || type.contains("archive");
      });
  auto *ark = menu->addMenu(Fusion::icon("ark", "package-x-generic"), "Ark");
  ark->setObjectName("arkMenu");
  std::function<void(QMenu *, QAction *)> append = [&](QMenu *target,
                                                       QAction *original) {
    if (original->isSeparator()) {
      target->addSeparator();
      return;
    }
    if (original->menu()) {
      auto *child = target->addMenu(original->icon(), original->text());
      for (auto *action : original->menu()->actions())
        append(child, action);
      return;
    }
    auto *copy = target->addAction(original->icon(), original->text());
    copy->setEnabled(original->isEnabled());
    QObject::connect(copy, &QAction::triggered, owner,
            [original = QPointer<QAction>(original), guard] {
              if (original && (!guard || guard()))
                original->trigger();
            });
  };
  for (const auto &metadata :
       KPluginMetaData::findPlugins("kf6/kfileitemaction")) {
    const auto id = metadata.pluginId();
    if (!((id == "compressfileitemaction" && compress) ||
          (id == "extractfileitemaction" && extract && archiveSelected)))
      continue;
    auto *plugin = arkPlugins.value(id);
    if (!plugin) {
      plugin = KPluginFactory::instantiatePlugin<KAbstractFileItemActionPlugin>(
                   metadata, owner)
                   .plugin;
      if (!plugin)
        continue;
      arkPlugins.insert(id, plugin);
      QObject::connect(plugin, &KAbstractFileItemActionPlugin::error, owner,
              message);
    }
    const auto actions = plugin->actions(KFileItemListProperties(items), ark);
    if (!ark->actions().isEmpty() && !actions.isEmpty())
      ark->addSeparator();
    for (auto *action : actions) {
      if (action->menu())
        for (auto *option : action->menu()->actions())
          append(ark, option);
      else
        append(ark, action);
    }
  }
  if (ark->actions().isEmpty()) {
    // Some distributions ship the executable separately from its menu plugins.
    auto fallback = [&](bool unpack) {
      auto *action = ark->addAction(unpack ? "Extract archive…" : "Compress…");
      action->setEnabled(!QStandardPaths::findExecutable("ark").isEmpty());
      QObject::connect(action, &QAction::triggered, owner, [directory, message, items, guard, unpack] {
        if (guard && !guard())
          return;
        QStringList args =
            unpack ? QStringList{"--batch", "--dialog", "--autosubfolder"}
                   : QStringList{"--add", "--dialog"};
        if (unpack && directory.isLocalFile())
          args << "--destination" << directory.toLocalFile();
        args << "--";
        for (const auto &item : items)
          args << (item.url().isLocalFile() ? item.url().toLocalFile()
                                            : item.url().toString());
        if (!QProcess::startDetached("ark", args))
          message("Ark could not be started.");
      });
    };
    if (compress)
      fallback(false);
    if (extract && archiveSelected)
      fallback(true);
    if (ark->isEmpty())
      ark->menuAction()->setVisible(false);
  }
}
void Fusion::customizeMenu(Preferences &preferences, QWidget *parent, const QString &scope) {
  QDialog dialog(parent);
  dialog.setWindowTitle(scope == "desktopMenu" ? "Customize desktop file menu" : "Customize context menu");
  dialog.resize(680, 550);
  auto *layout = new QVBoxLayout(&dialog);
  auto *intro = new QLabel(
      "Choose the actions you use. Drag to reorder; uncheck to hide.");
  layout->addWidget(intro);
  auto *list = new QListWidget;
  list->setDragDropMode(QAbstractItemView::InternalMove);
  layout->addWidget(list, 1);
  auto populate = [&](const QList<QVariantMap> &entries) {
    list->clear();
    for (const auto &entry : entries) {
      auto *item = new QListWidgetItem(Fusion::icon(entry["icon"].toString()),
                                       entry["name"].toString(), list);
      item->setData(Qt::UserRole, entry);
      item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
      item->setCheckState(
          entry.value("enabled", true).toBool() ? Qt::Checked : Qt::Unchecked);
    }
  };
  populate(preferences.menu(scope));
  auto *buttons = new QHBoxLayout;
  layout->addLayout(buttons);
  auto edit = [&](bool creating) {
    auto *item = list->currentItem();
    if (!creating && !item)
      return;
    QVariantMap data =
        creating ? QVariantMap{{"id", "custom:" + QUuid::createUuid().toString(
                                                      QUuid::WithoutBraces)},
                               {"enabled", true},
                               {"icon", "application-x-executable"}}
                 : item->data(Qt::UserRole).toMap();
    QDialog editor(&dialog);
    editor.setWindowTitle(creating ? "Add action" : "Edit action");
    auto *form = new QFormLayout(&editor);
    auto *name = new QLineEdit(data["name"].toString());
    auto *icon = new QLineEdit(data["icon"].toString());
    form->addRow("Name", name);
    form->addRow("Icon name or image path", icon);
    auto *choose = new QPushButton("Choose icon…");
    form->addRow("", choose);
    QObject::connect(choose, &QPushButton::clicked, &editor, [&] {
      const auto path = QFileDialog::getOpenFileName(
          &editor, "Choose icon", {}, "Images (*.svg *.png *.jpg *.webp)");
      if (!path.isEmpty())
        icon->setText(path);
    });
    auto *command = new QLineEdit(data["command"].toString());
    const bool custom = data["id"].toString().startsWith("custom:");
    if (custom) {
      form->addRow("Command", command);
      auto *hint =
          new QLabel("%f / %F: local file(s) · %u / %U: URL(s)\nArguments are "
                     "passed directly, without a shell.");
      form->addRow(hint);
    }
    auto *box =
        new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
    form->addRow(box);
    QObject::connect(box, &QDialogButtonBox::accepted, &editor, &QDialog::accept);
    QObject::connect(box, &QDialogButtonBox::rejected, &editor, &QDialog::reject);
    if (editor.exec() != QDialog::Accepted ||
        name->text().trimmed().isEmpty() ||
        (custom && QProcess::splitCommand(command->text()).isEmpty()))
      return;
    data["name"] = name->text();
    data["icon"] = icon->text();
    if (custom)
      data["command"] = command->text();
    if (creating) {
      item = new QListWidgetItem(list);
      item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
      item->setCheckState(Qt::Checked);
    }
    item->setText(name->text());
    item->setIcon(Fusion::icon(icon->text()));
    item->setData(Qt::UserRole, data);
  };
  for (const auto &label : {"Add…", "Edit…", "Remove", "Restore defaults"}) {
    auto *button = new QPushButton(label);
    buttons->addWidget(button);
    QObject::connect(button, &QPushButton::clicked, &dialog, [&, label] {
      if (QString(label) == "Add…")
        edit(true);
      else if (QString(label) == "Edit…")
        edit(false);
      else if (QString(label) == "Remove") {
        auto *item = list->currentItem();
        if (item && item->data(Qt::UserRole)
                        .toMap()["id"]
                        .toString()
                        .startsWith("custom:"))
          delete item;
        else if (item)
          item->setCheckState(Qt::Unchecked);
      } else
        populate(Fusion::menuDefaults());
    });
  }
  auto *box =
      new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
  layout->addWidget(box);
  QObject::connect(box, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  QObject::connect(box, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  if (dialog.exec() == QDialog::Accepted) {
    QList<QVariantMap> entries;
    for (int i = 0; i < list->count(); ++i) {
      auto *item = list->item(i);
      auto data = item->data(Qt::UserRole).toMap();
      data["enabled"] = item->checkState() == Qt::Checked;
      entries << data;
    }
    preferences.setMenu(entries, scope);
  }
}

void Fusion::emptyTrash(QWidget *parent, const std::function<void()> &finished) {
  static QPointer<QMessageBox> confirmation;
  static bool running = false;
  if (running) return;
  if (confirmation) { confirmation->raise(); confirmation->activateWindow(); return; }
  auto *dialog = new QMessageBox(QMessageBox::Warning, "Empty Trash",
      "Permanently delete all items in your Trash, including Trash on connected drives?\nThis cannot be undone.",
      QMessageBox::Cancel, parent);
  confirmation = dialog;
  dialog->setObjectName("emptyTrashConfirmation");
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  auto *empty = dialog->addButton("Empty Trash", QMessageBox::DestructiveRole);
  dialog->setDefaultButton(QMessageBox::Cancel);
  QObject::connect(dialog, &QDialog::finished, dialog, [dialog, empty, finished] {
    if (dialog->clickedButton() != empty) return;
    running = true;
    auto *job = KIO::emptyTrash();
    job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, nullptr));
    QObject::connect(job, &KJob::result, qApp, [finished](KJob *) { running = false; if (finished) finished(); });
  });
  dialog->open();
}
