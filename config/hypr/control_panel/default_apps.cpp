#include "default_apps.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QtWidgets>

namespace {
QIcon appIcon(const QString &name,
              const QString &fallback = "application-x-executable") {
  return name.startsWith('/')
             ? QIcon(name)
             : QIcon::fromTheme(name, QIcon::fromTheme(fallback));
}
QLabel *plain(const QString &text, const QString &name = {}) {
  auto *label = new QLabel(text);
  label->setObjectName(name);
  label->setTextFormat(Qt::PlainText);
  label->setWordWrap(true);
  return label;
}
QStringList strings(const QJsonArray &array) {
  QStringList result;
  for (const auto &value : array)
    result << value.toString();
  return result;
}

class AppCard final : public QPushButton {
public:
  QJsonObject role, application;
  AppCard(const QJsonObject &role, const QJsonObject &application,
          QWidget *parent)
      : QPushButton(parent), role(role), application(application) {
    setObjectName("defaultRole_" + role["id"].toString());
    setAccessibleName(role["title"].toString() + ": " +
                      application["name"].toString("Choose an app"));
    setToolTip(role["description"].toString() + "\n" +
               QString("Choose the default for %1 file types and links.")
                   .arg(role["types"].toArray().size()));
    setCursor(Qt::PointingHandCursor);
    setMinimumWidth(250);
    setFixedHeight(132);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  }
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const auto colors = palette();
    const bool highlighted =
        isEnabled() && (underMouse() || hasFocus() || isDown());
    const auto accent = colors.color(QPalette::Link);
    QLinearGradient surface(rect().topLeft(), rect().bottomRight());
    surface.setColorAt(0, colors.color(highlighted ? QPalette::Highlight
                                                   : QPalette::AlternateBase));
    surface.setColorAt(1, colors.color(QPalette::Base));
    painter.setBrush(surface);
    painter.setPen(QPen(highlighted ? accent : colors.color(QPalette::Midlight),
                        highlighted ? 1.5 : 1));
    const int radius = qApp->property("xetalPanelCardRadius").toInt();
    painter.drawRoundedRect(QRectF(rect()).adjusted(1, 1, -1, -1), radius,
                            radius);
    appIcon(role["icon"].toString()).paint(&painter, QRect(16, 16, 28, 28));
    QFont title = font();
    title.setBold(true);
    painter.setFont(title);
    painter.setPen(colors.color(QPalette::Text));
    painter.drawText(QRect(55, 13, width() - 68, 23), Qt::AlignVCenter,
                     painter.fontMetrics().elidedText(role["title"].toString(),
                                                      Qt::ElideRight,
                                                      width() - 68));
    QFont detail = font();
    detail.setPointSizeF(qMax(8., detail.pointSizeF() - 1));
    painter.setFont(detail);
    painter.setPen(colors.color(QPalette::PlaceholderText));
    painter.drawText(
        QRect(55, 35, width() - 68, 20), Qt::AlignVCenter,
        painter.fontMetrics().elidedText(role["description"].toString(),
                                         Qt::ElideRight, width() - 68));
    const QString chosen = application["name"].toString("Choose an app");
    appIcon(application["icon"].toString(), role["icon"].toString())
        .paint(&painter, QRect(18, 75, 30, 30));
    title.setPointSizeF(font().pointSizeF() + 1);
    painter.setFont(title);
    painter.setPen(colors.color(QPalette::Text));
    painter.drawText(
        QRect(59, 72, width() - 96, 28), Qt::AlignVCenter,
        painter.fontMetrics().elidedText(chosen, Qt::ElideRight, width() - 96));
    painter.setPen(accent);
    painter.drawText(QRect(width() - 32, 76, 18, 24), Qt::AlignCenter, "›");
    painter.setFont(detail);
    painter.setPen(colors.color(QPalette::PlaceholderText));
    const QString caption =
        role["mixed"].toBool()  ? "Some formats use other apps"
        : application.isEmpty() ? "Choose an installed application"
                                : "Default application";
    painter.drawText(QRect(59, 100, width() - 75, 18), Qt::AlignVCenter,
                     painter.fontMetrics().elidedText(caption, Qt::ElideRight,
                                                      width() - 75));
  }
};

class AppArtwork final : public QWidget {
public:
  explicit AppArtwork(QWidget *parent) : QWidget(parent) {
    setFixedSize(176, 84);
  }
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const QStringList icons{"internet-web-browser", "audio-x-generic",
                            "image-x-generic"};
    for (int i = 0; i < icons.size(); ++i) {
      const QRectF tile(4 + 55 * i, i == 1 ? 7 : 22, 57, 57);
      painter.setPen(palette().color(QPalette::Midlight));
      painter.setBrush(
          palette().color(i == 1 ? QPalette::Highlight : QPalette::Base));
      painter.drawRoundedRect(tile, 13, 13);
      appIcon(icons[i]).paint(&painter,
                              tile.adjusted(12, 12, -12, -12).toRect());
    }
  }
};

class PageStack : public QStackedWidget {
public:
  using QStackedWidget::QStackedWidget;
  QSize minimumSizeHint() const override {
    return currentWidget()
               ? QSize(0, currentWidget()->minimumSizeHint().height())
               : QSize();
  }
  QSize sizeHint() const override {
    return currentWidget() ? currentWidget()->sizeHint() : QSize();
  }
};
} // namespace

DefaultApps::DefaultApps(const QString &helper, QWidget *parent)
    : QWidget(parent), helper(helper) {
  setObjectName("defaultAppsTab");
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(8, 6, 8, 6);
  layout->setSpacing(16);
  auto *hero = new QFrame;
  hero->setObjectName("defaultsHero");
  auto *heroRow = new QHBoxLayout(hero);
  heroRow->setContentsMargins(24, 16, 24, 16);
  auto *intro = new QVBoxLayout;
  intro->setSpacing(6);
  intro->addWidget(plain("YOUR DESKTOP", "defaultsEyebrow"));
  intro->addWidget(plain("Default Apps", "defaultsTitle"));
  intro->addWidget(plain("Choose what opens your links, files and media.",
                         "defaultsSubtitle"));
  heroRow->addLayout(intro, 1);
  heroRow->addWidget(new AppArtwork(hero));
  layout->addWidget(hero);

  auto *navigation = new QHBoxLayout;
  everyday = new QToolButton;
  everyday->setText("Everyday apps");
  everyday->setCheckable(true);
  everyday->setChecked(true);
  byType = new QToolButton;
  byType->setText("File types && links");
  byType->setCheckable(true);
  auto *choices = new QButtonGroup(this);
  choices->addButton(everyday, 0);
  choices->addButton(byType, 1);
  navigation->addWidget(everyday);
  navigation->addWidget(byType);
  navigation->addStretch();
  refresh = new QPushButton("Refresh apps");
  refresh->setObjectName("defaultsRefresh");
  refresh->setIcon(appIcon("view-refresh"));
  navigation->addWidget(refresh);
  layout->addLayout(navigation);

  pages = new PageStack;
  cards = new QWidget;
  grid = new QGridLayout(cards);
  grid->setContentsMargins(0, 0, 0, 0);
  grid->setSpacing(12);
  grid->setAlignment(Qt::AlignTop);
  pages->addWidget(cards);
  auto *advanced = new QWidget;
  auto *advancedLayout = new QVBoxLayout(advanced);
  advancedLayout->setContentsMargins(0, 0, 0, 0);
  advancedLayout->setSpacing(10);
  search = new QLineEdit;
  search->setObjectName("defaultsTypeSearch");
  search->setPlaceholderText("Search .pdf, MP3, HTTPS, or a file type…");
  search->setClearButtonEnabled(true);
  advancedLayout->addWidget(search);
  types = new QTreeWidget;
  types->setObjectName("defaultsTypes");
  types->setHeaderLabels({"File type", "Extensions or link", "Default app"});
  types->setRootIsDecorated(false);
  types->setUniformRowHeights(true);
  types->setAlternatingRowColors(true);
  types->setIconSize({24, 24});
  types->setSelectionMode(QAbstractItemView::SingleSelection);
  types->setMinimumHeight(360);
  types->header()->setSectionResizeMode(0, QHeaderView::Stretch);
  types->header()->setSectionResizeMode(1, QHeaderView::Stretch);
  types->header()->setSectionResizeMode(2, QHeaderView::Stretch);
  advancedLayout->addWidget(types, 1);
  auto *typeActions = new QHBoxLayout;
  typeCount = plain("", "muted");
  typeActions->addWidget(typeCount, 1);
  changeType = new QPushButton("Change app…");
  changeType->setObjectName("defaultsChangeType");
  changeType->setEnabled(false);
  typeActions->addWidget(changeType);
  advancedLayout->addLayout(typeActions);
  pages->addWidget(advanced);
  layout->addWidget(pages, 1);
  connect(choices, &QButtonGroup::idClicked, this, [this](int index) {
    pages->setCurrentIndex(index);
    pages->updateGeometry();
    if (index)
      search->setFocus();
  });
  auto chooseType = [this] {
    auto *item = types->currentItem();
    if (!item || item->isHidden() || busy)
      return;
    const auto mime = item->data(0, Qt::UserRole).toString();
    choose(item->text(0), {mime}, item->data(2, Qt::UserRole).toString(),
           {{"type", mime}});
  };
  connect(changeType, &QPushButton::clicked, this, chooseType);
  connect(types, &QTreeWidget::itemActivated, this,
          [chooseType] { chooseType(); });
  connect(types, &QTreeWidget::itemSelectionChanged, this, [this] {
    changeType->setEnabled(!busy && types->currentItem() &&
                           !types->currentItem()->isHidden());
  });
  connect(search, &QLineEdit::textChanged, this, &DefaultApps::filterTypes);

  progress = new QProgressBar;
  progress->setRange(0, 0);
  progress->setFixedHeight(3);
  progress->setTextVisible(false);
  progress->hide();
  layout->addWidget(progress);
  auto *foot = new QHBoxLayout;
  status = plain("Reading your installed apps…", "defaultsStatus");
  foot->addWidget(status, 1);
  undo = new QPushButton("Undo last change");
  undo->setObjectName("defaultsUndo");
  undo->setIcon(appIcon("edit-undo"));
  undo->hide();
  foot->addWidget(undo);
  layout->addLayout(foot);
  connect(refresh, &QPushButton::clicked, this,
          [this] { request("snapshot"); });
  connect(undo, &QPushButton::clicked, this,
          [this] { request("undo", {{"token", undoToken}}); });

  process = new QProcess(this);
  timeout = new QTimer(this);
  timeout->setSingleShot(true);
  timeout->setInterval(15000);
  connect(timeout, &QTimer::timeout, process, &QProcess::kill);
  connect(process, &QProcess::errorOccurred, this,
          [this](QProcess::ProcessError error) {
            if (error == QProcess::FailedToStart) {
              timeout->stop();
              setBusy(false);
              status->setText(
                  "Could not start the default-app helper. Try Refresh apps.");
            }
          });
  connect(
      process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
      [this](int code, QProcess::ExitStatus) {
        timeout->stop();
        const auto result =
            QJsonDocument::fromJson(process->readAllStandardOutput()).object();
        process->readAllStandardError();
        setBusy(false);
        if (code || result.contains("error") || result.isEmpty()) {
          status->setText(result["error"].toString(
              "Could not read or save your defaults. Try Refresh apps."));
          status->setProperty("error", true);
        } else if (action == "snapshot") {
          display(result);
          status->setText(
              pendingMessage.isEmpty()
                  ? "Choose an app to apply it across your desktop account."
                  : pendingMessage);
          pendingMessage.clear();
        } else {
          undoToken = result["undo"].toString();
          undo->setVisible(!undoToken.isEmpty());
          pendingMessage = result["message"].toString();
          request("snapshot");
        }
        status->style()->unpolish(status);
        status->style()->polish(status);
      });
}

DefaultApps::~DefaultApps() {
  disconnect(process, nullptr, this, nullptr);
  if (process->state() != QProcess::NotRunning &&
      !process->waitForFinished(2000)) {
    process->kill();
    process->waitForFinished();
  }
}
void DefaultApps::setBusy(bool value) {
  busy = value;
  pages->setEnabled(!value);
  refresh->setEnabled(!value);
  undo->setEnabled(!value);
  progress->setVisible(value);
}
void DefaultApps::request(const QString &operation, const QJsonObject &data) {
  if (busy)
    return;
  action = operation;
  setBusy(true);
  status->setProperty("error", false);
  status->setText(operation == "snapshot"
                      ? "Reading installed apps and defaults…"
                      : "Saving your defaults…");
  process->start("python3", {helper, operation});
  process->write(QJsonDocument(data).toJson(QJsonDocument::Compact));
  process->closeWriteChannel();
  timeout->start();
}
void DefaultApps::display(const QJsonObject &data) {
  revision = data["revision"].toString();
  applications = data["apps"].toArray();
  appIndex.clear();
  for (const auto &entry : applications) {
    const auto app = entry.toObject();
    appIndex.insert(app["id"].toString(), app);
  }
  while (auto *item = grid->takeAt(0))
    delete item;
  qDeleteAll(roleCards);
  roleCards.clear();
  roleIndex.clear();
  for (const auto &entry : data["roles"].toArray()) {
    const auto role = entry.toObject();
    roleIndex.insert(role["id"].toString(), role);
    auto *card =
        new AppCard(role, appIndex.value(role["default"].toString()), cards);
    roleCards << card;
    connect(card, &QPushButton::clicked, this, [this, role] {
      choose(role["title"].toString(), strings(role["types"].toArray()),
             role["default"].toString(), {{"role", role["id"].toString()}});
    });
  }
  columns = 0;
  arrange();
  const auto selected =
      types->currentItem()
          ? types->currentItem()->data(0, Qt::UserRole).toString()
          : QString();
  types->setUpdatesEnabled(false);
  types->setSortingEnabled(false);
  types->clear();
  for (const auto &entry : data["filetypes"].toArray()) {
    const auto type = entry.toObject();
    const auto mime = type["id"].toString();
    const auto app = appIndex.value(type["default"].toString());
    const auto extension = mime.startsWith("x-scheme-handler/")
                               ? mime.section('/', 1) + "://"
                               : type["extensions"].toString();
    auto *item =
        new QTreeWidgetItem(types, {type["name"].toString(), extension,
                                    app["name"].toString("No app selected")});
    item->setData(0, Qt::UserRole, mime);
    item->setData(2, Qt::UserRole, type["default"].toString());
    item->setToolTip(0, mime);
    item->setToolTip(1, extension);
    item->setIcon(2, appIcon(app["icon"].toString()));
    if (mime == selected)
      types->setCurrentItem(item);
  }
  types->setSortingEnabled(true);
  types->sortItems(0, Qt::AscendingOrder);
  types->setUpdatesEnabled(true);
  filterTypes();
}
void DefaultApps::arrange() {
  const int wanted = qBound(1, (cards->width() + 12) / 300, 3);
  if (wanted == columns)
    return;
  columns = wanted;
  while (auto *item = grid->takeAt(0))
    delete item;
  for (int i = 0; i < roleCards.size(); ++i) {
    grid->addWidget(roleCards[i], i / columns, i % columns);
    roleCards[i]->show();
  }
  for (int i = 0; i < 3; ++i)
    grid->setColumnStretch(i, i < columns ? 1 : 0);
  pages->updateGeometry();
}
void DefaultApps::filterTypes() {
  const auto query = search->text().trimmed();
  int count = 0;
  for (int i = 0; i < types->topLevelItemCount(); ++i) {
    auto *item = types->topLevelItem(i);
    const auto text = item->text(0) + ' ' + item->text(1) + ' ' +
                      item->text(2) + ' ' +
                      item->data(0, Qt::UserRole).toString();
    const bool visible = text.contains(query, Qt::CaseInsensitive);
    item->setHidden(!visible);
    if (visible)
      ++count;
  }
  typeCount->setText(
      count ? QString("%1 file types and links · Select one to change its app")
                  .arg(count)
            : "No matching types. Try an extension such as .pdf or a name such "
              "as HTTPS.");
  changeType->setEnabled(!busy && types->currentItem() &&
                         !types->currentItem()->isHidden());
}
void DefaultApps::choose(const QString &title, const QStringList &mimeTypes,
                         const QString &current, const QJsonObject &target) {
  if (busy)
    return;
  QDialog dialog(this);
  dialog.setObjectName("defaultAppPicker");
  dialog.setWindowTitle("Choose an app · " + title);
  dialog.resize(570, 580);
  dialog.setMinimumSize(480, 420);
  auto *layout = new QVBoxLayout(&dialog);
  layout->setContentsMargins(22, 20, 22, 18);
  layout->setSpacing(12);
  layout->addWidget(plain(title, "defaultsPickerTitle"));
  layout->addWidget(plain(
      mimeTypes.size() == 1
          ? "Choose what opens this type across your desktop."
          : QString("Use one app for all %1 associated file types and links.")
                .arg(mimeTypes.size()),
      "muted"));
  auto *find = new QLineEdit;
  find->setObjectName("defaultsAppSearch");
  find->setPlaceholderText("Search installed applications…");
  find->setClearButtonEnabled(true);
  layout->addWidget(find);
  auto *all = new QCheckBox("Show all installed apps");
  all->setObjectName("defaultsAllApps");
  layout->addWidget(all);
  auto *list = new QListWidget;
  list->setObjectName("defaultsAppList");
  list->setIconSize({32, 32});
  list->setSpacing(3);
  layout->addWidget(list, 1);
  auto *empty = plain("No matching apps. Enable “Show all installed apps” or "
                      "install an application first.",
                      "muted");
  layout->addWidget(empty);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel);
  auto *use = buttons->addButton("Use this app", QDialogButtonBox::AcceptRole);
  use->setObjectName("defaultsUseApp");
  use->setProperty("primary", true);
  use->setDefault(true);
  use->setEnabled(false);
  layout->addWidget(buttons);
  for (const auto &value : applications) {
    const auto app = value.toObject();
    const auto ident = app["id"].toString();
    const auto support = strings(app["types"].toArray());
    bool recommended = ident == current;
    for (const auto &mime : mimeTypes)
      recommended |= support.contains(mime);
    const auto caption =
        ident == current ? "Current default" : app["description"].toString();
    auto *item = new QListWidgetItem(
        appIcon(app["icon"].toString()),
        app["name"].toString() +
            (caption.isEmpty() ? QString() : "\n" + caption),
        list);
    item->setData(Qt::UserRole, ident);
    item->setData(Qt::UserRole + 1, recommended);
    item->setToolTip(app["name"].toString() + "\n" +
                     app["description"].toString());
    item->setSizeHint({0, 60});
    if (ident == current)
      list->setCurrentItem(item);
  }
  auto filter = [&] {
    int shown = 0;
    for (int i = 0; i < list->count(); ++i) {
      auto *item = list->item(i);
      const bool visible =
          (all->isChecked() || item->data(Qt::UserRole + 1).toBool()) &&
          item->text().contains(find->text().trimmed(), Qt::CaseInsensitive);
      item->setHidden(!visible);
      if (visible)
        ++shown;
    }
    empty->setVisible(!shown);
    use->setEnabled(list->currentItem() && !list->currentItem()->isHidden());
  };
  connect(find, &QLineEdit::textChanged, &dialog, filter);
  connect(all, &QCheckBox::toggled, &dialog, filter);
  connect(list, &QListWidget::currentRowChanged, &dialog, filter);
  connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
  connect(list, &QListWidget::itemActivated, &dialog, [&] {
    if (use->isEnabled())
      dialog.accept();
  });
  filter();
  find->setFocus();
  if (dialog.exec() == QDialog::Accepted && list->currentItem() &&
      !list->currentItem()->isHidden()) {
    auto data = target;
    data["app"] = list->currentItem()->data(Qt::UserRole).toString();
    data["revision"] = revision;
    request("apply", data);
  }
}
void DefaultApps::focusSearch() {
  byType->click();
  search->setFocus();
}
void DefaultApps::showEvent(QShowEvent *event) {
  QWidget::showEvent(event);
  request("snapshot");
  QTimer::singleShot(0, this, [this] { arrange(); });
}
void DefaultApps::resizeEvent(QResizeEvent *event) {
  QWidget::resizeEvent(event);
  QTimer::singleShot(0, this, [this] { arrange(); });
}
