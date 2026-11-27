#include "native.h"
#include "tool_tile.h"
#include "tool_favorites.h"
#include "aur_page.h"
#include "software_page.h"
#include "window_sizing.h"
#include "ram_cleaner.h"
#include "default_apps.h"
#include "grub_editor.h"
#include "runtime_log_guard.h"
#include "system_tweaks_page.h"
#include "network_page.h"
#include "aur_helpers.h"
#include "deb_page.h"
#include "proton/page.h"
#include "rdp/page.h"
#include "ventoy_page.h"
#include "../theme/window_chrome.hpp"
#include "backend/mainwindow.h"
#include "backend/preferencesdialog.h"
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

PanelController::PanelController(MainWindow *window)
    : QObject(window), owner(window) {
  favorites = new ToolFavorites(HyperPanel::root(), this);
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
  auto *settingsButton = new QPushButton("Settings", header);
  settingsButton->setObjectName("panelSettingsButton");
  settingsButton->setIcon(QIcon::fromTheme("configure"));
  settingsButton->setToolTip("Control Panel settings · window buttons and shown tools");
  top->addWidget(settingsButton);
  connect(settingsButton, &QPushButton::clicked, this, [this] { open("preferences"); });
  windowControls = new FusionChrome::Controls(owner);
  top->addWidget(windowControls);
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
      connect(button->favoriteButton(), &QAbstractButton::clicked, this,
              [this, tool](bool checked) { favorites->setFavorite(tool["id"].toString(), checked); });
    }
    groups.append(group);
    homeLayout->addWidget(box);
  }
  connect(favorites, &ToolFavorites::changed, this, [this] {
    for (const auto &group : groups)
      for (const auto &tool : group.tools) {
        const auto id = tool.data["id"].toString();
        tool.button->setFavoriteState(favorites->contains(id), favorites->available(),
                                      favorites->pending(id), favorites->error());
      }
  });
  connect(favorites, &ToolFavorites::failed, this, [this](const QString &error) {
    QMessageBox::warning(owner, "Could not update Favorites", error);
  });
  homeEmpty = new QLabel(home);
  homeEmpty->setObjectName("panelEmptyTools");
  homeEmpty->setWordWrap(true);
  homeEmpty->setAlignment(Qt::AlignCenter);
  homeLayout->addWidget(homeEmpty);
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
  auto *grip = new QSizeGrip(rootWidget);
  footer->addWidget(grip);
  layout->addLayout(footer);
  owner->setCentralWidget(rootWidget);
  prepareTools();
  connect(owner, &MainWindow::preferencesChanged, this, &PanelController::refreshPreferences);
  refreshPreferences();
  connect(back, &QPushButton::clicked, this, [this] { open(""); });
  connect(homeButton, &QPushButton::clicked, this, [this] { open(""); });
  connect(search, &QLineEdit::textChanged, this, [this] {
    if (stack->currentIndex() != 0)
      open("");
    arrange();
  });
  auto *goHome = new QShortcut(QKeySequence("Alt+Left"), owner);
  connect(goHome, &QShortcut::activated, this, [this] { open(""); });
  auto *find = new QShortcut(QKeySequence::Find, owner);
  connect(find, &QShortcut::activated, this, [this] {
    if (current == "aur") {
      owner->findChild<QLineEdit *>("aurQuery")->setFocus();
      return;
    }
    if (current == "software") { owner->findChild<SoftwarePage *>()->focusSearch(); return; }
    if (current == "default-apps") {
      owner->findChild<DefaultApps *>()->focusSearch();
      return;
    }
    if (current == "proton") {
      owner->findChild<XetalProton::Page *>()->focusSearch();
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
  const auto startup = layoutPreferences.value("preferences/startupTab", "home").toString();
  if (startup != "home") open(startup);
  QTimer::singleShot(0, this, [this] { arrange(); });
}

void PanelController::prepareTools() {
  if (auto *link = owner->findChild<QPushButton *>("sensorsTweaksLink"))
    connect(link, &QPushButton::clicked, this, [this] {
      open("tweaks");
      if (auto *page = owner->findChild<SystemTweaksPage *>()) page->selectCategory("Performance");
    });
  auto *rootTabs = owner->findChild<QTabWidget *>("tabWidget");
  rootTabs->addTab(new RamCleaner(HyperPanel::root() + "/control_panel/ram_cleaner.py", rootTabs), "RAM Cleaner");
  rootTabs->addTab(new DefaultApps(HyperPanel::root() + "/control_panel/default_apps.py", rootTabs), "Default Apps");
  rootTabs->addTab(new XetalProton::Page(rootTabs), "Proton");
  rootTabs->addTab(new FusionRdp::Page(HyperPanel::root(), rootTabs), "RDP");
  rootTabs->addTab(new VentoyPage(HyperPanel::root(), rootTabs), "Ventoy USB");
  rootTabs->addTab(new GrubEditor(HyperPanel::root() + "/control_panel/grub_editor.py", rootTabs), "GRUB Boot Editor");
  if (auto *page = owner->findChild<QWidget *>("networkTab")) {
    page->setProperty("fusionNetworkReplaced", true);
    auto *legacyTabs = owner->findChild<QWidget *>("networkTabWidget");
    auto *network = new NetworkPage(owner, page);
    page->layout()->removeWidget(legacyTabs); legacyTabs->hide();
    page->layout()->addWidget(network);
    auto *sections = network->findChild<QTabWidget *>("networkSections");
    QSettings settings("XetalHyperland", "ControlPanel");
    for (const auto &name : {"firewallSubTab", "networkSharesSubTab"})
      sections->setTabVisible(sections->indexOf(owner->findChild<QWidget *>(name)),
                             settings.value(QString("tabs/") + name, true).toBool());
    connect(network, &NetworkPage::refreshRequested, this, [this](const QString &section) {
      if (section == "Connections") {
        QMetaObject::invokeMethod(owner, "refreshNetworkInfo");
        QMetaObject::invokeMethod(owner, "refreshInterfaceConfig");
        QMetaObject::invokeMethod(owner, "refreshConnectionsList");
        QMetaObject::invokeMethod(owner, "refreshWifiNetworks", Q_ARG(bool, false));
      } else if (section == "Virtual networks") {
        QMetaObject::invokeMethod(owner, "refreshBridges");
        QMetaObject::invokeMethod(owner, "refreshLibvirtNetworks");
      } else if (section == "Diagnostics") {
        QMetaObject::invokeMethod(owner, "refreshNetworkInfo");
        QMetaObject::invokeMethod(owner, "refreshInterfaceStats");
        QMetaObject::invokeMethod(owner, "refreshOpenPorts");
      } else if (section == "Shared folders") {
        QMetaObject::invokeMethod(owner, "refreshNetworkShares");
      }
    });
  }
  if (auto *page = owner->findChild<QWidget *>("tweaksTab")) {
    page->setProperty("fusionTweaksReplaced", true);
    // Keep legacy Ui pointers valid for the copied backend, but retire every
    // old control and connection from the visible workflow.
    auto *retired = new QWidget(owner); retired->setObjectName("retiredTweaks"); retired->hide();
    std::function<void(QLayout *)> retire = [&](QLayout *layout) {
      while (auto *item = layout->takeAt(0)) {
        if (auto *widget = item->widget()) { widget->setParent(retired); widget->hide(); }
        if (item->layout()) retire(item->layout());
        delete item;
      }
    };
    retire(page->layout());
    auto *tweaks = new SystemTweaksPage(HyperPanel::root(), page);
    page->layout()->addWidget(tweaks);
    connect(tweaks, &SystemTweaksPage::openTool, this, &PanelController::open);
  }
  if (auto *page = owner->findChild<QWidget *>("kvmTab"))
    rootTabs->removeTab(rootTabs->indexOf(page));

  // Keep legacy Ui pointers alive, but use one shared AUR workflow. It has its
  // own status/results, so opening it cannot display Pacman's unrelated output.
  auto *shared = owner->findChild<QBoxLayout *>("packageTopLayout");
  auto *retiredHelpers = new QWidget(owner);
  retiredHelpers->setObjectName("retiredAurHelpers"); retiredHelpers->hide();
  auto *packageTabs = owner->findChild<QTabWidget *>("packageManagerTabWidget");
  for (const auto &helper : {QString("yay"), QString("paru")}) {
    auto *page = owner->findChild<QWidget *>(helper + "Tab");
    packageTabs->removeTab(packageTabs->indexOf(page));
    page->setParent(retiredHelpers); page->hide();
    for (const auto &suffix : {"StatusLabel", "InstallButton", "ReinstallButton", "UninstallButton"}) {
      auto *widget = owner->findChild<QWidget *>(helper + suffix);
      shared->removeWidget(widget);
      widget->setParent(retiredHelpers); widget->hide();
    }
  }
  auto *aur = new AurPage(HyperPanel::root(), HyperPanel::terminal(), rootTabs);
  connect(aur, &AurPage::clearCacheRequested, owner->findChild<QPushButton *>("pacDocTrim"), &QPushButton::click);
  rootTabs->addTab(aur, "Yay & Paru");
  shared->addStretch();
  auto *install = owner->findChild<QPushButton *>("installDebButton");
  shared->removeWidget(install);
  auto *deb = new DebInstallerPage(HyperPanel::root(), install, rootTabs);
  rootTabs->addTab(deb, "Install .deb");

  {
    const QSignalBlocker rootGuard(rootTabs), packageGuard(packageTabs);
    owner->findChild<QWidget *>("packageManagerTab")->setProperty("fusionSoftwareReplaced", true);
    auto *oldPacman = owner->findChild<QWidget *>("pacmanTab");
    packageTabs->removeTab(packageTabs->indexOf(oldPacman)); oldPacman->setParent(retiredHelpers); oldPacman->hide();
    for (const auto &name : {"uninstallTab", "pacmanDoctorTab"}) rootTabs->removeTab(rootTabs->indexOf(owner->findChild<QWidget *>(name)));
    auto *software = new SoftwarePage(owner, HyperPanel::root(), HyperPanel::terminal(), rootTabs);
    rootTabs->addTab(software, "Software");
    auto *sections = software->findChild<QTabWidget *>("softwareSections");
    QSettings settings("XetalHyperland", "ControlPanel");
    for (const auto &name : {"uninstallTab", "pacmanDoctorTab"})
      sections->setTabVisible(sections->indexOf(owner->findChild<QWidget *>(name)), settings.value(QString("tabs/") + name, true).toBool());
    connect(software, &SoftwarePage::openTool, this, &PanelController::open);
    connect(software, &SoftwarePage::installDebRequested, this, [this, deb](const QString &id) {
      open("deb");
      deb->selectApp(id);
    });
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
      const bool enabled = layoutPreferences.value(AppPreferences::toolKey(tool.data["id"].toString()), true).toBool();
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
  count->setText(shown == total && query.isEmpty()
                     ? QString("%1 tools · CachyOsTools engine").arg(total)
                     : QString("%1 of %2 tools shown").arg(shown).arg(total));
  homeEmpty->setText(query.isEmpty() ? "Your tools are hidden. Open Settings → Workspace to show them again."
                                   : "No matching tools. Try another search, or show more tools in Settings → Workspace.");
  homeEmpty->setVisible(shown == 0);
}
void PanelController::refreshPreferences() {
  QSettings settings("XetalHyperland", "ControlPanel");
  layoutPreferences = AppPreferences::read(settings);
  windowControls->setVisible(layoutPreferences.value("appearance/showWindowControls", true).toBool());
  arrange();
}
void PanelController::open(const QString &id) {
  if (id == "rdp-host") {
    open("rdp");
    if (auto *page = owner->findChild<FusionRdp::Page *>()) page->showHosting();
    return;
  }
  // Existing Apps shortcuts/bookmarks keep working after the pages merge.
  if (id == "yay" || id == "paru") { open("aur"); return; }
  if (id == "pacman" || id == "remove" || id == "repair") {
    open("software");
    owner->findChild<SoftwarePage *>()->openSection(id == "remove" ? 1 : id == "repair" ? 2 : 0);
    return;
  }
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
          refreshPreferences();
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
          // Hiding a home tile must not disable a tool or its saved shortcuts.
          tabs->setTabVisible(tabs->indexOf(page), true);
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
      item.insert("shown", !tool.button->isHidden());
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
      {"windowControlsShown", !windowControls->isHidden()},
      {"settingsButtonAvailable", !owner->findChild<QWidget *>("panelSettingsButton")->isHidden()},
      {"settingsFile", QSettings("XetalHyperland", "ControlPanel").fileName()},
      {"title", owner->windowTitle()},
      {"width", owner->width()},
      {"height", owner->height()}};
}
QJsonArray PanelController::verifyNavigation() {
  // Smoke validation switches pages with refresh signals blocked; never runs a
  // tool.
  const auto previousAudit = owner->property("panelNavigationAudit");
  owner->setProperty("panelNavigationAudit", true);
  const auto restoreAudit = qScopeGuard([&] { owner->setProperty("panelNavigationAudit", previousAudit); });
  std::vector<std::unique_ptr<QSignalBlocker>> blockers;
  QMap<QTabWidget *, QWidget *> previousPages;
  for (auto *tabs : owner->findChildren<QTabWidget *>()) {
    previousPages[tabs] = tabs->currentWidget();
    blockers.emplace_back(new QSignalBlocker(tabs));
  }
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
  for (auto it = previousPages.begin(); it != previousPages.end(); ++it)
    if (it.value()) it.key()->setCurrentWidget(it.value());
  open(previous);
  return errors;
}
bool PanelController::eventFilter(QObject *object, QEvent *event) {
  if (object == owner && event->type() == QEvent::WindowActivate) favorites->refresh();
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
