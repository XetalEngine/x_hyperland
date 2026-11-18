#include "system_tweaks_page.h"
#include "runtime_log_guard.h"
#include <QtWidgets>
#include <algorithm>

namespace {
QString labelFor(const QJsonObject &spec, const QString &value) {
  for (const auto &item : spec["choices"].toArray()) {
    const auto option = item.toObject();
    if (option["value"].toString() == value) return option["label"].toString();
  }
  if (value.isEmpty()) return "Not reported";
  bool numeric = false; const auto number = value.toLongLong(&numeric);
  return numeric ? QLocale().toString(number) + spec["suffix"].toString() + spec["unit"].toString() : value;
}
QLabel *text(const QString &value, const char *name, QWidget *parent) {
  auto *label = new QLabel(value, parent);
  label->setTextFormat(Qt::PlainText); label->setWordWrap(true); label->setObjectName(name);
  label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  return label;
}
}

SystemTweaksPage::SystemTweaksPage(const QString &root, QWidget *parent) : QWidget(parent), root(root) {
  setObjectName("systemTweaksPage");
  setStyleSheet(
      "QWidget#systemTweaksPage {background:transparent;}"
      "QWidget#tweakCard {background:palette(alternate-base);border:1px solid palette(mid);border-radius:10px;}"
      "QWidget#tweakCard QLabel {background:transparent;border:0;}"
      "QLabel#tweakTitle {font-size:16px;font-weight:600;}"
      "QLabel#tweakDescription,QLabel#tweakNote,QLabel#tweakDetails {font-size:12px;}"
      "QLabel#tweakCurrent {font-weight:600;}"
      "QLabel#tweakSaved {color:palette(link);font-size:12px;}"
      "QLabel#tweaksHeading {font-size:26px;font-weight:650;}"
      "QLabel#tweaksMessage {padding:8px;border-radius:6px;background:palette(alternate-base);}"
      "QPushButton#tweakApply {font-weight:600;padding:6px 12px;}"
      "QPushButton#tweakApply:enabled {background:palette(highlight);color:palette(highlighted-text);border:1px solid palette(highlight);}"
      "QToolButton#tweakDetailsButton {border:0;background:transparent;padding:2px;text-align:left;}"
      "QScrollArea#tweaksScroll {border:0;background:transparent;}"
      "QWidget#tweaksCanvas {background:transparent;}");
  auto *layout = new QVBoxLayout(this); layout->setContentsMargins(0, 0, 0, 0); layout->setSpacing(12);
  auto *heading = new QHBoxLayout;
  auto *titles = new QVBoxLayout; titles->setSpacing(5);
  titles->addWidget(text("System Tweaks", "tweaksHeading", this));
  titles->addWidget(text("Your choices, saved across restarts. System changes are backed up automatically.", "muted", this));
  heading->addLayout(titles, 1);
  refresh = new QPushButton("Refresh status", this); refresh->setObjectName("tweaksRefresh");
  heading->addWidget(refresh, 0, Qt::AlignVCenter); layout->addLayout(heading);
  auto *tools = new QHBoxLayout;
  search = new QLineEdit(this); search->setObjectName("tweaksSearch");
  search->setPlaceholderText("Find a setting…"); search->setClearButtonEnabled(true);
  tools->addWidget(search, 1);
  summary = text("Reading system settings…", "muted", this); tools->addWidget(summary);
  layout->addLayout(tools);
  message = text({}, "tweaksMessage", this); message->hide(); layout->addWidget(message);
  tabs = new QTabWidget(this); tabs->setObjectName("systemTweaksCategories");
  tabs->setDocumentMode(true); tabs->setUsesScrollButtons(true);
  for (const auto &category : {"Performance", "Memory & storage", "Security", "Network", "System", "Desktop", "Hyprland"}) {
    auto *scroll = new QScrollArea(tabs); scroll->setObjectName("tweaksScroll");
    scroll->setWidgetResizable(true); scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *canvas = new QWidget; canvas->setObjectName("tweaksCanvas");
    auto *grid = new QGridLayout(canvas); grid->setContentsMargins(0, 12, 4, 8); grid->setSpacing(12);
    grids[category] = grid; categoryPages[category] = scroll;
    scroll->setWidget(canvas); tabs->addTab(scroll, QString(category).replace('&', "&&"));
  }
  layout->addWidget(tabs, 1);
  auto *hypr = grids["Hyprland"];
  hypr->addWidget(new RuntimeLogGuard(root + "/scripts/runtime-log-guard.py", this), 0, 0);
  hypr->setRowStretch(1, 1);
  addLink("Network", "DNS & connections", "Save DNS servers in the connection’s network profile.", "network");
  addLink("Security", "Firewall rules", "Manage persistent firewall rules and services.", "firewall");
  addLink("Security", "CPU vulnerability mitigations", "Review boot options and CPU mitigations in the boot editor.", "grub");
  addLink("System", "Startup & file indexing", "Review boot splash, initramfs and file indexing configuration individually.", "configuration");
  addLink("Performance", "Power-management services", "Review power services if they override your manual CPU choices.", "services");
  process = new QProcess(this);
  deadline = new QTimer(this); deadline->setSingleShot(true);
  connect(refresh, &QPushButton::clicked, this, [this] { request("status"); });
  connect(search, &QLineEdit::textChanged, this, [this] { arrange(); });
  connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) { finished(code); });
  connect(process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) finished(-1);
  });
  connect(deadline, &QTimer::timeout, this, [this] {
    if (action == "status") process->kill();
    else { message->setText("Still waiting for authentication or the system operation to finish…"); message->show(); }
  });
}

SystemTweaksPage::~SystemTweaksPage() {
  if (process->state() != QProcess::NotRunning) {
    // Closing stdin cancels an outstanding authentication request before any
    // changes. An authenticated transaction is allowed to finish/roll back.
    process->closeWriteChannel();
    if (action == "status") { process->kill(); process->waitForFinished(1000); }
    else {
      process->disconnect(this); process->setParent(QCoreApplication::instance());
      connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), process, &QObject::deleteLater);
    }
  }
}

void SystemTweaksPage::addLink(const QString &category, const QString &title, const QString &description, const QString &tool) {
  auto *box = new QWidget(this); box->setObjectName("tweakCard");
  box->setProperty("tweakCategory", category); box->setProperty("tweakLink", true);
  auto *layout = new QVBoxLayout(box); layout->setContentsMargins(16, 14, 16, 14); layout->setSpacing(8);
  layout->addWidget(text(title, "tweakTitle", box)); layout->addWidget(text(description, "tweakDescription", box));
  auto *button = new QPushButton("Open " + QString(title).replace('&', "&&").toLower() + " →", box);
  connect(button, &QPushButton::clicked, this, [this, tool] { emit openTool(tool); });
  layout->addWidget(button, 0, Qt::AlignLeft);
  categoryCards[category].append(box);
  grids[category]->addWidget(box, grids[category]->rowCount(), 0);
}

void SystemTweaksPage::addCard(const QJsonObject &spec) {
  const auto id = spec["id"].toString(), category = spec["category"].toString();
  Card card; card.spec = spec;
  card.box = new QWidget(this); card.box->setObjectName("tweakCard"); card.box->setProperty("tweakId", id);
  card.box->setProperty("tweakCategory", category);
  auto *layout = new QVBoxLayout(card.box); layout->setContentsMargins(16, 14, 16, 14); layout->setSpacing(8);
  layout->addWidget(text(spec["title"].toString(), "tweakTitle", card.box));
  layout->addWidget(text(spec["description"].toString(), "tweakDescription", card.box));
  card.current = text({}, "tweakCurrent", card.box); layout->addWidget(card.current);
  card.saved = text({}, "tweakSaved", card.box); layout->addWidget(card.saved);
  auto *edit = new QHBoxLayout;
  if (spec.contains("minimum")) {
    card.number = new QSpinBox(card.box); card.number->setRange(spec["minimum"].toInt(), spec["maximum"].toInt());
    card.number->setGroupSeparatorShown(true); card.number->setSuffix(spec["suffix"].toString());
    card.number->setObjectName(id + "Choice"); card.number->setAccessibleName(spec["title"].toString());
    edit->addWidget(card.number, 1);
    connect(card.number, qOverload<int>(&QSpinBox::valueChanged), this, [this, id] { cards[id].dirty = true; updateButtons(); });
  } else {
    card.combo = new QComboBox(card.box); card.combo->setObjectName(id + "Choice");
    card.combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); card.combo->setMinimumContentsLength(8);
    card.combo->setAccessibleName(spec["title"].toString()); edit->addWidget(card.combo, 1);
    connect(card.combo, qOverload<int>(&QComboBox::currentIndexChanged), this, [this, id] { cards[id].dirty = true; updateButtons(); });
  }
  card.apply = new QPushButton("Save && apply", card.box); card.apply->setObjectName("tweakApply");
  card.apply->setProperty("tweakId", id); edit->addWidget(card.apply); layout->addLayout(edit);
  connect(card.apply, &QPushButton::clicked, this, [this, id] { request("apply", id, value(cards[id])); });
  card.note = text({}, "tweakNote", card.box); layout->addWidget(card.note);
  auto *footer = new QHBoxLayout;
  auto *info = new QToolButton(card.box); info->setObjectName("tweakDetailsButton");
  info->setText("About this setting"); info->setCheckable(true); info->setArrowType(Qt::RightArrow);
  info->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); footer->addWidget(info); footer->addStretch();
  card.restore = new QPushButton("Restore previous", card.box); card.restore->setObjectName(id + "Restore");
  footer->addWidget(card.restore); layout->addLayout(footer);
  card.details = text(spec["details"].toString(), "tweakDetails", card.box); card.details->hide(); layout->addWidget(card.details);
  info->setVisible(!spec["details"].toString().isEmpty());
  connect(info, &QToolButton::toggled, this, [info, details = card.details](bool shown) {
    info->setArrowType(shown ? Qt::DownArrow : Qt::RightArrow); details->setVisible(shown);
  });
  connect(card.restore, &QPushButton::clicked, this, [this, id] { request("restore", id, ""); });
  cards[id] = card; categoryCards[category].append(card.box);
  grids[category]->addWidget(card.box, grids[category]->rowCount(), 0);
}

QString SystemTweaksPage::value(const Card &card) const {
  return card.number ? QString::number(card.number->value()) : card.combo->currentData().toString();
}

void SystemTweaksPage::display(const QJsonObject &snapshot) {
  revision = snapshot["revision"].toString(); int available = 0, savedCount = 0;
  for (const auto &item : snapshot["settings"].toArray()) {
    const auto spec = item.toObject(); const auto id = spec["id"].toString();
    if (id.isEmpty() || !grids.contains(spec["category"].toString())) continue;
    if (!cards.contains(id)) addCard(spec);
    auto &card = cards[id]; const auto previous = value(card); card.spec = spec;
    const auto current = spec["current"].toString(), saved = spec["saved"].toString();
    const auto choice = card.dirty ? previous : !saved.isEmpty() ? saved : !current.isEmpty() ? current : spec["default"].toString();
    if (card.number) { QSignalBlocker guard(card.number); card.number->setValue(choice.toInt()); }
    else {
      QSignalBlocker guard(card.combo); card.combo->clear();
      for (const auto &option : spec["choices"].toArray())
        card.combo->addItem(option.toObject()["label"].toString(), option.toObject()["value"].toString());
      card.combo->setCurrentIndex(card.combo->findData(choice));
      if (card.combo->currentIndex() < 0 && !card.dirty) {
        card.combo->insertItem(0, "Choose…", QString()); card.combo->setCurrentIndex(0);
      }
    }
    card.current->setText("Current · " + labelFor(spec, current));
    card.saved->setText(saved.isEmpty() ? "Using existing system configuration" : "Saved · " + labelFor(spec, saved));
    const auto note = spec["note"].toString();
    card.note->setText(note.isEmpty() && spec["restart"].toBool() ? "Takes effect after reboot." : note);
    card.note->setVisible(!card.note->text().isEmpty());
    card.apply->setText(spec["restart"].toBool() ? "Save for reboot" : "Save && apply");
    card.restore->setVisible(spec["has_backup"].toBool());
    if (spec["supported"].toBool()) ++available;
    if (!saved.isEmpty()) ++savedCount;
  }
  summary->setText(QString("%1 available · %2 saved").arg(available).arg(savedCount));
  updateButtons(); arrange();
}

void SystemTweaksPage::updateButtons() {
  const bool running = !action.isEmpty() || (process && process->state() != QProcess::NotRunning);
  for (auto &card : cards) {
    const bool available = card.spec["supported"].toBool();
    const bool reboot = card.spec["restart"].toBool() ||
        (card.spec["id"].toString() == "ptrace" && value(card) == "3");
    card.apply->setText(reboot ? "Save for reboot" : "Save && apply");
    auto note = card.spec["note"].toString();
    if (reboot) note += (note.isEmpty() ? "" : " ") + QString("Takes effect after reboot.");
    card.note->setText(note); card.note->setVisible(!note.isEmpty());
    card.apply->setEnabled(!running && available && !value(card).isEmpty());
    card.restore->setEnabled(!running);
    if (card.combo) card.combo->setEnabled(!running && available);
    if (card.number) card.number->setEnabled(!running && available);
  }
  refresh->setEnabled(!running);
}

void SystemTweaksPage::busy(bool active) {
  refresh->setEnabled(!active);
  for (auto &card : cards) {
    card.apply->setEnabled(!active && card.spec["supported"].toBool() && !value(card).isEmpty());
    card.restore->setEnabled(!active);
    if (card.combo) card.combo->setEnabled(!active && card.spec["supported"].toBool());
    if (card.number) card.number->setEnabled(!active && card.spec["supported"].toBool());
  }
}

void SystemTweaksPage::request(const QString &command, const QString &id, const QString &value) {
  if (process->state() != QProcess::NotRunning || !action.isEmpty()) return;
  action = command; activeId = id; busy(true);
  if (command != "status") {
    message->setText(command == "restore" ? "Restoring the previous saved setting…" : "Saving your choice. Administrator authentication may be requested…");
    message->show();
  }
  emit operationRequested(command, id, value, revision);
  QStringList args{"-I", root + "/control_panel/system_tweaks.py", command};
  if (command != "status") args << id << value << revision;
  process->start("/usr/bin/python3", args);
  deadline->start(command == "status" ? 30000 : 60000);
}

void SystemTweaksPage::finished(int code) {
  if (action.isEmpty()) return;
  deadline->stop();
  const auto completed = action; action.clear();
  const auto bytes = process->readAllStandardOutput();
  const auto data = QJsonDocument::fromJson(bytes).object();
  if (code != 0 || data.isEmpty() || data.contains("error")) {
    auto error = data["error"].toString();
    if (error.isEmpty()) error = QString::fromUtf8(process->readAllStandardError()).trimmed();
    if (error.isEmpty()) error = "The operation was cancelled or the helper could not finish.";
    message->setText("Could not " + QString(completed == "status" ? "read settings: " : "save the change: ") + error.left(1800));
    message->show(); busy(false); return;
  }
  if (completed == "status") { display(data); busy(false); }
  else {
    if (cards.contains(activeId)) cards[activeId].dirty = false;
    message->setText(data["message"].toString()); message->show();
    request("status");
  }
}

void SystemTweaksPage::arrange() {
  const auto query = search->text().trimmed();
  const int columns = width() >= 1050 ? 2 : 1;
  for (auto it = grids.begin(); it != grids.end(); ++it) {
    if (it.key() == "Hyprland") continue;
    auto *grid = it.value(); auto widgets = categoryCards[it.key()];
    while (grid->count()) delete grid->takeAt(0);
    std::stable_sort(widgets.begin(), widgets.end(), [](QWidget *a, QWidget *b) {
      return !a->property("tweakLink").toBool() && b->property("tweakLink").toBool();
    });
    for (int row = 0; row < grid->rowCount(); ++row) grid->setRowStretch(row, 0);
    grid->setColumnStretch(0, 1); grid->setColumnStretch(1, columns == 2 ? 1 : 0);
    int visible = 0;
    for (auto *widget : widgets) {
      QString content;
      for (auto *label : widget->findChildren<QLabel *>()) content += ' ' + label->text();
      const bool match = query.isEmpty() || content.contains(query, Qt::CaseInsensitive);
      widget->setVisible(match);
      if (match) { grid->addWidget(widget, visible / columns, visible % columns, Qt::AlignTop); ++visible; }
    }
    grid->setRowStretch((visible + columns - 1) / columns, 1);
    tabs->setTabVisible(tabs->indexOf(categoryPages[it.key()]), query.isEmpty() || visible > 0);
  }
  tabs->setTabVisible(tabs->indexOf(categoryPages["Hyprland"]), query.isEmpty() || QString("Hyprland logs").contains(query, Qt::CaseInsensitive));
}

void SystemTweaksPage::selectCategory(const QString &name) { if (categoryPages.contains(name)) tabs->setCurrentWidget(categoryPages[name]); }
void SystemTweaksPage::showEvent(QShowEvent *event) { QWidget::showEvent(event); QTimer::singleShot(0, this, [this] { request("status"); }); }
void SystemTweaksPage::resizeEvent(QResizeEvent *event) { QWidget::resizeEvent(event); arrange(); }
