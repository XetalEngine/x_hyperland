#include "new_items.h"
#include "core.h"
#include "transfers.h"
#include <QtWidgets>
#include <KIO/MkdirJob>
#include <KIO/Job>
#include <KIO/CopyJob>
#include <KIO/FileCopyJob>
#include <KIO/StoredTransferJob>
#include <KIO/FileUndoManager>

namespace {
QString validate(const Fusion::NewItem &item) {
  if (item.id.isEmpty() || item.id == "folder" || item.id == "text" || item.name.trimmed().isEmpty())
    return "Each template needs a name and a unique identity.";
  if (!Fusion::validName(item.filename)) return "Choose a file name without /, and different from . or ..";
  if (item.kind != "text" && item.kind != "file") return "Choose a text document or an existing template file.";
  if (item.kind == "file" && (!QDir::isAbsolutePath(item.source) || item.source.contains(QChar::Null)))
    return "Choose an absolute path to a template file.";
  return {};
}
void warning(QWidget *parent, const QString &text) {
  auto *box = new QMessageBox(QMessageBox::Warning, "New item", text, QMessageBox::Ok, parent);
  box->setTextFormat(Qt::PlainText); box->setAttribute(Qt::WA_DeleteOnClose); box->open();
}
bool editTemplate(Fusion::NewItem &item, QWidget *parent) {
  QDialog dialog(parent); dialog.setWindowTitle("Template entry"); dialog.resize(560, 460);
  auto *layout = new QVBoxLayout(&dialog);
  auto *form = new QFormLayout; layout->addLayout(form);
  auto *name = new QLineEdit(item.name); name->setObjectName("templateName");
  auto *filename = new QLineEdit(item.filename); filename->setObjectName("templateFilename");
  auto *kind = new QComboBox; kind->addItem("Text document", "text"); kind->addItem("Existing template file", "file");
  kind->setCurrentIndex(item.kind == "file" ? 1 : 0);
  form->addRow("Menu label", name); form->addRow("Default file name", filename); form->addRow("Create from", kind);
  auto *stack = new QStackedWidget; layout->addWidget(stack, 1);
  auto *textPage = new QWidget; auto *textLayout = new QVBoxLayout(textPage); textLayout->setContentsMargins(0, 0, 0, 0);
  textLayout->addWidget(new QLabel("Starting text (optional)"));
  auto *text = new QPlainTextEdit(item.text); text->setObjectName("templateText"); text->setLineWrapMode(QPlainTextEdit::WidgetWidth);
  textLayout->addWidget(text); stack->addWidget(textPage);
  auto *filePage = new QWidget; auto *fileLayout = new QVBoxLayout(filePage); fileLayout->setContentsMargins(0, 0, 0, 0);
  auto *fileRow = new QHBoxLayout;
  auto *source = new QLineEdit(item.source); source->setObjectName("templateSource");
  auto *browse = new QPushButton("Browse…"); fileRow->addWidget(source, 1); fileRow->addWidget(browse); fileLayout->addLayout(fileRow);
  auto *hint = new QLabel("A copy of this file will be created with your chosen name. Keep the template file available. Its contents are never executed or changed.");
  hint->setWordWrap(true); fileLayout->addWidget(hint); fileLayout->addStretch(); stack->addWidget(filePage);
  stack->setCurrentIndex(kind->currentIndex());
  QObject::connect(kind, &QComboBox::currentIndexChanged, stack, &QStackedWidget::setCurrentIndex);
  QObject::connect(browse, &QPushButton::clicked, &dialog, [&] {
    const auto path = QFileDialog::getOpenFileName(&dialog, "Choose template file", source->text());
    if (!path.isEmpty()) { source->setText(path); if (filename->text().isEmpty()) filename->setText(QFileInfo(path).fileName()); }
  });
  auto *error = new QLabel; error->setWordWrap(true); layout->addWidget(error);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel); layout->addWidget(buttons);
  QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
    auto candidate = item; candidate.name = name->text().trimmed(); candidate.filename = filename->text();
    candidate.kind = kind->currentData().toString(); candidate.text = text->toPlainText(); candidate.source = source->text();
    QString problem = validate(candidate);
    if (problem.isEmpty() && candidate.kind == "file" && !QFileInfo(candidate.source).isFile()) problem = "The selected template file is unavailable.";
    if (!problem.isEmpty()) { error->setText(problem); return; }
    item = candidate; dialog.accept();
  });
  return dialog.exec() == QDialog::Accepted;
}
}

QString Fusion::templateSettingsPath() { return root() + "/file_manager/state/templates.json"; }
Fusion::TemplateCatalog Fusion::loadTemplates(const QString &path) {
  TemplateCatalog catalog;
  QFile file(path);
  if (!file.exists()) return catalog;
  if (!file.open(QIODevice::ReadOnly)) { catalog.error = file.errorString(); return catalog; }
  catalog.revision = file.readAll();
  QJsonParseError parse;
  const auto json = QJsonDocument::fromJson(catalog.revision, &parse);
  if (parse.error != QJsonParseError::NoError || !json.isObject() || json["version"].toInt() != 1 || !json["entries"].isArray()) {
    catalog.error = "The template settings could not be read. Your saved file has been kept."; return catalog;
  }
  QSet<QString> ids;
  for (const auto &value : json["entries"].toArray()) {
    const auto entry = value.toObject();
    NewItem item{entry["id"].toString(), entry["name"].toString(), entry["filename"].toString(),
                 entry["kind"].toString(), entry["text"].toString(), entry["source"].toString(), entry["enabled"].toBool(true)};
    catalog.error = validate(item);
    if (ids.contains(item.id)) catalog.error = "Template identities must be unique.";
    if (!catalog.error.isEmpty()) { catalog.entries.clear(); return catalog; }
    ids.insert(item.id); catalog.entries << item;
  }
  return catalog;
}
bool Fusion::saveTemplates(const TemplateCatalog &catalog, QString *error, const QString &path) {
  auto fail = [&](const QString &message) { if (error) *error = message; return false; };
  if (!catalog.error.isEmpty()) return fail(catalog.error);
  if (!QDir().mkpath(QFileInfo(path).absolutePath())) return fail("Could not create the template settings folder.");
  QLockFile lock(path + ".lock");
  if (!lock.tryLock(0)) return fail("Template settings are being saved in another window. Try again.");
  const auto current = loadTemplates(path);
  if (!current.error.isEmpty()) return fail(current.error);
  if (current.revision != catalog.revision) return fail("Templates changed in another window. Close and reopen Template Options before saving.");
  QJsonArray entries; QSet<QString> ids;
  for (const auto &item : catalog.entries) {
    const auto problem = validate(item);
    if (!problem.isEmpty()) return fail(problem);
    if (ids.contains(item.id)) return fail("Template identities must be unique.");
    ids.insert(item.id);
    entries.append(QJsonObject{{"id", item.id}, {"name", item.name}, {"filename", item.filename}, {"kind", item.kind},
                               {"text", item.text}, {"source", item.source}, {"enabled", item.enabled}});
  }
  QSaveFile file(path);
  const auto data = QJsonDocument(QJsonObject{{"version", 1}, {"entries", entries}}).toJson();
  if (!file.open(QIODevice::WriteOnly)) return fail(file.errorString());
  file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
  if (file.write(data) != data.size() || !file.commit()) return fail(file.errorString());
  return true;
}
QList<Fusion::NewItem> Fusion::newItems() {
  QList<NewItem> entries{{"folder", "Folder", "New folder", "folder", {}, {}, true},
                         {"text", "Text document", "New text document.txt", "text", {}, {}, true}};
  for (auto item : loadTemplates().entries) {
    if (!item.enabled) continue;
    if (item.kind == "file" && !QFileInfo(item.source).isFile()) item.enabled = false;
    entries << item;
  }
  return entries;
}
void Fusion::configureTemplates(QWidget *parent) {
  auto catalog = loadTemplates();
  QDialog dialog(parent); dialog.setObjectName("templateOptions"); dialog.setWindowTitle("Template Options"); dialog.resize(600, 460);
  auto *layout = new QVBoxLayout(&dialog);
  auto *heading = new QLabel("Your New menu"); heading->setObjectName("settingsHeading"); layout->addWidget(heading);
  auto *hint = new QLabel("Folder and Text document are always available. Add custom entries below; these settings apply to Fusion Files and the desktop.");
  hint->setWordWrap(true); layout->addWidget(hint);
  auto *list = new QListWidget; list->setObjectName("templateEntries"); layout->addWidget(list, 1);
  auto fill = [&](int selected) {
    list->clear();
    for (const auto &entry : catalog.entries) {
      auto *item = new QListWidgetItem(icon(entry.kind == "file" ? "document-new" : "text-x-generic"), entry.name + " · " + entry.filename, list);
      item->setCheckState(entry.enabled ? Qt::Checked : Qt::Unchecked);
    }
    list->setCurrentRow(selected);
  };
  auto sync = [&] { for (int i = 0; i < list->count(); ++i) catalog.entries[i].enabled = list->item(i)->checkState() == Qt::Checked; };
  fill(catalog.entries.isEmpty() ? -1 : 0);
  auto *row = new QHBoxLayout; layout->addLayout(row);
  auto button = [&](const QString &label, auto action) { auto *b = new QPushButton(label); row->addWidget(b); QObject::connect(b, &QPushButton::clicked, &dialog, action); return b; };
  button("Add…", [&] {
    sync(); NewItem entry{QUuid::createUuid().toString(QUuid::WithoutBraces), {}, {}, "text", {}, {}, true};
    if (editTemplate(entry, &dialog)) { catalog.entries << entry; fill(catalog.entries.size()-1); }
  });
  auto edit = [&] { sync(); const int i = list->currentRow(); if (i >= 0 && editTemplate(catalog.entries[i], &dialog)) fill(i); };
  button("Edit…", edit);
  QObject::connect(list, &QListWidget::itemDoubleClicked, &dialog, [&](QListWidgetItem *) { edit(); });
  button("Remove", [&] { sync(); int i = list->currentRow(); if (i >= 0) { catalog.entries.removeAt(i); fill(qMin(i, int(catalog.entries.size())-1)); } });
  button("Move up", [&] { sync(); int i = list->currentRow(); if (i > 0) { catalog.entries.swapItemsAt(i, i-1); fill(i-1); } });
  button("Move down", [&] { sync(); int i = list->currentRow(); if (i >= 0 && i+1 < catalog.entries.size()) { catalog.entries.swapItemsAt(i, i+1); fill(i+1); } });
  auto *error = new QLabel(catalog.error); error->setWordWrap(true); layout->addWidget(error);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel); layout->addWidget(buttons);
  buttons->button(QDialogButtonBox::Save)->setEnabled(catalog.error.isEmpty());
  QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
    sync(); QString problem;
    if (saveTemplates(catalog, &problem)) dialog.accept(); else error->setText(problem);
  });
  dialog.exec();
}
KIO::Job *Fusion::createNewItem(const NewItem &item, const QString &name, const QUrl &directory) {
  if (!item.enabled || !validName(name) || !fileDropDestination(directory)) return nullptr;
  auto destination = directory;
  destination.setPath(directory.path() + (directory.path().endsWith('/') ? "" : "/") + name);
  KIO::Job *job = nullptr;
  if (item.kind == "folder") job = KIO::mkdir(destination);
  else if (item.kind == "text") job = KIO::storedPut(item.text.toUtf8(), destination, -1, KIO::HideProgressInfo);
  else if (item.kind == "file" && QFileInfo(item.source).isFile())
    job = KIO::file_copy(QUrl::fromLocalFile(item.source), destination, -1, KIO::HideProgressInfo);
  if (!job) return nullptr;
  job->setUiDelegate(nullptr); // Callers display errors; never silently overwrite an existing item.
  KIO::FileUndoManager::self()->recordJob(item.kind == "folder" ? KIO::FileUndoManager::Mkdir : KIO::FileUndoManager::Put, {}, destination, job);
  return job;
}
bool Fusion::promptNewItem(const QString &id, const QUrl &directory, QWidget *parent, QObject *owner, const NewItemCallbacks &callbacks) {
  if (!fileDropDestination(directory)) return false;
  const auto entries = newItems();
  const auto found = std::find_if(entries.cbegin(), entries.cend(), [&](const auto &item) { return item.id == id; });
  if (found == entries.cend() || !found->enabled) return false;
  const auto item = *found;
  auto *dialog = new QInputDialog(parent); dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->setWindowTitle("New " + item.name); dialog->setLabelText(item.kind == "folder" ? "Folder name:" : "File name:");
  dialog->setTextValue(item.filename);
  QObject::connect(owner, &QObject::destroyed, dialog, &QObject::deleteLater);
  QObject::connect(dialog, &QDialog::rejected, owner, [callbacks] { if (callbacks.finished) callbacks.finished(); });
  QObject::connect(dialog, &QInputDialog::textValueSelected, owner, [=](const QString &name) {
    if (!validName(name)) {
      warning(parent, "Choose a name without /, and different from . or ..");
      if (callbacks.finished) callbacks.finished(); return;
    }
    auto destination = directory; destination.setPath(directory.path() + (directory.path().endsWith('/') ? "" : "/") + name);
    if (callbacks.target) callbacks.target(destination);
    auto *job = createNewItem(item, name, directory);
    if (!job) { warning(parent, "The template or destination is no longer available."); if (callbacks.finished) callbacks.finished(); return; }
    QObject::connect(job, &KJob::result, owner, [callbacks, destination](KJob *result) {
      if (!result->error() && callbacks.created) callbacks.created(destination);
      if (callbacks.finished) callbacks.finished();
    });
    if (callbacks.track) callbacks.track(job);
  });
  dialog->open();
  if (auto *edit = dialog->findChild<QLineEdit *>()) {
    const int dot = item.filename.lastIndexOf('.');
    edit->setSelection(0, item.kind != "folder" && dot > 0 ? dot : item.filename.size());
  }
  return true;
}
void Fusion::addNewMenu(QMenu *menu, const QUrl &directory, QWidget *parent, QObject *owner, const NewItemCallbacks &callbacks) {
  auto *submenu = menu->addMenu(icon("folder-new"), "New"); submenu->setObjectName("newMenu"); submenu->menuAction()->setObjectName("newFolder");
  submenu->setEnabled(fileDropDestination(directory));
  for (const auto &item : newItems()) {
    auto *action = submenu->addAction(icon(item.kind == "folder" ? "folder-new" : "text-x-generic"), QString(item.name).replace('&', "&&"));
    action->setObjectName("new:" + item.id); action->setEnabled(item.enabled);
    if (!item.enabled) action->setToolTip("The template file is unavailable. Update its path in Template Options.");
    QObject::connect(action, &QAction::triggered, owner, [=] { promptNewItem(item.id, directory, parent, owner, callbacks); });
  }
  submenu->addSeparator();
  submenu->addAction(icon("configure"), "Template Options…", owner, [parent] { configureTemplates(parent); });
}
