#include "picker.h"
#include <KWindowSystem>
#include <cstdio>

namespace {
QString memoryKey(const QJsonObject &request) {
  const auto identity = request.value("app_id").toString("unknown") + ':' +
                        request.value("method").toString("OpenFile") + ':' +
                        (request.value("directory").toBool() ? "folder" : "file");
  return "picker/" + QString::fromLatin1(QCryptographicHash::hash(identity.toUtf8(), QCryptographicHash::Sha256).toHex().left(24));
}
QUrl initialFolder(const QJsonObject &request, const QString &settingsPath) {
  Fusion::Preferences preferences(settingsPath);
  QStringList candidates{request.value("current_folder").toString()};
  if (!request.value("current_file").toString().isEmpty())
    candidates << QFileInfo(request.value("current_file").toString()).absolutePath();
  candidates << preferences.settings.value(memoryKey(request) + "/folder").toString() << QDir::homePath();
  for (const auto &path : candidates)
    if (!path.isEmpty() && QFileInfo(path).isDir()) return QUrl::fromLocalFile(path);
  return QUrl::fromLocalFile(QDir::rootPath());
}
QString label(QString text) {
  // Portal labels use GTK underscores; Qt uses ampersands for mnemonics.
  return text.replace('&', "&&").replace('_', '&');
}
QString globSuffix(const QString &pattern) {
  if (!pattern.startsWith("*.")) return {};
  QString suffix;
  for (int i = 2; i < pattern.size(); ++i) {
    auto letter = pattern.at(i);
    if (letter == '[') {
      // Chromium represents case-insensitive extensions as *.[pP][nN][gG].
      // Only collapse a class when every member names the same character;
      // a real choice/range such as [ab] or [0-9] has no unambiguous suffix.
      const int end = pattern.indexOf(']', i+1);
      if (end < i+2) return {};
      const auto alternatives = pattern.mid(i+1, end-i-1).toLower();
      letter = alternatives.front();
      for (auto alternative : alternatives) if (alternative != letter) return {};
      i = end;
    }
    if (!((letter >= 'a' && letter <= 'z') || (letter >= 'A' && letter <= 'Z') ||
          letter.isDigit() || letter == '.' || letter == '_' || letter == '-')) return {};
    suffix += letter;
  }
  return suffix;
}
}

PickerWindow::PickerWindow(const QJsonObject &value, const QString &settingsPath, bool scanDrives)
    : FilesWindow(initialFolder(value, settingsPath), scanDrives, settingsPath, memoryKey(value)+"/geometry"),
      request(value), key(memoryKey(value)),
      saving(value.value("method").toString() != "OpenFile"),
      directory(value.value("directory").toBool() || value.value("method").toString() == "SaveFiles"),
      multiple(value.value("multiple").toBool() && !saving) {
  preparePicker();
  setAttribute(Qt::WA_QuitOnClose);
  setProperty("xetalFilePicker", true);
  const auto title = value.value("title").toString(saving ? "Save file" : "Open file");
  auto setTitle = [this, title] { setWindowTitle(title + " — Fusion Files"); };
  connect(browser(), &Browser::locationChanged, this, setTitle);
  setTitle();
  if (!preferences.settings.contains(key+"/geometry")) resize(1080, 700);
  auto *panel = new QFrame;
  panel->setObjectName("pickerActions");
  // This is a form footer, not a second pane. Keep its natural themed height
  // as the window grows; the folder view receives the additional space.
  panel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
  auto *layout = new QGridLayout(panel);
  layout->setContentsMargins(18, 14, 18, 16);
  layout->setHorizontalSpacing(12);
  layout->setVerticalSpacing(10);
  name = new QLineEdit;
  name->setObjectName("pickerName");
  name->setClearButtonEnabled(true);
  name->setPlaceholderText(directory ? "Select a folder, or use the current folder" : "File name or full path…");
  name->setText(value.value("current_name").toString());
  if (name->text().isEmpty() && !value.value("current_file").toString().isEmpty())
    name->setText(QFileInfo(value.value("current_file").toString()).fileName());
  auto *nameLabel = new QLabel(directory ? "&Folder" : "File &name");
  nameLabel->setBuddy(name);
  layout->addWidget(nameLabel, 0, 0);
  layout->addWidget(name, 0, 1, 1, 3);
  types = new QComboBox;
  types->setObjectName("pickerFileType");
  filters = value.value("filters").toArray();
  int selected = 0;
  for (const auto &entry : filters) {
    const auto pair = entry.toArray();
    types->addItem(pair.at(0).toString());
    if (entry == value.value("current_filter")) selected = types->count()-1;
  }
  if (filters.isEmpty()) types->addItem("All files");
  types->setCurrentIndex(selected);
  types->setVisible(!directory);
  auto *typeLabel = new QLabel("File &type");
  typeLabel->setBuddy(types);
  typeLabel->setVisible(!directory);
  layout->addWidget(typeLabel, 1, 0);
  layout->addWidget(types, 1, 1, 1, 3);
  auto filterChanged = [this] {
    browser()->setPickerFilter((filters.isEmpty() ? QJsonArray{} : filters.at(types->currentIndex()).toArray().at(1).toArray()), directory);
  };
  connect(types, &QComboBox::currentIndexChanged, this, filterChanged);
  filterChanged();
  int row = 2;
  for (const auto &entry : value.value("choices").toArray()) {
    const auto choice = entry.toArray();
    if (choice.size() != 4) continue;
    const QString id = choice[0].toString();
    if (choice[2].toArray().isEmpty()) {
      auto *check = new QCheckBox(label(choice[1].toString()));
      check->setChecked(choice[3].toString() == "true");
      layout->addWidget(check, row++, 1, 1, 3);
      choices.append({id, check});
    } else {
      auto *combo = new QComboBox;
      for (const auto &option : choice[2].toArray()) {
        const auto pair = option.toArray();
        combo->addItem(pair.at(1).toString(), pair.at(0).toString());
      }
      const int index = combo->findData(choice[3].toString());
      if (index >= 0) combo->setCurrentIndex(index);
      auto *caption = new QLabel(label(choice[1].toString()));
      caption->setBuddy(combo);
      layout->addWidget(caption, row, 0);
      layout->addWidget(combo, row++, 1, 1, 3);
      choices.append({id, combo});
    }
  }
  auto *hint = new QLabel("Fusion Files · " + QString(saving ? "Choose where to save" : directory ? "Choose a folder" : "Choose files to open"));
  hint->setObjectName("muted");
  layout->addWidget(hint, row, 0, 1, 2);
  auto *cancel = new QPushButton("Cancel");
  cancel->setObjectName("pickerCancel");
  auto *accept = new QPushButton(label(value.value("accept_label").toString(saving ? "Save" : directory ? "Select folder" : "Open")));
  accept->setObjectName("pickerAccept");
  accept->setDefault(true);
  accept->setMinimumWidth(110);
  layout->addWidget(cancel, row, 2);
  layout->addWidget(accept, row, 3);
  layout->setColumnStretch(1, 1);
  auto *content = qobject_cast<QVBoxLayout *>(centralWidget()->layout());
  content->setStretch(0, 1);
  content->addWidget(panel, 0);
  // Some Wayland clients retain a stale normalGeometry after a compositor
  // resize. Save the actual content size as well, independent of maximize bits.
  const QSize savedSize = preferences.settings.value(key+"/size").toSize();
  setWindowState(Qt::WindowNoState);
  if (savedSize.isValid() && savedSize.width() <= 32768 && savedSize.height() <= 32768)
    resize(savedSize.expandedTo(minimumSize()));
  for (auto *view : {static_cast<QAbstractItemView *>(browser()->icons), static_cast<QAbstractItemView *>(browser()->details)})
    view->setSelectionMode(multiple ? QAbstractItemView::ExtendedSelection : QAbstractItemView::SingleSelection);
  connect(cancel, &QPushButton::clicked, this, &QWidget::close);
  connect(accept, &QPushButton::clicked, this, &PickerWindow::acceptSelection);
  connect(name, &QLineEdit::returnPressed, this, &PickerWindow::acceptSelection);
  connect(new QShortcut(QKeySequence(Qt::Key_Escape), this), &QShortcut::activated, this, &QWidget::close);
  connect(browser(), &Browser::selectionChanged, this, [this] {
    const auto items = browser()->selectedItems();
    if (items.size() == 1 && (directory || !items.first().isDir())) name->setText(items.first().name());
    else if (!saving) name->setText({});
  });
  connect(browser(), &Browser::locationChanged, this, [this] { if (!saving || directory) name->setText({}); });
  if (saving || !name->text().isEmpty()) { name->setFocus(); name->selectAll(); }
  else browser()->view()->setFocus();
}

void PickerWindow::openItem(const KFileItem &item, bool) {
  if (item.isNull()) return;
  if (item.isDir()) { openLocation(item.url()); return; }
  name->setText(item.name());
  acceptSelection(); // Selecting executables never runs them in a picker.
}

void PickerWindow::fail(const QString &text) {
  browser()->notice->setText(text);
  browser()->notice->show();
}

QString PickerWindow::withExtension(const QString &path) const {
  if (!request.value("add_extension").toBool(true)) return path;
  const QString filename = QFileInfo(path).fileName();
  const auto patterns = (filters.isEmpty() ? QJsonArray{} : filters.at(types->currentIndex()).toArray().at(1).toArray());
  QStringList suffixes;
  for (const auto &entry : patterns) {
    const auto pair = entry.toArray();
    const QString pattern = pair.at(1).toString();
    if (pair.at(0).toInt() == 0) {
      // Accept every alternative in the chosen filter, including upper-case
      // extensions and "All files". A different suffix is part of the name.
      if (QRegularExpression(QRegularExpression::wildcardToRegularExpression(pattern),
                             QRegularExpression::CaseInsensitiveOption).match(filename).hasMatch()) return path;
      const auto suffix = globSuffix(pattern);
      if (!suffix.isEmpty()) suffixes << suffix;
    } else if (pair.at(0).toInt() == 1) {
      const auto type = QMimeDatabase().mimeTypeForName(pattern);
      if (!type.preferredSuffix().isEmpty()) suffixes << type.preferredSuffix();
      suffixes << type.suffixes();
    }
  }
  if (suffixes.isEmpty()) {
    QString fallback = request.value("default_suffix").toString();
    if (fallback.startsWith('.')) fallback.remove(0, 1);
    if (QRegularExpression("^[A-Za-z0-9._-]+$").match(fallback).hasMatch()) suffixes << fallback;
  }
  for (const auto &suffix : suffixes)
    if (filename.endsWith('.' + suffix, Qt::CaseInsensitive)) return path;
  return suffixes.isEmpty() ? path : path + '.' + suffixes.first();
}

void PickerWindow::acceptSelection() {
  const auto location = browser()->location();
  if (!location.isLocalFile()) { fail("Choose a local folder or a mounted drive first."); return; }
  QList<QUrl> urls;
  const QString typed = name->text();
  const auto selected = browser()->selectedUrls();
  if (!saving && !selected.isEmpty() && !name->isModified()) urls = selected;
  else if (!typed.isEmpty()) urls << Fusion::userUrl(typed, location);
  else if (directory) urls << location;
  if (urls.isEmpty()) { fail(directory ? "Choose a folder." : "Enter a file name or select a file."); return; }
  if (!multiple && urls.size() > 1) urls = {urls.first()};
  for (auto &url : urls) {
    if (!url.isLocalFile()) { fail("This application needs a local file. Mount the network location first."); return; }
    QFileInfo info(url.toLocalFile());
    if (info.isDir() && !directory) { openLocation(url); return; }
    if (directory && !info.isDir()) { fail("Select an existing folder."); return; }
    if (!saving && !info.exists()) { fail("This file no longer exists. Choose another file."); return; }
    if (saving && !directory) {
      url = QUrl::fromLocalFile(withExtension(info.absoluteFilePath()));
      info.setFile(url.toLocalFile());
      if (!QFileInfo(info.absolutePath()).isDir() || info.isDir()) { fail("Choose an existing folder and a file name."); return; }
      if (info.exists() && !request.value("dont_confirm_overwrite").toBool() &&
          QMessageBox::question(this, "Replace file?", "“" + info.fileName() + "” already exists. Replace it?",
                                QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
    }
  }
  if (request.value("method").toString() == "SaveFiles") {
    const QDir destination(urls.first().toLocalFile());
    urls.clear();
    QSet<QString> reserved;
    for (const auto &value : request.value("files").toArray()) {
      const QString original = QFileInfo(value.toString()).fileName();
      if (original.isEmpty() || original == "." || original == "..") { fail("The application supplied an invalid file name."); return; }
      QString filename = original;
      for (int n = 1; destination.exists(filename) || reserved.contains(filename); ++n) {
        const QFileInfo info(original);
        filename = info.completeBaseName() + "_copy" + QString::number(n) + (info.suffix().isEmpty() ? "" : '.' + info.suffix());
      }
      reserved.insert(filename);
      urls << QUrl::fromLocalFile(destination.filePath(filename));
    }
    if (urls.isEmpty()) { fail("The application did not supply any files to save."); return; }
  }
  finish(urls);
}

void PickerWindow::finish(const QList<QUrl> &urls) {
  QJsonArray uris;
  for (const auto &url : urls) uris.append(url.toString(QUrl::FullyEncoded));
  QJsonArray selectedChoices;
  for (const auto &choice : choices) {
    QString value;
    if (auto *check = qobject_cast<QCheckBox *>(choice.second)) value = check->isChecked() ? "true" : "false";
    else value = static_cast<QComboBox *>(choice.second)->currentData().toString();
    selectedChoices.append(QJsonArray{choice.first, value});
  }
  QJsonObject result{{"response", 0}, {"uris", uris}, {"choices", selectedChoices}};
  if (!filters.isEmpty()) result["current_filter"] = filters.at(types->currentIndex());
  completed = true;
  // closeEvent saves geometry before the response is delivered to a caller.
  close();
  emit finished(result);
}

void PickerWindow::closeEvent(QCloseEvent *event) {
  preferences.settings.setValue(key+"/size", size());
  if (browser()->location().isLocalFile()) preferences.settings.setValue(key+"/folder", browser()->location().toLocalFile());
  FilesWindow::closeEvent(event);
  if (!completed) { completed = true; emit finished({{"response", 1}}); }
}

int runPicker(QApplication &app) {
  QFile input;
  if (!input.open(stdin, QIODevice::ReadOnly)) return 2;
  const auto bytes = input.readLine(1024*1024);
  QJsonParseError error;
  const auto document = QJsonDocument::fromJson(bytes, &error);
  if (error.error != QJsonParseError::NoError || !document.isObject()) return 2;
  app.setDesktopFileName("xetal-file-picker-" + memoryKey(document.object()).section('/', -1));
  auto *picker = new PickerWindow(document.object());
  picker->winId();
  const auto parent = document.object().value("parent_window").toString();
  if (!parent.isEmpty()) KWindowSystem::setMainWindow(picker->windowHandle(), parent);
  QObject::connect(picker, &PickerWindow::finished, &app, [](const QJsonObject &result) {
    const auto output = QJsonDocument(result).toJson(QJsonDocument::Compact) + '\n';
    std::fwrite(output.constData(), 1, output.size(), stdout);
    std::fflush(stdout);
  });
  picker->show();
  return app.exec();
}
