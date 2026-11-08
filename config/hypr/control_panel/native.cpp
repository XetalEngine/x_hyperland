#include "native.h"
#include "window_sizing.h"
#include "ram_cleaner.h"
#include "default_apps.h"
#include "grub_editor.h"
#include "runtime_log_guard.h"
#include "../theme/window_chrome.hpp"
#include "backend/mainwindow.h"
#include <QFileSystemWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QWindow>
#include <QtWidgets>
#include <memory>
#include <vector>

QString HyperPanel::terminal() { return root() + "/control_panel/terminal.py"; }
QString HyperPanel::accent() {
  QFile state(root() + "/theme/state.json"),
      palettes(root() + "/theme/palettes.json");
  state.open(QIODevice::ReadOnly);
  palettes.open(QIODevice::ReadOnly);
  auto choice = QJsonDocument::fromJson(state.readAll()).object();
  auto colors = QJsonDocument::fromJson(palettes.readAll()).object();
  auto style = choice.value("design").toString("raw");
  if (style != "raw")
    colors = colors.value(style).toObject();
  return colors.value(choice.value("mode").toString("dark"))
      .toObject()
      .value("Accent")
      .toString("#63d4cb");
}
QJsonObject HyperPanel::request(const QString &action,
                                const QJsonObject &input) {
  QProcess process;
  process.start("python3", {root() + "/control_panel/bridge.py", action});
  if (!process.waitForStarted(3000))
    return {{"error", "Could not start the Control Panel helper."}};
  process.write(QJsonDocument(input).toJson(QJsonDocument::Compact));
  process.closeWriteChannel();
  if (!process.waitForFinished(6000)) {
    process.kill();
    process.waitForFinished();
    return {{"error", "The Control Panel helper timed out."}};
  }
  auto result =
      QJsonDocument::fromJson(process.readAllStandardOutput()).object();
  if (result.isEmpty())
    result.insert("error",
                  QString::fromUtf8(process.readAllStandardError()).left(800));
  return result;
}
void HyperPanel::shortcut(const QJsonObject &input) {
  // The shared Apps editor owns its options, validation and Favorites format.
  auto *process = new QProcess(qApp);
  QObject::connect(process, &QProcess::started, process, [process, input] {
    process->write(QJsonDocument(input).toJson());
    process->closeWriteChannel();
  });
  QObject::connect(process,
                   qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
                   process, &QObject::deleteLater);
  process->start("python3", {root() + "/control_panel/bridge.py", "shortcut"});
}

class ToolButton final : public QPushButton {
  QString title, detail, iconName;

public:
  ToolButton(const QJsonObject &data, QWidget *parent)
      : QPushButton(parent), title(data["title"].toString()),
        detail(data["description"].toString()),
        iconName(data["icon"].toString()) {
    setText(title);
    setAccessibleName(title);
    setToolTip(detail);
    setMinimumHeight(72);
    setCursor(Qt::PointingHandCursor);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setObjectName("panelTool");
    setIcon(QIcon::fromTheme(data["icon"].toString(),
                             style()->standardIcon(QStyle::SP_ComputerIcon)));
  }
  void paintEvent(QPaintEvent *) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    QColor accent = palette().color(QPalette::Link);
    auto bounds = QRectF(rect()).adjusted(1, 1, -1, -1);
    auto fill = palette().color(QPalette::AlternateBase);
    auto border = palette().color(QPalette::Midlight);
    if (underMouse() || hasFocus() || isDown()) {
      fill = palette().color(QPalette::Highlight);
      border = accent;
    }
    p.setBrush(fill);
    p.setPen(QPen(border, hasFocus() ? 1.5 : 1));
    const auto corner = qApp->property("xetalPanelCardRadius");
    const auto radius = corner.isValid() ? corner.toInt() : 10;
    p.drawRoundedRect(bounds, radius, radius);
    QIcon::fromTheme(iconName, icon()).paint(&p, QRect(13, 14, 42, 42));
    auto f = font();
    f.setBold(true);
    p.setFont(f);
    p.setPen(palette().color(QPalette::Text));
    p.drawText(QRect(69, 12, width() - 80, 25), Qt::AlignVCenter,
               p.fontMetrics().elidedText(title, Qt::ElideRight, width() - 80));
    f.setBold(false);
    f.setPointSizeF(qMax(8., f.pointSizeF() - 1));
    p.setFont(f);
    p.setPen(palette().color(QPalette::PlaceholderText));
    p.drawText(
        QRect(69, 38, width() - 80, 22), Qt::AlignVCenter,
        p.fontMetrics().elidedText(detail, Qt::ElideRight, width() - 80));
  }
};

PanelController::PanelController(MainWindow *window)
    : QObject(window), owner(window) {
  auto *backend = owner->takeCentralWidget();
  owner->menuBar()->hide();
  owner->statusBar()->hide();
  owner->setWindowTitle("Control Panel — Hyper Fusion");
  owner->setWindowIcon(QIcon::fromTheme("preferences-system"));
  owner->setWindowFlags(Qt::Window | Qt::FramelessWindowHint);
  owner->setMinimumSize(740, 520);
  qApp->installEventFilter(new HyperPanel::WindowSizing(owner));
  owner->resize(1650, 910);
  auto *rootWidget = new QWidget(owner);
  rootWidget->setObjectName("hyperControlPanel");
  auto *layout = new QVBoxLayout(rootWidget);
  layout->setContentsMargins(18, 16, 18, 12);
  layout->setSpacing(14);
  auto *header = new QFrame(rootWidget);
  header->setObjectName("panelHeader");
  header->installEventFilter(this);
  auto *top = new QHBoxLayout(header);
  top->setContentsMargins(0, 0, 0, 0);
  back = new QPushButton("←", header);
  back->setToolTip("Back to all tools · Alt+Left");
  back->setFixedSize(36, 34);
  top->addWidget(back);
  auto *homeButton = new QPushButton("Control Panel", header);
  homeButton->setIcon(QIcon::fromTheme("preferences-system"));
  top->addWidget(homeButton);
  crumb = new QLabel("All tools", header);
  crumb->setObjectName("muted");
  crumb->setAttribute(Qt::WA_TransparentForMouseEvents);
  top->addWidget(crumb);
  top->addStretch();
  search = new QLineEdit(header);
  search->setPlaceholderText("Search settings and tools…");
  search->setClearButtonEnabled(true);
  search->setMaximumWidth(310);
  top->addWidget(search);
  top->addWidget(new FusionChrome::Controls(owner));
  layout->addWidget(header);
  stack = new QStackedWidget(rootWidget);
  layout->addWidget(stack, 1);
  auto *homeScroll = new QScrollArea(stack);
  homeScroll->setFrameShape(QFrame::NoFrame);
  homeScroll->setWidgetResizable(true);
  home = new QWidget(homeScroll);
  auto *homeLayout = new QVBoxLayout(home);
  homeLayout->setContentsMargins(0, 0, 8, 0);
  homeLayout->setSpacing(18);
  auto *intro = new QLabel("Your system. Every tool in one place.", home);
  intro->setObjectName("panelTitle");
  homeLayout->addWidget(intro);
  QFile source(HyperPanel::root() + "/control_panel/tools.json");
  source.open(QIODevice::ReadOnly);
  for (auto value : QJsonDocument::fromJson(source.readAll()).array()) {
    auto data = value.toObject();
    auto *box =
        new QGroupBox(data["title"].toString().replace("&", "&&"), home);
    auto *grid = new QGridLayout(box);
    grid->setSpacing(10);
    grid->setContentsMargins(10, 22, 10, 10);
    Group group{box, grid, {}};
    for (auto entry : data["tools"].toArray()) {
      auto tool = entry.toObject();
      auto *button = new ToolButton(tool, box);
      group.tools.append({tool, button});
      connect(button, &QPushButton::clicked, this,
              [this, tool] { open(tool["id"].toString()); });
    }
    groups.append(group);
    homeLayout->addWidget(box);
  }
  homeLayout->addStretch();
  homeScroll->setWidget(home);
  stack->addWidget(homeScroll);
  body = new QScrollArea(stack);
  body->setObjectName("panelBody");
  body->setFrameShape(QFrame::NoFrame);
  body->setWidgetResizable(true);
  body->setWidget(backend);
  stack->addWidget(body);
  // Keep the build controls visible while settings and output scroll above
  // them.
  isoActions = new QWidget(rootWidget);
  auto *actions =
      owner->findChild<QHBoxLayout *>("horizontalLayout_iso_buttons");
  if (actions) {
    auto *preview = new QPushButton("Preview installer…", isoActions);
    preview->setObjectName("isoPreviewButton");
    preview->setToolTip("Explore the restore wizard with sample drives. No ISO build or disk changes.");
    actions->insertWidget(1, preview);
    connect(preview, &QPushButton::clicked, owner, [this] {
      const auto script = HyperPanel::root() + "/control_panel/backend/iso/installer-graphical.py";
      if (!QProcess::startDetached("python3", {script, "preview"}))
        QMessageBox::warning(owner, "Installer preview", "Could not open the graphical preview.");
    });
    owner->findChild<QWidget *>("isoCreatorTab")->layout()->removeItem(actions);
    actions->setParent(nullptr);
    isoActions->setLayout(actions);
    actions->setContentsMargins(0, 0, 0, 0);
  }
  layout->addWidget(isoActions);
  isoActions->hide();
  for (const auto &name :
       {"tabWidget", "dashSubTabs", "packageManagerTabWidget", "servicesSubTabs"})
    if (auto *tabs = owner->findChild<QTabWidget *>(name))
      tabs->tabBar()->hide();
  auto *footer = new QHBoxLayout();
  count = new QLabel(rootWidget);
  count->setObjectName("muted");
  footer->addWidget(count);
  footer->addStretch();
  auto *about = new QPushButton("About", rootWidget);
  footer->addWidget(about);
  auto *grip = new QSizeGrip(rootWidget);
  footer->addWidget(grip);
  layout->addLayout(footer);
  owner->setCentralWidget(rootWidget);
  prepareTools();
  connect(back, &QPushButton::clicked, this, [this] { open(""); });
  connect(homeButton, &QPushButton::clicked, this, [this] { open(""); });
  connect(about, &QPushButton::clicked, this, [this] {
    QMessageBox::about(
        owner, "Hyper Fusion Control Panel",
        "<h2>Hyper Fusion</h2><p>A Hyprland control panel powered by the "
        "CachyOsTools C++ engine.</p><p>All system tools and the ISO builder "
        "are included in this desktop's source. GPLv3.</p>");
  });
  connect(search, &QLineEdit::textChanged, this, [this] {
    if (stack->currentIndex() != 0)
      open("");
    arrange();
  });
  auto *goHome = new QShortcut(QKeySequence("Alt+Left"), owner);
  connect(goHome, &QShortcut::activated, this, [this] { open(""); });
  auto *find = new QShortcut(QKeySequence::Find, owner);
  connect(find, &QShortcut::activated, this, [this] {
    if (current == "default-apps") {
      owner->findChild<DefaultApps *>()->focusSearch();
      return;
    }
    open("");
    search->setFocus();
  });
  owner->installEventFilter(this);
  homeScroll->viewport()->installEventFilter(this);
  themeProcess = new QProcess(this);
  connect(
      themeProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
      this, [this](int, QProcess::ExitStatus) {
        auto value =
            QJsonDocument::fromJson(themeProcess->readAllStandardOutput())
                .object();
        if (value.contains("stylesheet")) {
          QPalette palette;
          auto colors = value["colors"].toObject();
          auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
          for (auto it = colors.begin(); it != colors.end(); ++it) {
            int role = roles.keyToValue(it.key().toUtf8());
            if (role >= 0)
              palette.setColor(QPalette::All, QPalette::ColorRole(role),
                               QColor(it.value().toString()));
          }
          for (auto role : {QPalette::Text, QPalette::WindowText,
                            QPalette::ButtonText, QPalette::PlaceholderText})
            palette.setColor(QPalette::Disabled, role,
                             QColor(colors["Disabled"].toString()));
          qApp->setPalette(palette);
          qApp->setFont(QFont(value["font"].toString("Noto Sans"), 10));
          QStringList iconPaths;
          for (const auto &path:value["iconSearchPaths"].toArray()) iconPaths << path.toString();
          if (!iconPaths.isEmpty()) QIcon::setThemeSearchPaths(iconPaths);
          QIcon::setFallbackThemeName("hicolor");
          QIcon::setThemeName(value["iconTheme"].toString("Papirus-Dark"));
          qApp->setProperty("xetalPanelCardRadius", value["cardRadius"].toInt(10));
          qApp->setStyleSheet(value["stylesheet"].toString());
          owner->update();
        }
      });
  auto *watcher = new QFileSystemWatcher({HyperPanel::root() + "/theme"}, this);
  auto *debounce = new QTimer(this);
  debounce->setSingleShot(true);
  debounce->setInterval(80);
  connect(watcher, &QFileSystemWatcher::directoryChanged, debounce,
          [debounce] { debounce->start(); });
  connect(debounce, &QTimer::timeout, this, &PanelController::theme);
  theme();
  open("");
  QSettings settings("XetalHyperland", "ControlPanel");
  if (settings.value("preferences/windowSizeEnabled", true).toBool() &&
      settings.contains("window/geometry"))
    owner->restoreGeometry(settings.value("window/geometry").toByteArray());
  // Apply the roomier default once, then continue remembering user resizes.
  if (settings.value("window/layoutVersion", 1).toInt() < 3) {
    owner->resize(1650, 910);
    settings.setValue("window/layoutVersion", 3);
  }
  if (auto *screen = owner->screen())
    owner->resize(owner->size().boundedTo(screen->availableGeometry().size() -
                                          QSize(24, 48)));
  const auto startup =
      settings.value("preferences/startupTab", "home").toString();
  for (const auto &group : groups)
    for (const auto &tool : group.tools) {
      auto path = tool.data["path"].toArray();
      if (!path.isEmpty() && path[0].toString() == startup) {
        open(tool.data["id"].toString());
        goto startupDone;
      }
    }
startupDone:
  QTimer::singleShot(0, this, [this] { arrange(); });
}

void PanelController::prepareTools() {
  auto *rootTabs = owner->findChild<QTabWidget *>("tabWidget");
  rootTabs->addTab(new RamCleaner(HyperPanel::root() + "/control_panel/ram_cleaner.py", rootTabs), "RAM Cleaner");
  rootTabs->addTab(new DefaultApps(HyperPanel::root() + "/control_panel/default_apps.py", rootTabs), "Default Apps");
  rootTabs->addTab(new GrubEditor(HyperPanel::root() + "/control_panel/grub_editor.py", rootTabs), "GRUB Boot Editor");
  auto promote = [this, rootTabs](const QString &name, const QString &title) {
    auto *page = owner->findChild<QWidget *>(name);
    if (!page) return;
    auto *parent = page->parentWidget();
    while (parent && !qobject_cast<QTabWidget *>(parent)) parent = parent->parentWidget();
    if (auto *tabs = qobject_cast<QTabWidget *>(parent)) tabs->removeTab(tabs->indexOf(page));
    rootTabs->addTab(page, title);
  };
  promote("firewallSubTab", "Firewall");
  promote("networkSharesSubTab", "Network Shares");
  if (auto *tabs = owner->findChild<QTabWidget *>("tweaksTabWidget")) {
    for (int i = tabs->count() - 1; i >= 0; --i)
      if (tabs->tabText(i).contains("KDE", Qt::CaseInsensitive))
        tabs->removeTab(i);
    auto *hyprland = new QWidget(tabs);
    hyprland->setObjectName("hyprlandTweaksTab");
    auto *layout = new QVBoxLayout(hyprland);
    layout->addWidget(new RuntimeLogGuard(HyperPanel::root() + "/scripts/runtime-log-guard.py", hyprland));
    layout->addStretch();
    tabs->insertTab(0, hyprland, "Hyprland");
    tabs->setCurrentWidget(hyprland);
  }
  if (auto *page = owner->findChild<QWidget *>("kvmTab"))
    rootTabs->removeTab(rootTabs->indexOf(page));

  // Keep helper management with the helper it manages, including future
  // installed/not-installed status changes made by the C++ backend.
  auto *shared = owner->findChild<QBoxLayout *>("packageTopLayout");
  for (const auto &helper : {QString("yay"), QString("paru")}) {
    auto *page = owner->findChild<QWidget *>(helper + "Tab");
    auto *row = new QHBoxLayout;
    for (const auto &suffix : {"StatusLabel", "InstallButton", "ReinstallButton", "UninstallButton"}) {
      auto *widget = owner->findChild<QWidget *>(helper + suffix);
      shared->removeWidget(widget);
      const bool hidden = widget->isHidden();
      row->addWidget(widget);
      widget->setVisible(!hidden);
    }
    row->addStretch();
    qobject_cast<QVBoxLayout *>(page->layout())->insertLayout(0, row);
  }
  shared->addStretch();
  auto *deb = new QWidget(rootTabs);
  deb->setObjectName("debInstallTab");
  auto *debLayout = new QVBoxLayout(deb);
  auto *title = new QLabel("Install a Debian package", deb);
  title->setObjectName("panelTitle");
  debLayout->addWidget(title);
  auto *description = new QLabel(
      "Choose a trusted .deb application. Hyper Fusion checks its Debian requirements, "
      "maps supported dependencies to Arch packages, then converts and installs it with pacman. "
      "You can check compatibility first without changing your system.\n\n"
      "Experimental: some Debian applications need a package-specific recipe. "
      "Unresolved dependencies stop installation and are listed in the terminal.", deb);
  description->setWordWrap(true);
  debLayout->addWidget(description);
  auto *install = owner->findChild<QPushButton *>("installDebButton");
  shared->removeWidget(install);
  install->setText("Choose .deb and install…");
  install->setEnabled(true);
  install->setToolTip("Check dependencies, convert, and review the pacman installation in a terminal.");
  install->setIcon(QIcon::fromTheme("application-x-deb"));
  debLayout->addWidget(install, 0, Qt::AlignLeft);
  install->show();
  auto *checkDeb = new QPushButton("Check dependencies only…", deb);
  checkDeb->setObjectName("checkDebButton");
  debLayout->addWidget(checkDeb, 0, Qt::AlignLeft);
  connect(checkDeb, &QPushButton::clicked, owner, [install] {
    install->setProperty("debCheckOnly", true);
    install->click();
    install->setProperty("debCheckOnly", false);
  });
  debLayout->addStretch();
  rootTabs->addTab(deb, "Install .deb");

  // Separate options from actions instead of making this one unbreakable row.
  if (auto *actions = owner->findChild<QHBoxLayout *>("uninstallActionsLayout")) {
    auto *page = owner->findChild<QWidget *>("uninstallTab");
    auto *row = new QHBoxLayout;
    while (actions->count() > 3) {
      auto *item = actions->takeAt(3);
      row->addItem(item);
    }
    actions->addStretch();
    qobject_cast<QVBoxLayout *>(page->layout())->addLayout(row);
  }
  for (const auto &name : {"isoStatusLabel", "isoInfoText"}) {
    auto *output = owner->findChild<QTextEdit *>(name);
    output->setMinimumHeight(90);
    output->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
  }
  for (auto *view : owner->findChildren<QAbstractItemView *>()) {
    view->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    view->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    view->setTextElideMode(Qt::ElideRight);
    view->viewport()->installEventFilter(this);
  }
  auto *page = owner->findChild<QWidget *>("autostartSubTab");
  auto *startup = new QGroupBox("Desktop startup", page);
  auto *startupLayout = new QVBoxLayout(startup);
  numLockStartup = new QCheckBox("Turn on Num Lock when I log in", startup);
  numLockStartup->setObjectName("numLockStartupEnabled");
  startupLayout->addWidget(numLockStartup);
  numLockStatus = new QLabel("Use the Num Lock key to change it during your session.", startup);
  numLockStatus->setObjectName("muted");
  numLockStatus->setWordWrap(true);
  startupLayout->addWidget(numLockStatus);
  startupScreen = new QCheckBox("Show the animated dashboard when I log in", startup);
  startupScreen->setObjectName("startupScreenEnabled");
  startupLayout->addWidget(startupScreen);
  startupStatus = new QLabel("Super + D opens or hides the dashboard anytime.", startup);
  startupStatus->setObjectName("muted");
  startupStatus->setWordWrap(true);
  startupLayout->addWidget(startupStatus);
  qobject_cast<QVBoxLayout *>(page->layout())->insertWidget(0, startup);
  loadStartupPreference();
  connect(numLockStartup, &QCheckBox::toggled, this, [this](bool checked) {
    const auto result = HyperPanel::request("numlock-startup", {{"enabled", checked}});
    const QSignalBlocker guard(numLockStartup);
    if (result.contains("error")) {
      numLockStartup->setChecked(!checked);
      numLockStatus->setText("Could not save: " + result["error"].toString());
    } else {
      numLockStartup->setChecked(result["enabled"].toBool());
      numLockStatus->setText("Saved for future Hyprland logins. The Num Lock key still works normally.");
    }
  });
  connect(startupScreen, &QCheckBox::toggled, this, [this](bool checked) {
    const auto result = HyperPanel::request("startup-screen", {{"enabled", checked}});
    if (result.contains("error")) {
      QSignalBlocker guard(startupScreen);
      startupScreen->setChecked(!checked);
      startupStatus->setText("Could not save: " + result["error"].toString());
    } else {
      startupStatus->setText("Saved. Super + D opens or hides the dashboard anytime.");
    }
  });
}

void PanelController::loadStartupPreference() {
  const auto keyboard = HyperPanel::request("numlock-startup");
  const QSignalBlocker keyboardGuard(numLockStartup);
  numLockStartup->setEnabled(!keyboard.contains("error"));
  if (keyboard.contains("error"))
    numLockStatus->setText("Could not read Num Lock preference: " + keyboard["error"].toString());
  else {
    numLockStartup->setChecked(keyboard["enabled"].toBool());
    numLockStatus->setText("Use the Num Lock key to change it during your session.");
  }
  const auto result = HyperPanel::request("startup-screen");
  const QSignalBlocker guard(startupScreen);
  startupScreen->setEnabled(!result.contains("error"));
  if (result.contains("error"))
    startupStatus->setText("Could not read startup preference: " + result["error"].toString());
  else {
    startupScreen->setChecked(result["enabled"].toBool(true));
    startupStatus->setText("Super + D opens or hides the dashboard anytime.");
  }
}
void PanelController::theme() {
  if (themeProcess->state() != QProcess::NotRunning)
    return;
  themeProcess->start(
      "python3", {HyperPanel::root() + "/control_panel/bridge.py", "theme"});
  themeProcess->closeWriteChannel();
}
void PanelController::arrange() {
  const int columns = qBound(2, (home->width() - 28) / 300, 4);
  int shown = 0, total = 0;
  auto query = search->text().trimmed();
  for (auto &group : groups) {
    while (auto *item = group.grid->takeAt(0))
      delete item;
    int index = 0;
    for (auto &tool : group.tools) {
      total++;
      const auto path = tool.data["path"].toArray();
      const bool enabled =
          path.isEmpty() || QSettings("XetalHyperland", "ControlPanel")
                                .value("tabs/" + path[0].toString(), true)
                                .toBool();
      bool visible = enabled && (tool.data["title"].toString() + " " +
                                 tool.data["description"].toString() + " " +
                                 tool.data["keywords"].toString())
                                    .contains(query, Qt::CaseInsensitive);
      tool.button->setVisible(visible);
      if (visible) {
        group.grid->addWidget(tool.button, index / columns, index % columns);
        index++;
        shown++;
      }
    }
    group.box->setVisible(index > 0);
    for (int column = 0; column < 4; column++)
      group.grid->setColumnStretch(column, column < columns ? 1 : 0);
  }
  count->setText(query.isEmpty()
                     ? QString("%1 tools · CachyOsTools engine").arg(total)
                     : QString("%1 of %2 tools").arg(shown).arg(total));
}
void PanelController::open(const QString &id) {
  if (id.isEmpty()) {
    isoActions->hide();
    stack->setCurrentIndex(0);
    current.clear();
    crumb->setText("All tools");
    back->setEnabled(false);
    return;
  }
  for (const auto &group : groups)
    for (const auto &tool : group.tools)
      if (tool.data["id"] == id) {
        if (id == "preferences") {
          QMetaObject::invokeMethod(owner, "on_actionShowHideTabs_triggered");
          arrange();
          return;
        }
        if (id == "desktop-updates") {
          QProcess::startDetached(
              "python3", {HyperPanel::root() + "/theme/run.py", "python3",
                          HyperPanel::root() + "/updates/app.py"});
          return;
        }
        for (auto name : tool.data["path"].toArray()) {
          auto *page = owner->findChild<QWidget *>(name.toString());
          if (!page) {
            QMessageBox::warning(owner, "Tool unavailable",
                                 "Missing panel: " + name.toString());
            return;
          }
          auto *parent = page->parentWidget();
          while (parent && !qobject_cast<QTabWidget *>(parent))
            parent = parent->parentWidget();
          auto *tabs = qobject_cast<QTabWidget *>(parent);
          if (!tabs) {
            QMessageBox::warning(owner, "Tool unavailable",
                                 "This page has no tab container.");
            return;
          }
          if (tabs->indexOf(page) < 0)
            tabs->addTab(page, tool.data["title"].toString());
          tabs->setCurrentWidget(page);
        }
        stack->setCurrentIndex(1);
        body->verticalScrollBar()->setValue(0);
        body->horizontalScrollBar()->setValue(0);
        if (id == "autostart") loadStartupPreference();
        isoActions->setVisible(id == "iso");
        current = id;
        crumb->setText("›  " + tool.data["title"].toString());
        back->setEnabled(true);
        return;
      }
}
QJsonObject PanelController::inventory() const {
  QJsonArray tools;
  for (const auto &group : groups)
    for (const auto &tool : group.tools) {
      auto item = tool.data;
      QJsonArray missing;
      for (auto name : item["path"].toArray())
        if (!owner->findChild<QWidget *>(name.toString()))
          missing.append(name);
      item.insert("missing", missing);
      item.insert("hasIcon", QIcon::hasThemeIcon(item["icon"].toString()));
      tools.append(item);
    }
  QJsonObject views, tabs, cells;
  for (auto *view : owner->findChildren<QAbstractScrollArea *>()) {
    if (!view->isVisible() || view->objectName().isEmpty()) continue;
    views[view->objectName()] = QJsonObject{
      {"width", view->width()}, {"height", view->height()},
      {"horizontalRange", view->horizontalScrollBar()->maximum()},
      {"verticalRange", view->verticalScrollBar()->maximum()}};
  }
  for (auto *tab : owner->findChildren<QTabWidget *>()) {
    QJsonArray pages;
    for (int i = 0; i < tab->count(); ++i) pages.append(tab->widget(i)->objectName());
    tabs[tab->objectName()] = QJsonObject{{"pages", pages}, {"barVisible", tab->tabBar()->isVisible()}};
  }
  for (const auto &name : {"aliasTable", "configTable"}) {
    auto *table = owner->findChild<QTableWidget *>(name);
    if (table->isVisible() && table->rowCount() && table->cellWidget(0, 2)) {
      auto *button = table->cellWidget(0, 2);
      cells[name] = QJsonObject{{"height", button->height()}, {"width", button->width()},
                                {"neededHeight", button->sizeHint().height()}};
    }
  }
  return {
      {"tools", tools},
      {"views", views}, {"tabs", tabs}, {"cellActions", cells},
      {"section", current}, {"startupScreen", startupScreen->isChecked()},
      {"settingsFile", QSettings("XetalHyperland", "ControlPanel").fileName()},
      {"title", owner->windowTitle()},
      {"width", owner->width()},
      {"height", owner->height()}};
}
QJsonArray PanelController::verifyNavigation() {
  // Smoke validation switches pages with refresh signals blocked; never runs a
  // tool.
  std::vector<std::unique_ptr<QSignalBlocker>> blockers;
  for (auto *tabs : owner->findChildren<QTabWidget *>())
    blockers.emplace_back(new QSignalBlocker(tabs));
  const auto previous = current;
  QJsonArray errors;
  for (const auto &group : groups)
    for (const auto &tool : group.tools) {
      const auto path = tool.data["path"].toArray();
      if (path.isEmpty())
        continue;
      open(tool.data["id"].toString());
      for (const auto &name : path) {
        auto *page = owner->findChild<QWidget *>(name.toString());
        auto *parent = page ? page->parentWidget() : nullptr;
        while (parent && !qobject_cast<QTabWidget *>(parent))
          parent = parent->parentWidget();
        auto *tabs = qobject_cast<QTabWidget *>(parent);
        if (!tabs || tabs->currentWidget() != page)
          errors.append(tool.data["id"].toString() + ": " + name.toString());
      }
    }
  open(previous);
  return errors;
}
bool PanelController::eventFilter(QObject *object, QEvent *event) {
  if (object->objectName() == "panelHeader" && event->type() == QEvent::MouseButtonDblClick) {
    if (static_cast<QMouseEvent *>(event)->button() == Qt::LeftButton) {
      FusionChrome::toggleMaximized(owner);return true;
    }
  }
  if (event->type() == QEvent::ToolTip) {
    auto *view = qobject_cast<QAbstractItemView *>(object->parent());
    auto *help = static_cast<QHelpEvent *>(event);
    if (view) {
      const auto index = view->indexAt(help->pos());
      if (index.isValid()) {
        auto text = index.data(Qt::ToolTipRole).toString();
        if (text.isEmpty()) text = index.data().toString();
        QToolTip::showText(help->globalPos(), text, view);
        return true;
      }
    }
  }
  if (event->type() == QEvent::Resize)
    QTimer::singleShot(0, this, [this] {
      arrange();
      if (auto *modes = owner->findChild<QBoxLayout *>("isoModesLayout"))
        modes->setDirection(owner->width() < 1100 ? QBoxLayout::TopToBottom
                                                  : QBoxLayout::LeftToRight);
    });
  if (object->objectName() == "panelHeader" &&
      event->type() == QEvent::MouseButtonPress) {
    auto *mouse = static_cast<QMouseEvent *>(event);
    if (mouse->button() == Qt::LeftButton && owner->windowHandle())
      return owner->windowHandle()->startSystemMove();
  }
  return QObject::eventFilter(object, event);
}
