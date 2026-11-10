#include "context_actions.h"
#include "transfer_access.h"
#include <QtWidgets>
#include <KIO/EmptyTrashJob>
#include <KIO/JobUiDelegateFactory>
#include <KJobWidgets>
#include <algorithm>
bool Fusion::isArchive(const KFileItem &item) {
  if (item.isDir()) return false;
  const auto type = item.mimetype();
  if (!type.startsWith("application/") && !item.name().endsWith(".001")) return false;
  return type.contains("zip") || type.contains("tar") || type.contains("rar") ||
      type.contains("compressed") || type.contains("archive") || type.contains("7z") ||
      type == "application/x-iso9660-image" || type == "application/x-cd-image" ||
      item.name().endsWith(".001");
}
bool Fusion::launchArchive(const QString &operation, const QList<QUrl> &files, const QUrl &directory,
                          const std::function<void(const QString &)> &message) {
  if (files.isEmpty()) return false;
  QStringList args{Fusion::root()+"/archive_manager/app.py", operation};
  if (directory.isLocalFile()) args << "--directory" << directory.toLocalFile();
  args << "--";
  for (const auto &url : files) {
    const auto local = Fusion::ordinaryFileUrl(url);
    if (!local.isLocalFile()) {
      message("Save remote items to a local folder before using 7-Zip."); return false;
    }
    args << local.toLocalFile();
  }
  if (!QProcess::startDetached("/usr/bin/python3", args)) {
    message("The Fusion 7-Zip window could not be started."); return false;
  }
  return true;
}
void Fusion::addArchiveActions(QMenu *menu, const KFileItemList &items, bool compress, bool extract,
    QObject *owner, const QUrl &directory, const std::function<void(const QString &)> &message,
    const std::function<bool()> &guard) {
  if (items.isEmpty() || (!compress && !extract)) return;
  auto *archive = menu->addMenu(Fusion::icon("package-x-generic"), "7-Zip");
  archive->setObjectName("sevenZipMenu");
  archive->menuAction()->setProperty("iconName", "package-x-generic");
  QList<QUrl> files;
  for (const auto &item : items) files << item.url();
  auto append = [&](const QString &text, const QString &operation) {
    auto *action = archive->addAction(text);
    action->setObjectName("sevenZip_"+operation);
    action->setProperty("iconName", operation.startsWith("extract") ? "archive-extract" : "package-x-generic");
    QObject::connect(action, &QAction::triggered, owner, [files, operation, directory, message, guard] {
      if (!guard || guard()) Fusion::launchArchive(operation, files, directory, message);
    });
  };
  if (compress) {
    append("Compress…", "compress");
    append("Compress to…", "compress-to");
    append("Compress to 7z", "quick-7z");
    append("Compress to ZIP", "quick-zip");
  }
  const bool filesOnly = std::none_of(items.cbegin(), items.cend(), [](const KFileItem &item) { return item.isDir(); });
  if (extract && filesOnly) {
    if (compress) archive->addSeparator();
    append("Open archive…", "open");
    append("Extract here", "extract-here");
    append("Extract to separate folder", "extract-folder");
    append("Extract to…", "extract");
    append("Test archive", "test");
  }
}
Fusion::MenuEditor::MenuEditor(const Preferences &preferences, const QString &scope, QWidget *parent)
    : QWidget(parent) {
  setObjectName(scope == "desktopMenu" ? "desktopMenuEditor" : "filesMenuEditor");
  auto *layout = new QVBoxLayout(this);
  auto *intro = new QLabel(
      (scope == "desktopMenu" ? "Right-click actions for files and folders on the desktop.\n"
                              : "Right-click actions for files and folders in Fusion Files.\n")
      + QString("Drag to reorder; uncheck to hide an action."));
  intro->setWordWrap(true);
  layout->addWidget(intro);
  list = new QListWidget;
  list->setObjectName("menuActions");
  list->setDragDropMode(QAbstractItemView::InternalMove);
  layout->addWidget(list, 1);
  auto populate = [this](const QList<QVariantMap> &entries) {
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
  auto edit = [this](bool creating) {
    auto *item = list->currentItem();
    if (!creating && !item)
      return;
    QVariantMap data =
        creating ? QVariantMap{{"id", "custom:" + QUuid::createUuid().toString(
                                                      QUuid::WithoutBraces)},
                               {"enabled", true},
                               {"icon", "application-x-executable"}}
                 : item->data(Qt::UserRole).toMap();
    QDialog editor(this);
    editor.setObjectName("menuActionEditor");
    editor.setWindowTitle(creating ? "Add action" : "Edit action");
    auto *form = new QFormLayout(&editor);
    auto *name = new QLineEdit(data["name"].toString());
    name->setObjectName("actionName");
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
    auto *command = new QLineEdit(data["command"].toString(), &editor);
    command->setObjectName("actionCommand");
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
    QObject::connect(button, &QPushButton::clicked, this, [this, edit, populate, label] {
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
}

QList<QVariantMap> Fusion::MenuEditor::entries() const {
  QList<QVariantMap> entries;
  for (int i = 0; i < list->count(); ++i) {
    auto *item = list->item(i);
    auto data = item->data(Qt::UserRole).toMap();
    data["enabled"] = item->checkState() == Qt::Checked;
    entries << data;
  }
  return entries;
}

void Fusion::customizeMenu(Preferences &preferences, QWidget *parent, const QString &scope) {
  QDialog dialog(parent);
  dialog.setWindowTitle(scope == "desktopMenu" ? "Customize desktop file menu" : "Customize context menu");
  dialog.resize(680, 550);
  auto *layout = new QVBoxLayout(&dialog);
  auto *menu = new MenuEditor(preferences, scope);
  layout->addWidget(menu);
  auto *box =
      new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
  layout->addWidget(box);
  QObject::connect(box, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  QObject::connect(box, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  if (dialog.exec() == QDialog::Accepted)
    preferences.setMenu(menu->entries(), scope);
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
