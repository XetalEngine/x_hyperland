#include "search.h"
#include "core.h"
#include "search_presets.h"
#include <QDesktopServices>
#include <QSaveFile>
#include <QStandardPaths>
#include <csignal>
#include <unistd.h>

int SearchResults::rowCount(const QModelIndex &parent) const {
  return parent.isValid() ? 0 : rows.size();
}
int SearchResults::columnCount(const QModelIndex &parent) const {
  return parent.isValid() ? 0 : 7;
}
QJsonObject SearchResults::result(int row) const {
  return row >= 0 && row < rows.size() ? rows[row] : QJsonObject{};
}
QVariant SearchResults::headerData(int section, Qt::Orientation orientation,
                                   int role) const {
  if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
    return {};
  return QStringList{"Name",     "Size",      "Line",         "Matches",
                     "Modified", "Full path", "Matching text"}
      .value(section);
}
QVariant SearchResults::data(const QModelIndex &index, int role) const {
  if (!index.isValid() || index.row() >= rows.size())
    return {};
  const auto row = rows[index.row()];
  if (role == Qt::DecorationRole && index.column() == 0)
    return Fusion::icon(row["directory"].toBool() ? "folder"
                                                  : "text-x-generic");
  if (role == Qt::TextAlignmentRole && index.column() >= 1 &&
      index.column() <= 3)
    return int(Qt::AlignRight | Qt::AlignVCenter);
  if (role != Qt::DisplayRole && role != Qt::ToolTipRole &&
      role != Qt::UserRole)
    return {};
  switch (index.column()) {
  case 0:
    return row["name"].toString();
  case 1:
    return role == Qt::UserRole ? QVariant(row["size"].toInteger())
                                : QVariant(row["directory"].toBool()
                                               ? QString("Folder")
                                               : QLocale().formattedDataSize(
                                                     row["size"].toInteger()));
  case 2:
    return role == Qt::UserRole
               ? QVariant(row["line"].toInteger())
               : QVariant(row["line"].toInteger()
                              ? QString::number(row["line"].toInteger())
                              : QString());
  case 3:
    return role == Qt::UserRole
               ? QVariant(row["matches"].toInteger())
               : QVariant(row["matches"].toInteger()
                              ? QString::number(row["matches"].toInteger())
                              : QString());
  case 4:
    return role == Qt::UserRole
               ? QVariant(row["modified"].toInteger())
               : QVariant(QLocale().toString(
                     QDateTime::fromSecsSinceEpoch(row["modified"].toInteger()),
                     QLocale::ShortFormat));
  case 5:
    return row["path"].toString();
  case 6:
    return row["preview"].toString();
  }
  return {};
}
void SearchResults::append(const QJsonArray &batch) {
  if (batch.isEmpty())
    return;
  beginInsertRows({}, rows.size(), rows.size() + batch.size() - 1);
  for (const auto &item : batch)
    rows.append(item.toObject());
  endInsertRows();
}
void SearchResults::clear() {
  beginResetModel();
  rows.clear();
  endResetModel();
}

SearchPane::SearchPane(QWidget *parent) : QWidget(parent) {
  setObjectName("searchPane");
  options = FusionSearch::defaults();
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(12, 10, 12, 10);
  layout->setSpacing(9);
  auto *bar = new QFrame;
  bar->setObjectName("searchBar");
  auto *row = new QHBoxLayout(bar);
  row->setContentsMargins(10, 8, 10, 8);
  auto *symbol = new QLabel;
  symbol->setPixmap(Fusion::icon("edit-find").pixmap(22, 22));
  row->addWidget(symbol);
  query = new QLineEdit;
  query->setObjectName("fileSearchQuery");
  query->setAccessibleName("Search files");
  query->setClearButtonEnabled(true);
  row->addWidget(query, 1);
  advanced = new QCheckBox("Advanced");
  advanced->setObjectName("advancedSearch");
  row->addWidget(advanced);
  settingsButton = new QPushButton("Options…");
  settingsButton->setObjectName("searchOptions");
  row->addWidget(settingsButton);
  searchButton = new QPushButton("Search");
  searchButton->setObjectName("searchStart");
  row->addWidget(searchButton);
  auto *close = new QToolButton;
  close->setText("×");
  close->setToolTip("Close search · Escape");
  close->setAccessibleName("Close search");
  row->addWidget(close);
  layout->addWidget(bar);
  scope = new QLabel;
  scope->setObjectName("searchScope");
  scope->setTextFormat(Qt::PlainText);
  scope->setWordWrap(true);
  auto *scopeRow = new QHBoxLayout;
  scopeRow->addWidget(scope, 1);
  auto *folder = new QPushButton("Choose folder…");
  scopeRow->addWidget(folder);
  layout->addLayout(scopeRow);
  hint = new QLabel;
  hint->setObjectName("muted");
  hint->setTextFormat(Qt::PlainText);
  hint->setWordWrap(true);
  layout->addWidget(hint);
  pages = new QStackedWidget;
  layout->addWidget(pages, 1);
  empty = new QLabel("Find something beyond this folder.\nEnter a name or "
                     "wildcard, then press Enter.");
  empty->setObjectName("searchEmpty");
  empty->setAlignment(Qt::AlignCenter);
  empty->setWordWrap(true);
  empty->setTextFormat(Qt::PlainText);
  pages->addWidget(empty);
  results = new QTreeView;
  results->setObjectName("searchResults");
  results->setAccessibleName("Search results");
  results->setRootIsDecorated(false);
  results->setUniformRowHeights(true);
  results->setAlternatingRowColors(true);
  results->setSelectionMode(QAbstractItemView::ExtendedSelection);
  results->setSelectionBehavior(QAbstractItemView::SelectRows);
  results->setEditTriggers(QAbstractItemView::NoEditTriggers);
  results->setContextMenuPolicy(Qt::CustomContextMenu);
  model = new SearchResults(this);
  proxy = new QSortFilterProxyModel(this);
  proxy->setSourceModel(model);
  proxy->setSortRole(Qt::UserRole);
  proxy->setDynamicSortFilter(false);
  results->setModel(proxy);
  const QList<int> widths{210, 90, 65, 80, 155, 330, 350};
  for (int i = 0; i < widths.size(); ++i)
    results->setColumnWidth(i, widths[i]);
  results->header()->setStretchLastSection(true);
  pages->addWidget(results);
  auto *actions = new QHBoxLayout;
  auto *open = new QPushButton("Open file");
  auto *reveal = new QPushButton("Show in folder");
  auto *copy = new QPushButton("Copy paths");
  exportButton = new QPushButton("Export CSV…");
  for (auto *button : {open, reveal, copy}) {
    button->setEnabled(false);
    actions->addWidget(button);
  }
  actions->addStretch();
  actions->addWidget(exportButton);
  exportButton->setEnabled(false);
  layout->addLayout(actions);
  connect(results->selectionModel(), &QItemSelectionModel::selectionChanged,
          this, [this, open, reveal, copy] {
            const bool selected = !selectedUrls().isEmpty();
            for (auto *button : {open, reveal, copy})
              button->setEnabled(selected);
            emit selectionChanged();
          });
  progress = new QProgressBar;
  progress->setRange(0, 0);
  progress->setFixedHeight(4);
  progress->setTextVisible(false);
  progress->hide();
  layout->addWidget(progress);
  auto *footer = new QHBoxLayout;
  status = new QLabel("Ready");
  status->setObjectName("searchStatus");
  status->setTextFormat(Qt::PlainText);
  status->setWordWrap(true);
  footer->addWidget(status, 1);
  stopButton = new QPushButton("Stop");
  stopButton->setObjectName("searchStop");
  stopButton->setEnabled(false);
  footer->addWidget(stopButton);
  layout->addLayout(footer);
  connect(query, &QLineEdit::returnPressed, this, &SearchPane::start);
  connect(searchButton, &QPushButton::clicked, this, &SearchPane::start);
  connect(stopButton, &QPushButton::clicked, this, &SearchPane::cancel);
  connect(close, &QToolButton::clicked, this, &SearchPane::closeRequested);
  connect(settingsButton, &QPushButton::clicked, this,
          &SearchPane::advancedDialog);
  connect(advanced, &QCheckBox::toggled, this, [this](bool on) {
    if (on)
      advancedDialog();
    else
      updateMode();
  });
  connect(folder, &QPushButton::clicked, this, [this] {
    const auto path = QFileDialog::getExistingDirectory(
        this, "Search in folder", options["root"].toString());
    if (!path.isEmpty()) {
      setLocation(QUrl::fromLocalFile(path));
      focusQuery();
    }
  });
  connect(open, &QPushButton::clicked, this, [this] { openResult(); });
  connect(reveal, &QPushButton::clicked, this, &SearchPane::revealResult);
  connect(copy, &QPushButton::clicked, this, [this] { copyResults(true); });
  connect(exportButton, &QPushButton::clicked, this,
          &SearchPane::exportResults);
  connect(results, &QTreeView::doubleClicked, this,
          [this] { openResult(true); });
  connect(results, &QTreeView::customContextMenuRequested, this,
          [this](const QPoint &point) {
            if (!results->indexAt(point).isValid())
              return;
            QMenu menu(this);
            menu.addAction("Open file", this, [this] { openResult(); });
            if (currentResult()["line"].toInt())
              menu.addAction("Preview matching text", this,
                             [this] { openResult(true); });
            menu.addAction("Show in folder", this, &SearchPane::revealResult);
            menu.addSeparator();
            menu.addAction("Copy full paths", this,
                           [this] { copyResults(true); });
            menu.addAction("Copy result rows", this,
                           [this] { copyResults(false); });
            menu.exec(results->viewport()->mapToGlobal(point));
          });
  auto *escape = new QShortcut(QKeySequence(Qt::Key_Escape), this);
  escape->setContext(Qt::WidgetWithChildrenShortcut);
  connect(escape, &QShortcut::activated, this, [this] {
    if (running())
      cancel();
    else
      emit closeRequested();
  });
  updateMode();
}
SearchPane::~SearchPane() { stopProcess(); }
void SearchPane::setLocation(const QUrl &url) {
  const auto path = url.isLocalFile() ? url.toLocalFile() : QString();
  if (options["root"].toString() != path) {
    cancel();
    model->clear();
    exportButton->setEnabled(false);
    pages->setCurrentWidget(empty);
    empty->setText("Enter a name or wildcard, then press Enter.\nSearch starts "
                   "in the folder above.");
    status->setText("Ready");
    status->setToolTip({});
  }
  options["root"] = path;
  updateMode();
}
void SearchPane::focusQuery() {
  query->setFocus(Qt::ShortcutFocusReason);
  query->selectAll();
}
void SearchPane::updateMode() {
  const bool contents = advanced->isChecked() && options["contents"].toBool();
  settingsButton->setVisible(advanced->isChecked());
  query->setPlaceholderText(
      contents ? "Find text inside files…"
               : "Search names…  *.jpg  ·  par*ialname*png  ·  *.");
  scope->setText(options["root"].toString().isEmpty()
                     ? "Choose a local or mounted folder to begin."
                     : "Search in: " + options["root"].toString());
  hint->setText(
      contents
          ? "Search file contents · " +
                QString(options["regex"].toBool() ? "Regular expression"
                                                  : "Text") +
                " · File names: " + options["names"].toString("*")
          : "Names and wildcards · Includes subfolders by default · Separate "
            "patterns with ; · *. finds names without an extension");
}

void SearchPane::advancedDialog() {
  QDialog dialog(this);
  dialog.setObjectName("advancedSearchDialog");
  dialog.setWindowTitle("Advanced search — Fusion Files");
  dialog.resize(850, 800);
  auto *outer = new QVBoxLayout(&dialog);
  auto *heading = new QLabel("Find exactly what you need");
  heading->setObjectName("settingsHeading");
  outer->addWidget(heading);
  SearchPresets presets(Fusion::root() + "/file_manager/state/search-presets",
                        &dialog);
  auto *presetBar = new QFrame;
  presetBar->setObjectName("searchPresetBar");
  auto *presetRow = new QHBoxLayout(presetBar);
  presetRow->setContentsMargins(10, 8, 10, 8);
  presetRow->addWidget(new QLabel("Presets"));
  auto *presetList = new QComboBox;
  presetList->setObjectName("searchPresetList");
  presetList->setMinimumContentsLength(16);
  presetList->setSizeAdjustPolicy(
      QComboBox::AdjustToMinimumContentsLengthWithIcon);
  presetRow->addWidget(presetList, 1);
  auto *loadPreset = new QPushButton("Load");
  loadPreset->setObjectName("loadSearchPreset");
  auto *savePreset = new QPushButton("Save…");
  savePreset->setObjectName("saveSearchPreset");
  auto *loadFile = new QPushButton("Load file…");
  loadFile->setObjectName("loadSearchPresetFile");
  auto *presetFolder = new QPushButton("Open folder");
  presetFolder->setToolTip(presets.directory());
  for (auto *button : {loadPreset, savePreset, loadFile, presetFolder})
    presetRow->addWidget(button);
  outer->addWidget(presetBar);
  auto *presetNote = new QLabel(
      "Choose a preset, then Load. Open folder to rename or delete presets.");
  presetNote->setObjectName("searchPresetStatus");
  presetNote->setTextFormat(Qt::PlainText);
  presetNote->setWordWrap(true);
  outer->addWidget(presetNote);
  auto *scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  auto *body = new QWidget;
  auto *form = new QFormLayout(body);
  form->setSpacing(11);
  scroll->setWidget(body);
  outer->addWidget(scroll, 1);
  auto *root = new QLineEdit(options["root"].toString());
  root->setObjectName("searchRoot");
  auto *rootRow = new QHBoxLayout;
  rootRow->addWidget(root, 1);
  auto *browse = new QPushButton("Browse…");
  rootRow->addWidget(browse);
  form->addRow("Search in", rootRow);
  connect(browse, &QPushButton::clicked, &dialog, [&] {
    auto path = QFileDialog::getExistingDirectory(&dialog, "Search in folder",
                                                  root->text());
    if (!path.isEmpty())
      root->setText(path);
  });
  auto *term = new QLineEdit(query->text());
  term->setObjectName("advancedQuery");
  form->addRow("Search for", term);
  auto *contents = new QCheckBox("Search text inside files");
  contents->setObjectName("searchContents");
  contents->setChecked(options["contents"].toBool());
  form->addRow(contents);
  auto *mode = new QComboBox;
  mode->setObjectName("contentMatchMode");
  mode->addItems({"Text", "Regular expression"});
  mode->setCurrentIndex(options["regex"].toBool() ? 1 : 0);
  form->addRow("Content matching", mode);
  mode->setToolTip("Fast ripgrep regular expressions. Look-around and "
                   "backreferences are not supported.");
  auto *names = new QLineEdit(options["names"].toString("*"));
  names->setObjectName("searchNamePatterns");
  names->setPlaceholderText("*.txt;*.cpp;README*");
  form->addRow("File names", names);
  auto *typesBox = new QGroupBox("Common text file types");
  typesBox->setObjectName("searchTypesBox");
  auto *typeGrid = new QGridLayout(typesBox);
  const QList<QStringList> groups{
      {"Text && notes", "*.txt;*.md;*.rst;*.adoc;*.log"},
      {"Source code", "*.c;*.cpp;*.cc;*.h;*.hpp;*.py;*.rs;*.go;*.java;*.cs;*."
                      "sh;*.rb;*.swift;*.kt"},
      {"Web", "*.html;*.htm;*.css;*.scss;*.js;*.jsx;*.ts;*.tsx;*.vue;*.php"},
      {"Configuration",
       "*.conf;*.ini;*.cfg;*.toml;*.yaml;*.yml;*.json;*.xml;*.desktop"},
      {"Data && logs", "*.csv;*.tsv;*.sql;*.log;*.jsonl"}};
  QList<QCheckBox *> types;
  QList<QStringList> groupExtensions;
  for (int i = 0; i < groups.size(); ++i) {
    auto *check = new QCheckBox(groups[i][0]);
    check->setObjectName("searchTypeGroup" + QString::number(i));
    QStringList values;
    FusionSearch::extensions(groups[i][1], &values, nullptr);
    groupExtensions << values;
    check->setToolTip(values.join(", "));
    typeGrid->addWidget(check, i / 2, i % 2);
    types << check;
  }
  auto *extensions = new QPlainTextEdit;
  extensions->setObjectName("searchExtensions");
  extensions->setAccessibleName("File extensions");
  extensions->setPlaceholderText(".txt, .html, .cpp, .py…");
  extensions->setLineWrapMode(QPlainTextEdit::WidgetWidth);
  extensions->setWordWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);
  extensions->setTabChangesFocus(true);
  extensions->setMinimumHeight(80);
  extensions->setMaximumHeight(120);
  extensions->setPlainText(
      FusionSearch::extensionText(options["types"].toString()));
  typeGrid->addWidget(extensions, 3, 0, 1, 2);
  auto *extensionHint = new QLabel;
  extensionHint->setObjectName("muted");
  extensionHint->setWordWrap(true);
  extensionHint->setTextFormat(Qt::PlainText);
  typeGrid->addWidget(extensionHint, 4, 0, 1, 2);
  auto syncTypes = [&] {
    QStringList values;
    QString message;
    const bool valid =
        FusionSearch::extensions(extensions->toPlainText(), &values, &message);
    extensionHint->setText(valid ? "Edit extensions separated by commas. An "
                                   "empty list searches all file types."
                                 : message);
    if (!valid)
      return;
    for (int i = 0; i < types.size(); ++i) {
      QSignalBlocker blocker(types[i]);
      types[i]->setChecked(std::all_of(
          groupExtensions[i].cbegin(), groupExtensions[i].cend(),
          [&](const QString &value) { return values.contains(value); }));
    }
  };
  connect(extensions, &QPlainTextEdit::textChanged, &dialog, syncTypes);
  for (int i = 0; i < types.size(); ++i)
    connect(types[i], &QCheckBox::toggled, &dialog, [&, i](bool checked) {
      QStringList values;
      QString message;
      if (!FusionSearch::extensions(extensions->toPlainText(), &values,
                                    &message)) {
        QSignalBlocker blocker(types[i]);
        types[i]->setChecked(!checked);
        extensionHint->setText(message);
        return;
      }
      for (const auto &value : groupExtensions[i]) {
        if (checked) {
          if (!values.contains(value))
            values << value;
        } else {
          bool shared = false;
          for (int j = 0; j < types.size(); ++j)
            shared |= j != i && types[j]->isChecked() &&
                      groupExtensions[j].contains(value);
          if (!shared)
            values.removeAll(value);
        }
      }
      extensions->setPlainText(values.join(", "));
      syncTypes();
    });
  syncTypes();
  form->addRow(typesBox);
  auto *exclude = new QLineEdit(options["exclude"].toString());
  exclude->setObjectName("searchExclusions");
  exclude->setPlaceholderText(".git;node_modules;build;*.bak");
  form->addRow("Exclude names / folders", exclude);
  auto *toggles = new QWidget;
  auto *checks = new QGridLayout(toggles);
  checks->setContentsMargins(0, 0, 0, 0);
  QMap<QString, QCheckBox *> flags;
  const QList<QStringList> definitions{
      {"recursive", "Include subfolders"}, {"hidden", "Include hidden files"},
      {"case", "Case sensitive"},          {"word", "Whole words"},
      {"follow", "Follow symbolic links"}, {"binary", "Include binary data"},
      {"multiline", "Match across lines"}, {"folders", "Include folder names"}};
  for (int i = 0; i < definitions.size(); ++i) {
    auto *check = new QCheckBox(definitions[i][1]);
    const auto key = definitions[i][0];
    check->setObjectName("searchFlag_" + key);
    check->setChecked(
        options[key].toBool(key == "recursive" || key == "folders"));
    flags[key] = check;
    checks->addWidget(check, i / 2, i % 2);
  }
  form->addRow(toggles);
  auto *sizes = new QHBoxLayout;
  auto *minimum = new QSpinBox;
  auto *maximum = new QSpinBox;
  minimum->setObjectName("searchMinimumSize");
  maximum->setObjectName("searchMaximumSize");
  for (auto *spin : {minimum, maximum}) {
    spin->setRange(0, 1048576);
    spin->setSuffix(" MiB");
  }
  minimum->setSpecialValueText("No minimum");
  maximum->setSpecialValueText("No maximum");
  minimum->setValue(options["min_size"].toInteger() / 1048576);
  maximum->setValue(options["max_size"].toInteger() / 1048576);
  sizes->addWidget(minimum);
  sizes->addWidget(new QLabel("to"));
  sizes->addWidget(maximum);
  form->addRow("File size", sizes);
  auto *dates = new QHBoxLayout;
  auto *after = new QCheckBox("From");
  auto *before = new QCheckBox("Through");
  auto *from = new QDateEdit;
  auto *to = new QDateEdit;
  after->setObjectName("searchAfterEnabled");
  before->setObjectName("searchBeforeEnabled");
  from->setObjectName("searchAfterDate");
  to->setObjectName("searchBeforeDate");
  for (auto *date : {from, to}) {
    date->setCalendarPopup(true);
    date->setDate(QDate::currentDate());
    date->setDisplayFormat("yyyy-MM-dd");
  }
  after->setChecked(options["after"].toInteger() > 0);
  before->setChecked(options["before"].toInteger() > 0);
  if (after->isChecked())
    from->setDate(
        QDateTime::fromSecsSinceEpoch(options["after"].toInteger()).date());
  if (before->isChecked())
    to->setDate(QDateTime::fromSecsSinceEpoch(options["before"].toInteger())
                    .date()
                    .addDays(-1));
  from->setEnabled(after->isChecked());
  to->setEnabled(before->isChecked());
  connect(after, &QCheckBox::toggled, from, &QDateEdit::setEnabled);
  connect(before, &QCheckBox::toggled, to, &QDateEdit::setEnabled);
  dates->addWidget(after);
  dates->addWidget(from);
  dates->addWidget(before);
  dates->addWidget(to);
  form->addRow("Modified", dates);
  auto *encoding = new QComboBox;
  encoding->setObjectName("searchEncoding");
  for (const auto &entry :
       QList<QStringList>{{"Automatic (UTF-8 / Unicode BOM)", "auto"},
                          {"UTF-8", "utf-8"},
                          {"UTF-16 little endian", "utf-16le"},
                          {"UTF-16 big endian", "utf-16be"},
                          {"Windows-1252", "windows-1252"}})
    encoding->addItem(entry[0], entry[1]);
  encoding->setCurrentIndex(
      qMax(0, encoding->findData(options["encoding"].toString("auto"))));
  form->addRow("Text encoding", encoding);
  auto *workers = new QSpinBox;
  workers->setObjectName("searchWorkers");
  workers->setRange(0, 32);
  workers->setSpecialValueText("Automatic (up to 4)");
  workers->setValue(options["workers"].toInt());
  form->addRow("Parallel workers", workers);
  workers->setToolTip("Independent readers share a bounded queue. Try fewer "
                      "workers for a hard drive or a network mount.");
  auto *limit = new QSpinBox;
  limit->setObjectName("searchResultLimit");
  limit->setRange(1, 100000);
  limit->setValue(options["limit"].toInt(20000));
  form->addRow("Maximum result rows", limit);
  auto *note = new QLabel(
      "Content results show one row per matching line. PDF, Office and archive "
      "contents are not extracted. Searches never modify files.");
  note->setObjectName("muted");
  note->setWordWrap(true);
  form->addRow(note);
  auto update = [&] {
    const bool on = contents->isChecked();
    mode->setEnabled(on);
    names->setEnabled(on);
    encoding->setEnabled(on);
    for (const auto &key : {"word", "binary", "multiline"})
      flags[key]->setEnabled(on);
    flags["folders"]->setEnabled(!on);
  };
  connect(contents, &QCheckBox::toggled, &dialog, update);
  update();
  auto *error = new QLabel;
  error->setObjectName("searchValidation");
  error->setTextFormat(Qt::PlainText);
  error->setWordWrap(true);
  outer->addWidget(error);
  auto *buttons =
      new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Ok);
  buttons->button(QDialogButtonBox::Ok)->setText("Search");
  outer->addWidget(buttons);
  connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  auto collect = [&](QJsonObject *chosen, QString *message) {
    auto draft = FusionSearch::defaults();
    draft["root"] = root->text();
    draft["query"] = term->text();
    draft["contents"] = contents->isChecked();
    draft["regex"] = mode->currentIndex() == 1;
    draft["names"] = names->text().isEmpty() ? "*" : names->text();
    draft["exclude"] = exclude->text();
    draft["extensions"] = extensions->toPlainText();
    for (auto it = flags.cbegin(); it != flags.cend(); ++it)
      draft[it.key()] = it.value()->isChecked();
    draft["min_size"] = qint64(minimum->value()) * 1048576;
    draft["max_size"] = qint64(maximum->value()) * 1048576;
    draft["after"] = after->isChecked()
                         ? from->date().startOfDay().toSecsSinceEpoch()
                         : qint64(0);
    draft["before"] =
        before->isChecked()
            ? to->date().addDays(1).startOfDay().toSecsSinceEpoch()
            : qint64(0);
    draft["encoding"] = encoding->currentData().toString();
    draft["workers"] = workers->value();
    draft["limit"] = limit->value();
    return FusionSearch::settings(draft, chosen, message);
  };
  auto refreshPresets = [&] {
    const auto selected = presetList->currentData().toString();
    QSignalBlocker blocker(presetList);
    presetList->clear();
    presetList->addItem("Saved presets…", QString());
    for (const auto &path : presets.files()) {
      presetList->addItem(QFileInfo(path).completeBaseName(), path);
      presetList->setItemData(presetList->count() - 1, path, Qt::ToolTipRole);
    }
    presetList->setCurrentIndex(qMax(0, presetList->findData(selected)));
    loadPreset->setEnabled(!presetList->currentData().toString().isEmpty());
  };
  connect(&presets, &SearchPresets::changed, &dialog, refreshPresets);
  connect(presetList, &QComboBox::currentIndexChanged, &dialog, [&] {
    loadPreset->setEnabled(!presetList->currentData().toString().isEmpty());
  });
  refreshPresets();
  auto load = [&](const QString &path) {
    QJsonObject chosen;
    QString message;
    if (!SearchPresets::load(path, &chosen, &message)) {
      presetNote->setText(message);
      presets.refresh();
      return;
    }
    root->setText(chosen["root"].toString());
    term->setText(chosen["query"].toString());
    contents->setChecked(chosen["contents"].toBool());
    mode->setCurrentIndex(chosen["regex"].toBool() ? 1 : 0);
    names->setText(chosen["names"].toString());
    exclude->setText(chosen["exclude"].toString());
    extensions->setPlainText(chosen["extensions"].toString());
    for (auto it = flags.cbegin(); it != flags.cend(); ++it)
      it.value()->setChecked(chosen[it.key()].toBool());
    minimum->setValue(chosen["min_size"].toInteger() / 1048576);
    maximum->setValue(chosen["max_size"].toInteger() / 1048576);
    after->setChecked(chosen["after"].toInteger() > 0);
    before->setChecked(chosen["before"].toInteger() > 0);
    from->setDate(
        after->isChecked()
            ? QDateTime::fromSecsSinceEpoch(chosen["after"].toInteger()).date()
            : QDate::currentDate());
    to->setDate(before->isChecked() ? QDateTime::fromSecsSinceEpoch(
                                          chosen["before"].toInteger())
                                          .date()
                                          .addDays(-1)
                                    : QDate::currentDate());
    encoding->setCurrentIndex(
        encoding->findData(chosen["encoding"].toString()));
    workers->setValue(chosen["workers"].toInt());
    limit->setValue(chosen["limit"].toInt());
    update();
    error->clear();
    presetNote->setText("Loaded " + QFileInfo(path).completeBaseName() +
                        ". Review the settings, then Search.");
  };
  connect(loadPreset, &QPushButton::clicked, &dialog,
          [&] { load(presetList->currentData().toString()); });
  connect(loadFile, &QPushButton::clicked, &dialog, [&] {
    const auto path = QFileDialog::getOpenFileName(
        &dialog, "Load search settings", presets.directory(),
        "Search presets (*.json)");
    if (!path.isEmpty()) {
      presetList->setCurrentIndex(qMax(0, presetList->findData(path)));
      load(path);
    }
  });
  connect(savePreset, &QPushButton::clicked, &dialog, [&] {
    QJsonObject chosen;
    QString message;
    if (!collect(&chosen, &message)) {
      presetNote->setText(message);
      return;
    }
    bool accepted;
    const auto selected = presetList->currentData().toString();
    const auto name = QInputDialog::getText(
        &dialog, "Save search preset", "Preset name:", QLineEdit::Normal,
        selected.isEmpty() ? QString() : QFileInfo(selected).completeBaseName(),
        &accepted);
    if (!accepted)
      return;
    const auto path = presets.pathForName(name);
    const bool exists = !path.isEmpty() && QFileInfo::exists(path);
    if (exists && QMessageBox::question(
                      &dialog, "Replace preset",
                      "Replace the existing preset with these search settings?",
                      QMessageBox::Yes | QMessageBox::No,
                      QMessageBox::No) != QMessageBox::Yes)
      return;
    if (!presets.save(name, chosen, exists, &message)) {
      presetNote->setText(message);
      return;
    }
    presetList->setCurrentIndex(presetList->findData(path));
    presetNote->setText("Saved " + QFileInfo(path).completeBaseName() +
                        ". Presets stay available across Files windows.");
  });
  connect(presetFolder, &QPushButton::clicked, &dialog, [&] {
    QString message;
    if (!presets.ensureDirectory(&message)) {
      presetNote->setText(message);
      return;
    }
    if (!QDesktopServices::openUrl(QUrl::fromLocalFile(presets.directory())))
      presetNote->setText("Could not open the presets folder: " +
                          presets.directory());
  });
  connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
    QJsonObject chosen;
    QString message;
    if (!collect(&chosen, &message)) {
      error->setText(message);
      return;
    }
    if (!QFileInfo(root->text()).isDir()) {
      error->setText("Choose an existing local or mounted folder.");
      return;
    }
    if (term->text().trimmed().isEmpty()) {
      error->setText("Enter something to search for.");
      term->setFocus();
      return;
    }
    options = chosen;
    query->setText(term->text());
    dialog.accept();
  });
  term->setFocus();
  term->selectAll();
  if (dialog.exec() == QDialog::Accepted) {
    updateMode();
    start();
  } else if (!settingsButton->isVisible()) {
    QSignalBlocker blocker(advanced);
    advanced->setChecked(false);
    updateMode();
  }
}

void SearchPane::stopProcess() {
  auto *old = process;
  process = nullptr;
  if (!old)
    return;
  disconnect(old, nullptr, this, nullptr);
  connect(old, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), old,
          &QObject::deleteLater);
  if (old->state() == QProcess::NotRunning) {
    old->deleteLater();
    return;
  }
  auto terminate = [old] {
    if (old->processId() > 0)
      ::kill(-pid_t(old->processId()), SIGTERM);
    old->terminate();
  };
  // Wait until exec has completed before signalling a just-forked child. It
  // must not run a signal handler inherited from the GUI/test process.
  if (old->state() == QProcess::Starting)
    connect(old, &QProcess::started, old, terminate);
  else
    terminate();
  QTimer::singleShot(300, old, [old] {
    if (old->state() != QProcess::NotRunning) {
      if (old->processId() > 0)
        ::kill(-pid_t(old->processId()), SIGKILL);
      old->kill();
    }
  });
}
void SearchPane::cancel() {
  if (!running())
    return;
  drain();
  stopProcess();
  progress->hide();
  stopButton->setEnabled(false);
  results->setSortingEnabled(true);
  status->setText(
      QString("Stopped · %1 result rows kept").arg(model->rowCount()));
  if (!model->rowCount())
    empty->setText("Search stopped. Change the search and try again.");
}
void SearchPane::start() {
  if (query->text().trimmed().isEmpty()) {
    status->setText("Enter a name, wildcard or text to find.");
    focusQuery();
    return;
  }
  if (!QFileInfo(options["root"].toString()).isDir()) {
    status->setText("Choose a local or mounted folder first.");
    return;
  }
  stopProcess();
  output.clear();
  warnings.clear();
  results->setSortingEnabled(false);
  proxy->sort(-1);
  model->clear();
  exportButton->setEnabled(false);
  pages->setCurrentWidget(empty);
  empty->setText("Searching…\nResults appear as they are found.");
  progress->show();
  stopButton->setEnabled(true);
  status->setText("Starting search…");
  QJsonObject request = advanced->isChecked() ? options : QJsonObject{};
  request["root"] = options["root"];
  request["query"] = query->text();
  auto *job = new QProcess(qApp);
  process = job;
  job->setUnixProcessParameters(QProcess::UnixProcessFlag::CreateNewSession |
                                QProcess::UnixProcessFlag::ResetSignalHandlers);
  connect(job, &QProcess::started, this, [job, request] {
    job->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n');
    job->closeWriteChannel();
  });
  connect(job, &QProcess::readyReadStandardOutput, this, &SearchPane::drain);
  connect(job, &QProcess::readyReadStandardError, this, [this, job] {
    const auto text = QString::fromUtf8(job->readAllStandardError()).left(2000);
    if (!text.isEmpty())
      warnings << text;
  });
  connect(job, &QProcess::errorOccurred, this,
          [this](QProcess::ProcessError error) {
            if (error == QProcess::FailedToStart) {
              status->setText("Could not start the search worker. Check the "
                              "Python installation.");
              stopProcess();
              progress->hide();
              stopButton->setEnabled(false);
            }
          });
  connect(job, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
          [this, job](int code, QProcess::ExitStatus exit) {
            drain();
            process = nullptr;
            job->deleteLater();
            progress->hide();
            stopButton->setEnabled(false);
            results->setSortingEnabled(true);
            if (exit == QProcess::CrashExit || code > 1)
              status->setText("Search stopped unexpectedly. " +
                              warnings.join('\n').left(1000));
            if (!model->rowCount())
              empty->setText(code == 0 ? "No matches found.\nTry a different "
                                         "name, file type or search folder."
                                       : status->text());
          });
  job->start(QStandardPaths::findExecutable("python3"),
             {Fusion::root() + "/file_manager/search_worker.py"});
}
void SearchPane::drain() {
  if (!process)
    return;
  output += process->readAllStandardOutput();
  int newline;
  while ((newline = output.indexOf('\n')) >= 0) {
    const auto raw = output.left(newline);
    output.remove(0, newline + 1);
    QJsonParseError error;
    const auto message = QJsonDocument::fromJson(raw, &error);
    if (error.error != QJsonParseError::NoError) {
      status->setText("The search worker returned an invalid response.");
      continue;
    }
    event(message.object());
  }
}
void SearchPane::event(const QJsonObject &message) {
  const auto type = message["event"].toString();
  if (type == "rows") {
    model->append(message["rows"].toArray());
    pages->setCurrentWidget(results);
    exportButton->setEnabled(true);
  } else if (type == "warning")
    warnings << message["message"].toString();
  else if (type == "error") {
    status->setText(message["message"].toString());
    status->setToolTip(status->text());
  } else if (type == "started")
    status->setText(
        QString("Searching with %1 workers…").arg(message["workers"].toInt()));
  else if (type == "progress" || type == "done") {
    const bool done = type == "done";
    QString text =
        QString("%1 · %2 rows · %3 matches · %4 entries checked · %5 s")
            .arg(done ? (message["limited"].toBool() ? "Result limit reached"
                                                     : "Finished")
                      : "Searching")
            .arg(message["rows"].toInt())
            .arg(message["matches"].toInt())
            .arg(message["scanned"].toInt())
            .arg(message["seconds"].toDouble(), 0, 'f', 1);
    if (message["skipped"].toInt())
      text +=
          QString(" · %1 outside size limits").arg(message["skipped"].toInt());
    if (message["binary"].toInt())
      text +=
          QString(" · %1 binary files skipped").arg(message["binary"].toInt());
    if (message["long_lines"].toInt())
      text += QString(" · %1 oversized result lines skipped")
                  .arg(message["long_lines"].toInt());
    if (message["errors"].toInt())
      text += QString(" · %1 unreadable items").arg(message["errors"].toInt());
    status->setText(text);
    status->setToolTip(warnings.join('\n'));
  }
}
QJsonObject SearchPane::currentResult() const {
  return model->result(proxy->mapToSource(results->currentIndex()).row());
}
QList<QUrl> SearchPane::selectedUrls() const {
  QList<QUrl> urls;
  for (const auto &index : results->selectionModel()->selectedRows()) {
    const auto url = QUrl::fromLocalFile(
        model->result(proxy->mapToSource(index).row())["path"].toString());
    if (!urls.contains(url))
      urls << url;
  }
  return urls;
}
void SearchPane::openResult(bool preview) {
  const auto row = currentResult();
  if (row.isEmpty())
    return;
  if (preview && row["line"].toInt()) {
    QDialog dialog(this);
    dialog.setWindowTitle("Matching text — " + row["name"].toString());
    dialog.resize(760, 340);
    auto *layout = new QVBoxLayout(&dialog);
    auto *label =
        new QLabel(row["path"].toString() + QString("\nLine %1 · Column %2")
                                                .arg(row["line"].toInt())
                                                .arg(row["column"].toInt()));
    label->setTextFormat(Qt::PlainText);
    label->setWordWrap(true);
    layout->addWidget(label);
    auto *text = new QPlainTextEdit(row["preview"].toString());
    text->setReadOnly(true);
    text->setFont(QFontDatabase::systemFont(QFontDatabase::FixedFont));
    layout->addWidget(text);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close);
    layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    dialog.exec();
    return;
  }
  emit openRequested(QUrl::fromLocalFile(row["path"].toString()),
                     row["directory"].toBool());
}
void SearchPane::revealResult() {
  const auto row = currentResult();
  if (!row.isEmpty())
    emit revealRequested(QUrl::fromLocalFile(row["path"].toString()));
}
void SearchPane::copyResults(bool pathsOnly) {
  QStringList lines;
  for (const auto &index : results->selectionModel()->selectedRows()) {
    const auto row = model->result(proxy->mapToSource(index).row());
    const auto line = pathsOnly ? row["path"].toString()
                                : QString("%1\t%2\t%3\t%4")
                                      .arg(row["path"].toString())
                                      .arg(row["line"].toInt())
                                      .arg(row["matches"].toInt())
                                      .arg(row["preview"].toString());
    if (!pathsOnly || !lines.contains(line))
      lines << line;
  }
  if (!lines.isEmpty())
    QApplication::clipboard()->setText(lines.join('\n'));
}
void SearchPane::exportResults() {
  const auto path = QFileDialog::getSaveFileName(
      this, "Export search results", QDir::homePath() + "/search-results.csv",
      "CSV files (*.csv)");
  if (path.isEmpty())
    return;
  QSaveFile file(path);
  if (!file.open(QIODevice::WriteOnly)) {
    status->setText(file.errorString());
    return;
  }
  auto cell = [](QString value) {
    if (!value.isEmpty() && QString("=+-@\t\r").contains(value[0]))
      value.prepend('\'');
    value.replace('"', "\"\"");
    return '"' + value + '"';
  };
  file.write(
      "Name,Size bytes,Line,Matches,Modified,Full path,Matching text\r\n");
  for (int i = 0; i < proxy->rowCount(); ++i) {
    const auto row =
        model->result(proxy->mapToSource(proxy->index(i, 0)).row());
    QStringList values{
        row["name"].toString(),
        QString::number(row["size"].toInteger()),
        QString::number(row["line"].toInt()),
        QString::number(row["matches"].toInt()),
        QDateTime::fromSecsSinceEpoch(row["modified"].toInteger())
            .toString(Qt::ISODate),
        row["path"].toString(),
        row["preview"].toString()};
    for (auto &value : values)
      value = cell(value);
    file.write((values.join(',') + "\r\n").toUtf8());
  }
  if (!file.commit())
    status->setText(file.errorString());
  else
    status->setText("Results exported to " + path);
}
bool SearchPane::handleAction(const QString &id) {
  if (id == "copy") {
    copyResults(false);
    return true;
  }
  if (id == "copyPath") {
    copyResults(true);
    return true;
  }
  if (id == "selectAll") {
    results->selectAll();
    return true;
  }
  if (id == "open") {
    openResult(true);
    return true;
  }
  if (QStringList{"cut", "paste", "rename", "trash", "delete", "undo",
                  "newFolder", "compress", "extract"}
          .contains(id)) {
    status->setText(
        "Use Show in folder to change files. Search results stay read-only.");
    return true;
  }
  return false;
}
