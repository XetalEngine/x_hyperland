#include "../native.h"
#include "../../theme/about.hpp"
#include <QProcess>
#include "preferencesdialog.h"
#include "themepresets.h"

#include <QtWidgets>
#include <utility>

namespace {
QString translated(const char *text) { return QCoreApplication::translate("PreferencesDialog", text); }
QString controlObjectName(QString key) { return key.replace('/', '_'); }
QLabel *hint(const QString &text, QWidget *parent) {
    auto *label = new QLabel(text, parent);
    label->setTextFormat(Qt::PlainText);
    label->setWordWrap(true);
    label->setProperty("prefHint", true);
    label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    return label;
}
QHBoxLayout *field(QGroupBox *card, const QString &title, QWidget *control) {
    auto *row = new QHBoxLayout;
    auto *label = new QLabel(title, card);
    label->setWordWrap(true);
    label->setBuddy(control);
    row->addWidget(label, 1);
    control->setMinimumWidth(170);
    control->setMaximumWidth(260);
    control->setAccessibleName(title);
    row->addWidget(control, 1);
    qobject_cast<QVBoxLayout *>(card->layout())->addLayout(row);
    return row;
}
}

QList<AppPreferences::Tab> AppPreferences::tabs() {
    return {
        {"dashboardTab", translated("Dashboard"), translated("Overview and system tools")},
        {"driveToolsTab", translated("Drives"), translated("Disks, partitions and mounts")},
        {"shellToolsTab", translated("Shell"), translated("Aliases and shell configuration")},
        {"servicesTab", translated("Services"), translated("Services and startup applications")},
        {"tweaksTab", translated("Tweaks"), translated("Performance and desktop settings")},
        {"configTab", translated("System Config"), translated("Configuration file editors")},
        {"logsTab", translated("Logs"), translated("System logs and journal")},
        {"backupTab", translated("Backup"), translated("Save system files")},
        {"restoreTab", translated("Restore"), translated("Restore a saved backup")},
        {"isoCreatorTab", translated("System ISO"), translated("Clone and preview installers")},
        {"packageManagerTab", translated("Package Updates"), translated("System upgrades and Arch news")},
        {"softwareTab", translated("Software"), translated("Browse, installed packages and repairs")},
        {"pacmanDoctorTab", translated("Package Repair"), translated("Mirrors, keyrings and diagnostics")},
        {"debInstallTab", translated("Install .deb"), translated("Convert a Debian package")},
        {"aurTab", translated("Yay & Paru"), translated("Search packages and manage AUR helpers")},
        {"firewallSubTab", translated("Firewall"), translated("Firewall rules and configuration")},
        {"networkSharesSubTab", translated("Network Shares"), translated("Discover, mount and share folders")},
        {"uninstallTab", translated("Installed Software"), translated("Remove installed packages")},
        {"cleanerTab", translated("Cleaner"), translated("Review caches and disk usage")},
        {"networkTab", translated("Network"), translated("Connections, shares and firewall")},
    };
}

QList<AppPreferences::Tool> AppPreferences::tools() {
    QFile file(HyperPanel::root() + "/control_panel/tools.json");
    if (!file.open(QIODevice::ReadOnly)) return {};
    QList<Tool> result;
    for (const auto &group : QJsonDocument::fromJson(file.readAll()).array())
        for (const auto &entry : group.toObject()["tools"].toArray()) {
            const auto value = entry.toObject();
            Tool tool{value["id"].toString(), value["title"].toString(),
                      value["description"].toString(), value["icon"].toString(), {}};
            for (const auto &name : value["path"].toArray()) tool.path << name.toString();
            if (!tool.id.isEmpty()) result.append(tool);
        }
    return result;
}

QString AppPreferences::toolKey(const QString &id) { return "tools/visible/" + id; }

bool AppPreferences::toolVisible(QSettings &settings, const Tool &tool) {
    const auto key = toolKey(tool.id);
    if (settings.contains(key)) return settings.value(key).toBool();
    // Keep older family choices until an individual tool choice is saved.
    for (const auto &name : tool.path)
        if (!settings.value("tabs/" + name, true).toBool()) return false;
    return true;
}

QString AppPreferences::startupTool(const QString &value) {
    const auto catalog = tools();
    for (const auto &tool : catalog) if (tool.id == value && !tool.path.isEmpty()) return value;
    // Previous versions stored backend tab names, sometimes a parent tab.
    for (const auto &tool : catalog) if (tool.path.contains(value)) return tool.id;
    if (value == "uninstallTab" || value == "pacmanDoctorTab") return "software";
    return "home";
}

QVariantMap AppPreferences::defaults() {
    QVariantMap values{
        {"preferences/windowSizeEnabled", true}, {"preferences/autoSaveEnabled", true},
        {"appearance/showWindowControls", true},
        {"preferences/debugIsoCreatorEnabled", false}, {"preferences/startupTab", "home"},
        {"language/code", "en"}, {"theme/preset", 0}, {"theme/accent", "#27ae60"},
        {"theme/background", ""}, {"theme/text", ""},
        {"defaults/drives/minimumEnabled", true}, {"defaults/drives/minimumMB", 500},
        {"defaults/config/editor", "nano"}, {"defaults/packages/searchMode", 2},
        {"defaults/packages/searchType", 1},
        {"defaults/iso/folderMinimumMB", 500}, {"defaults/iso/fileMinimumMB", 100},
    };
    for (const auto &tab : tabs()) values.insert("tabs/" + tab.id, true);
    for (const auto &tool : tools()) values.insert(toolKey(tool.id), true);
    return values;
}

QVariantMap AppPreferences::read(QSettings &settings) {
    QVariantMap values = defaults();
    for (auto it = values.begin(); it != values.end(); ++it) {
        QVariant stored = settings.value(it.key(), it.value());
        if (it.value().userType() == QMetaType::Bool) it.value() = stored.toBool();
        else if (it.value().userType() == QMetaType::Int) {
            bool ok;
            int number = stored.toInt(&ok);
            if (ok) it.value() = number;
        } else it.value() = stored.toString();
    }
    auto bound = [&](const QString &key, int low, int high) { values[key] = qBound(low, values[key].toInt(), high); };
    bound("theme/preset", 0, THEME_PRESET_COUNT - 1);
    bound("defaults/drives/minimumMB", 1, 999999);
    bound("defaults/packages/searchMode", 0, 2);
    bound("defaults/packages/searchType", 0, 1);
    bound("defaults/iso/folderMinimumMB", 1, 1000000);
    bound("defaults/iso/fileMinimumMB", 10, 1000000);
    for (const QString &key : {QString("theme/accent"), QString("theme/background"), QString("theme/text")}) {
        QString color = values[key].toString();
        if (!color.isEmpty() && QColor(color).isValid()) values[key] = QColor(color).name();
        else if (!color.isEmpty() || key == "theme/accent") values[key] = defaults()[key];
    }
    if (!QStringList{"en", "pt_BR", "de"}.contains(values["language/code"].toString())) values["language/code"] = "en";
    if (!QStringList{"nano", "kate", "mousepad", "geany"}.contains(values["defaults/config/editor"].toString())) values["defaults/config/editor"] = "nano";
    QStringList visible;
    for (const auto &tab : tabs()) if (values["tabs/" + tab.id].toBool()) visible << tab.id;
    if (visible.isEmpty()) { values["tabs/dashboardTab"] = true; visible << "dashboardTab"; }
    for (const auto &tool : tools()) values[toolKey(tool.id)] = toolVisible(settings, tool);
    const auto startup = startupTool(values["preferences/startupTab"].toString());
    values["preferences/startupTab"] = values.value(toolKey(startup), false).toBool() ? startup : "home";
    return values;
}

bool AppPreferences::write(QSettings &settings, const QVariantMap &values) {
    // Keep unrelated application settings, geometry and profiles intact.
    const auto known = defaults();
    QVariantMap previous;
    for (auto it = known.begin(); it != known.end(); ++it) {
        if (settings.contains(it.key())) previous[it.key()] = settings.value(it.key());
        settings.setValue(it.key(), values.value(it.key(), it.value()));
    }
    settings.sync();
    if (settings.status() == QSettings::NoError) return true;
    // QSettings also caches values in memory. A failed save must not leave the
    // rejected draft available to other readers or a later settings writer.
    for (auto it = known.begin(); it != known.end(); ++it) {
        if (previous.contains(it.key())) settings.setValue(it.key(), previous[it.key()]);
        else settings.remove(it.key());
    }
    settings.sync();
    return false;
}

PreferencesDialog::PreferencesDialog(const QVariantMap &values, Save save, QWidget *parent)
    : QDialog(parent), m_saved(values), m_draft(values), m_save(std::move(save)) {
    setObjectName("preferencesDialog");
    setWindowTitle(tr("Control Panel Settings"));
    setWindowFlag(Qt::WindowContextHelpButtonHint, false);
    setMinimumSize(720, 520);
    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(22, 20, 22, 16);
    outer->setSpacing(18);
    auto *header = new QHBoxLayout;
    auto *titles = new QVBoxLayout;
    auto *title = new QLabel(tr("Control Panel Settings"), this);
    title->setObjectName("preferencesTitle");
    titles->addWidget(title);
    titles->addWidget(hint(tr("Your workspace. Your way."), this));
    header->addLayout(titles, 1);
    m_search = new QLineEdit(this);
    m_search->setObjectName("preferencesSearch");
    m_search->setPlaceholderText(tr("Find a setting…"));
    m_search->setAccessibleName(tr("Search preferences"));
    m_search->setToolTip(tr("Search all categories. Ctrl+F to focus."));
    m_search->setClearButtonEnabled(true);
    m_search->installEventFilter(this);
    m_search->setMaximumWidth(300);
    m_search->setMinimumWidth(200);
    header->addWidget(m_search);
    outer->addLayout(header);

    auto *body = new QHBoxLayout;
    body->setSpacing(22);
    auto *sidebar = new QFrame(this);
    sidebar->setObjectName("preferencesSidebar");
    sidebar->setFixedWidth(184);
    auto *side = new QVBoxLayout(sidebar);
    side->setContentsMargins(8, 14, 8, 14);
    side->addWidget(hint(tr("PERSONALIZE"), sidebar));
    m_navigation = new QListWidget(sidebar);
    m_navigation->setObjectName("preferencesNavigation");
    m_navigation->setAccessibleName(tr("Preference categories"));
    m_navigation->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_navigation->setSpacing(5);
    side->addWidget(m_navigation, 1);
    side->addWidget(hint(tr("Settings are saved for your user account."), sidebar));
    body->addWidget(sidebar);
    m_pages = new QStackedWidget(this);
    m_pages->setObjectName("preferencesPages");
    body->addWidget(m_pages, 1);
    outer->addLayout(body, 1);

    buildGeneral(); buildAppearance(); buildWorkspace(); buildTools(); buildIso();
    for (auto &page : m_sections) page.layout->addStretch();
    auto *empty = new QWidget(m_pages);
    auto *emptyLayout = new QVBoxLayout(empty);
    emptyLayout->addStretch();
    auto *emptyTitle = new QLabel(tr("No matching settings"), empty);
    emptyTitle->setAlignment(Qt::AlignCenter);
    emptyLayout->addWidget(emptyTitle);
    auto *emptyHint = hint(tr("Try “theme”, “startup”, “drives” or “dummy ISO”."), empty);
    emptyHint->setAlignment(Qt::AlignCenter);
    emptyLayout->addWidget(emptyHint);
    auto *clear = new QPushButton(tr("Clear search"), empty);
    emptyLayout->addWidget(clear, 0, Qt::AlignCenter);
    emptyLayout->addStretch();
    m_pages->addWidget(empty);
    connect(clear, &QPushButton::clicked, m_search, &QLineEdit::clear);

    auto *footer = new QHBoxLayout;
    m_reset = new QPushButton(tr("Reset page"), this);
    m_reset->setObjectName("preferencesReset");
    m_reset->setToolTip(tr("Stage this page's defaults. Apply to save them."));
    footer->addWidget(m_reset);
    m_status = new QLabel(this);
    m_status->setObjectName("preferencesStatus");
    m_status->setProperty("prefHint", true);
    m_status->setWordWrap(true);
    m_status->setMinimumWidth(100);
    footer->addWidget(m_status, 1);
    auto *about = new QPushButton(tr("About…"), this);
    about->setObjectName("aboutApplicationButton");
    about->setAutoDefault(false);
    footer->addWidget(about);
    connect(about, &QPushButton::clicked, this, [this] {
        FusionAbout::show(this, HyperPanel::root(), "Control Panel",
            "System tools and desktop management for Hyper Fusion.",
            "Powered by the CachyOsTools C++ engine. All system tools and the "
            "ISO builder are included in this desktop's source. GPLv3.");
    });
    m_cancel = new QPushButton(tr("Cancel"), this);
    m_cancel->setObjectName("preferencesCancel");
    m_apply = new QPushButton(tr("Apply"), this);
    m_apply->setObjectName("preferencesApply");
    m_done = new QPushButton(tr("Done"), this);
    m_done->setObjectName("preferencesDone");
    m_done->setDefault(true);
    footer->addWidget(m_cancel); footer->addWidget(m_apply); footer->addWidget(m_done);
    outer->addLayout(footer);
    connect(m_cancel, &QPushButton::clicked, this, &QDialog::reject);
    connect(m_apply, &QPushButton::clicked, this, [this]() { apply(); });
    connect(m_done, &QPushButton::clicked, this, [this]() { if (apply()) accept(); });
    connect(m_reset, &QPushButton::clicked, this, &PreferencesDialog::resetPage);
    connect(m_navigation, &QListWidget::currentRowChanged, this, [this](int index) {
        if (index >= 0) { m_pages->setCurrentIndex(index); m_reset->setEnabled(true); }
    });
    connect(m_search, &QLineEdit::textChanged, this, &PreferencesDialog::filter);
    auto *find = new QShortcut(QKeySequence::Find, this);
    connect(find, &QShortcut::activated, this, [this]() { m_search->setFocus(); m_search->selectAll(); });
    loadWidgets();
    m_navigation->setCurrentRow(0);
    styleDialog();
    updateFooter();
    const auto available = (parent && parent->screen() ? parent->screen() : QGuiApplication::primaryScreen())->availableGeometry().size();
    resize(qMin(960, available.width() - 40), qMin(740, available.height() - 60));
}

int PreferencesDialog::addPage(const QString &title, const QString &description, const QString &icon) {
    const int index = m_sections.size();
    auto *scroll = new QScrollArea(m_pages);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *page = new QWidget(scroll);
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(0, 0, 8, 4);
    layout->setSpacing(12);
    auto *heading = new QLabel(title, page);
    heading->setProperty("prefHeading", true);
    layout->addWidget(heading);
    layout->addWidget(hint(description, page));
    scroll->setWidget(page);
    m_pages->addWidget(scroll);
    m_sections.append({page, layout, title, description, {}});
    const QStyle::StandardPixmap fallbacks[] = {QStyle::SP_ComputerIcon, QStyle::SP_DesktopIcon,
        QStyle::SP_DirIcon, QStyle::SP_FileDialogDetailedView, QStyle::SP_DriveCDIcon};
    auto *item = new QListWidgetItem(QIcon::fromTheme(icon, style()->standardIcon(fallbacks[index])), title, m_navigation);
    item->setSizeHint(QSize(150, 48));
    item->setToolTip(description);
    return index;
}

QGroupBox *PreferencesDialog::addCard(int page, const QString &title, const QString &description) {
    auto *card = new QGroupBox(title, m_sections[page].widget);
    card->setProperty("preferencePage", page);
    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(14, 18, 14, 12);
    layout->setSpacing(10);
    if (!description.isEmpty()) layout->addWidget(hint(description, card));
    m_sections[page].layout->addWidget(card);
    m_cards.append({card, page});
    return card;
}

void PreferencesDialog::registerControl(QGroupBox *card, const QString &key, QWidget *control) {
    control->setObjectName(key == "preferences/debugIsoCreatorEnabled" ? "debugIsoCreatorCheck" : controlObjectName(key));
    m_controls[key] = control;
    m_sections[card->property("preferencePage").toInt()].keys.append(key);
}

QCheckBox *PreferencesDialog::addCheck(QGroupBox *card, const QString &key, const QString &title, const QString &description) {
    auto *box = new QCheckBox(title, card);
    registerControl(card, key, box);
    auto *layout = qobject_cast<QVBoxLayout *>(card->layout());
    layout->addWidget(box);
    if (!description.isEmpty()) { box->setToolTip(description); layout->addWidget(hint(description, card)); }
    connect(box, &QCheckBox::toggled, this, [this, key](bool checked) {
        if (m_loading) return;
        m_draft[key] = checked; edited();
    });
    return box;
}

QComboBox *PreferencesDialog::addCombo(QGroupBox *card, const QString &key, const QString &title,
                                      const QList<QPair<QString, QVariant>> &choices) {
    auto *combo = new QComboBox(card);
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setMinimumContentsLength(12);
    registerControl(card, key, combo);
    for (const auto &choice : choices) combo->addItem(choice.first, choice.second);
    field(card, title, combo);
    connect(combo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, key, combo](int index) {
        if (m_loading || index < 0) return;
        m_draft[key] = combo->currentData();
        if (key == "theme/preset" && index < THEME_PRESET_COUNT - 1) {
            m_draft["theme/accent"] = THEME_PRESETS[index].accent;
            m_draft["theme/background"] = THEME_PRESETS[index].background;
            m_draft["theme/text"] = THEME_PRESETS[index].text;
            loadWidgets();
        }
        edited();
    });
    return combo;
}

void PreferencesDialog::addSpin(QGroupBox *card, const QString &key, const QString &title, int minimum, int maximum) {
    auto *spin = new QSpinBox(card);
    spin->setRange(minimum, maximum);
    spin->setSuffix(tr(" MB"));
    spin->setKeyboardTracking(false);
    registerControl(card, key, spin);
    field(card, title, spin);
    connect(spin, QOverload<int>::of(&QSpinBox::valueChanged), this, [this, key](int value) {
        if (m_loading) return;
        m_draft[key] = value; edited();
    });
}

void PreferencesDialog::buildGeneral() {
    int page = addPage(tr("General"), tr("Choose how the app opens and how your preferences are saved."), "preferences-system");
    auto *startup = addCard(page, tr("When you open the app"));
    addCheck(startup, "preferences/windowSizeEnabled", tr("Remember window size"), tr("Return to your previous layout on the current display."));
    addCombo(startup, "preferences/startupTab", tr("Start on"), {});
    auto *saving = addCard(page, tr("Saving preferences"));
    addCheck(saving, "preferences/autoSaveEnabled", tr("Save changes automatically"), tr("Turn this off to review changes, then use Apply or Save & Close."));
    auto *language = addCard(page, tr("Language"), tr("Language changes take effect after restarting the app."));
    addCombo(language, "language/code", tr("Interface language"), {{"English", "en"}, {"Português (Brasil)", "pt_BR"}, {"Deutsch", "de"}});
}

void PreferencesDialog::buildAppearance() {
    int nativePage = addPage(tr("Appearance"), tr("Follows your Hyprland desktop theme."), "preferences-desktop-theme");
    auto *controls = addCard(nativePage, tr("Window buttons"));
    addCheck(controls, "appearance/showWindowControls", tr("Show window buttons (minimize, maximize/restore, close)"),
             tr("The header makes room automatically. Settings stays available when the buttons are hidden."));
    controls->layout()->addWidget(hint(tr("In KDE mode, use the window's gear menu to add a title bar above the app. Hold Super to reach the gear when the title bar and overlay controls are off."), controls));
    auto *nativeCard = addCard(nativePage, tr("Desktop appearance"), tr("Desktop themes, including Binary Knife, are managed in Fusion Settings."));
    m_themePreview = new QWidget(nativeCard); m_themePreview->hide();
    auto *openTheme = new QPushButton(tr("Open Fusion Settings theme settings"), nativeCard);
    nativeCard->layout()->addWidget(openTheme);
    connect(openTheme, &QPushButton::clicked, this, [] { QProcess::startDetached(HyperPanel::root()+"/scripts/control-center.sh", {"--tab", "theme"}); });
    return;

    int page = addPage(tr("Appearance"), tr("Keep the Xetal colors or make the app your own."), "preferences-desktop-theme");
    auto *theme = addCard(page, tr("Theme"));
    QList<QPair<QString, QVariant>> presets;
    for (int i = 0; i < THEME_PRESET_COUNT; ++i) presets.append({translated(THEME_PRESETS[i].name), i});
    addCombo(theme, "theme/preset", tr("Preset"), presets);
    m_themePreview = new QFrame(theme);
    m_themePreview->setObjectName("preferencesThemePreview");
    auto *sample = new QVBoxLayout(m_themePreview);
    sample->setContentsMargins(18, 14, 18, 14);
    auto *sampleTitle = new QLabel(tr("XETAL ENGINE"), m_themePreview);
    sampleTitle->setObjectName("previewAccent");
    sample->addWidget(sampleTitle);
    sample->addWidget(new QLabel(tr("A familiar workspace, in your colors."), m_themePreview));
    auto *progress = new QProgressBar(m_themePreview);
    progress->setRange(0, 100); progress->setValue(65); progress->setTextVisible(false);
    progress->setFixedHeight(6);
    sample->addWidget(progress);
    qobject_cast<QVBoxLayout *>(theme->layout())->addWidget(m_themePreview);
    auto *colors = addCard(page, tr("Custom colors"), tr("Choose a color to customize the preset. The preview updates before you save."));
    const QStringList keys{"theme/accent", "theme/background", "theme/text"};
    const QStringList labels{tr("Accent"), tr("Background"), tr("Text")};
    for (int i = 0; i < keys.size(); ++i) {
        QString key = keys[i];
        auto *pick = new QPushButton(colors);
        registerControl(colors, key, pick);
        auto *row = field(colors, labels[i], pick);
        if (i > 0) {
            auto *automatic = new QPushButton(i == 1 ? tr("System") : tr("Automatic"), colors);
            row->addWidget(automatic);
            connect(automatic, &QPushButton::clicked, this, [this, key]() {
                m_draft[key] = ""; m_draft["theme/preset"] = THEME_PRESET_COUNT - 1;
                loadWidgets(); edited();
            });
        }
        connect(pick, &QPushButton::clicked, this, [this, key, label = labels[i]]() {
            QString initial = m_draft[key].toString();
            if (initial.isEmpty()) initial = key == "theme/background" ? QApplication::palette().color(QPalette::Window).name() : QApplication::palette().color(QPalette::WindowText).name();
            QColor chosen = QColorDialog::getColor(QColor(initial), this, tr("Choose %1 color").arg(label.toLower()));
            if (!chosen.isValid()) return;
            m_draft[key] = chosen.name(); m_draft["theme/preset"] = THEME_PRESET_COUNT - 1;
            loadWidgets(); edited();
        });
    }
}

void PreferencesDialog::buildWorkspace() {
    int page = addPage(tr("Workspace"), tr("Choose which tools appear on your Control Panel home page and in its search."), "view-grid");
    auto *card = addCard(page, tr("Shown and hidden tools"),
                         tr("Select tools, then use the arrows to move them. The header Settings button is always available."));
    auto *layout = qobject_cast<QVBoxLayout *>(card->layout());
    auto *actions = new QHBoxLayout;
    m_tabCount = hint({}, card);
    actions->addWidget(m_tabCount, 1);
    for (const auto &preset : QList<QPair<QString, bool>>{{tr("Show all"), true}, {tr("Essentials"), false}}) {
        auto *button = new QPushButton(preset.first, card);
        button->setObjectName(preset.second ? "preferencesShowAll" : "preferencesEssentials");
        actions->addWidget(button);
        connect(button, &QPushButton::clicked, this, [this, all = preset.second]() {
            const QStringList essentials{"overview", "drives", "services", "autostart", "logs", "updates", "network", "preferences"};
            for (const auto &tool : AppPreferences::tools()) m_draft[AppPreferences::toolKey(tool.id)] = all || essentials.contains(tool.id);
            loadWidgets(); edited();
        });
    }
    layout->addLayout(actions);
    auto *lists = new QHBoxLayout;
    auto pane = [&](const QString &name, const QString &title, QLabel *&count) {
        auto *column = new QVBoxLayout;
        count = new QLabel(title, card);
        column->addWidget(count);
        auto *list = new QListWidget(card);
        list->setObjectName(name);
        list->setAccessibleName(title);
        list->setSelectionMode(QAbstractItemView::ExtendedSelection);
        list->setIconSize(QSize(22, 22));
        list->setSpacing(3);
        list->setMinimumWidth(0);
        list->setMinimumHeight(250);
        list->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        list->setTextElideMode(Qt::ElideRight);
        list->setSortingEnabled(true);
        column->addWidget(list, 1);
        lists->addLayout(column, 1);
        return list;
    };
    m_shownTools = pane("preferencesShownTools", tr("Shown"), m_shownCount);
    auto *arrows = new QVBoxLayout;
    arrows->addStretch();
    m_hideTools = new QPushButton(QString::fromUtf8("→"), card);
    m_showTools = new QPushButton(QString::fromUtf8("←"), card);
    m_hideTools->setObjectName("preferencesHideTools");
    m_showTools->setObjectName("preferencesShowTools");
    m_hideTools->setToolTip(tr("Hide selected tools"));
    m_showTools->setToolTip(tr("Show selected tools"));
    for (auto *button : {m_hideTools, m_showTools}) {
        button->setAccessibleName(button->toolTip());
        button->setFixedSize(40, 36);
        button->setAutoDefault(false);
        arrows->addWidget(button);
    }
    arrows->addStretch();
    lists->addLayout(arrows);
    m_hiddenTools = pane("preferencesHiddenTools", tr("Hidden"), m_hiddenCount);
    layout->addLayout(lists);
    connect(m_hideTools, &QPushButton::clicked, this, [this] { moveTools(false); });
    connect(m_showTools, &QPushButton::clicked, this, [this] { moveTools(true); });
    connect(m_shownTools, &QListWidget::itemSelectionChanged, this, [this] { m_hideTools->setEnabled(!m_shownTools->selectedItems().isEmpty()); });
    connect(m_hiddenTools, &QListWidget::itemSelectionChanged, this, [this] { m_showTools->setEnabled(!m_hiddenTools->selectedItems().isEmpty()); });
    for (const auto &tool : AppPreferences::tools()) m_sections[page].keys.append(AppPreferences::toolKey(tool.id));

    // These sections have no separate home tile. Keep their existing choices.
    auto *sections = addCard(page, tr("Software sections"));
    addCheck(sections, "tabs/uninstallTab", tr("Show Installed Software"));
    addCheck(sections, "tabs/pacmanDoctorTab", tr("Show Package Repair"));
}

void PreferencesDialog::loadToolLists() {
    m_shownTools->clear(); m_hiddenTools->clear();
    for (const auto &tool : AppPreferences::tools()) {
        const bool shown = m_draft.value(AppPreferences::toolKey(tool.id), true).toBool();
        auto *item = new QListWidgetItem(QIcon::fromTheme(tool.icon), tool.title, shown ? m_shownTools : m_hiddenTools);
        item->setData(Qt::UserRole, tool.id);
        item->setToolTip(tool.title + "\n" + tool.description);
        item->setSizeHint(QSize(0, 34));
    }
    m_shownCount->setText(tr("Shown · %1").arg(m_shownTools->count()));
    m_hiddenCount->setText(tr("Hidden · %1").arg(m_hiddenTools->count()));
    m_tabCount->setText(tr("%1 of %2 tools shown").arg(m_shownTools->count()).arg(m_shownTools->count() + m_hiddenTools->count()));
    m_hideTools->setEnabled(false); m_showTools->setEnabled(false);
}

void PreferencesDialog::moveTools(bool show) {
    auto *source = show ? m_hiddenTools : m_shownTools;
    QStringList moved;
    for (auto *item : source->selectedItems()) {
        const auto id = item->data(Qt::UserRole).toString();
        m_draft[AppPreferences::toolKey(id)] = show;
        moved << id;
    }
    if (moved.isEmpty()) return;
    const int next = source->currentRow();
    loadToolLists();
    if (source->count()) source->setCurrentRow(qBound(0, next, source->count() - 1));
    auto *destination = show ? m_shownTools : m_hiddenTools;
    for (int i = 0; i < destination->count(); ++i)
        destination->item(i)->setSelected(moved.contains(destination->item(i)->data(Qt::UserRole).toString()));
    source->setFocus();
    edited();
}

void PreferencesDialog::buildTools() {
    int page = addPage(tr("Tool defaults"), tr("Set the starting options for everyday tasks. Each tool still lets you adjust them."), "configure");
    auto *drives = addCard(page, tr("Drive list"), tr("Disks expand to show their partitions. Choose the minimum size shown in Drives."));
    addCheck(drives, "defaults/drives/minimumEnabled", tr("Filter small devices"));
    addSpin(drives, "defaults/drives/minimumMB", tr("Minimum size"), 1, 999999);
    auto *editor = addCard(page, tr("Configuration editor"), tr("Used when opening files from System Config. The selected editor must be installed."));
    addCombo(editor, "defaults/config/editor", tr("External editor"), {{"nano", "nano"}, {"Kate", "kate"}, {"Mousepad", "mousepad"}, {"Geany", "geany"}});
    auto *packages = addCard(page, tr("Package search"), tr("Shared search defaults for Pacman/AUR, Yay and Paru."));
    addCombo(packages, "defaults/packages/searchMode", tr("Search in"), {{tr("Package name"), 0}, {tr("Description"), 1}, {tr("Name and description"), 2}});
    addCombo(packages, "defaults/packages/searchType", tr("Match"), {{tr("Exact"), 0}, {tr("Contains"), 1}});
}

void PreferencesDialog::buildIso() {
    int page = addPage(tr("System ISO"), tr("Tune the exclusion browser and enable installer design previews."), "media-optical");
    auto *debug = addCard(page, tr("Installer previews"));
    addCheck(debug, "preferences/debugIsoCreatorEnabled", tr("Debug ISO Creator Button"), tr("Show Create Dummy ISO on the System ISO tab. It builds a bootable installer preview with an empty snapshot and simulated disk changes."));
    auto *note = hint(tr("The first dummy build prepares the live environment. Later builds reuse it and refresh the installer and logo."), debug);
    qobject_cast<QVBoxLayout *>(debug->layout())->addWidget(note);
    auto *filters = addCard(page, tr("Exclusion browser"), tr("Starting size filters for Manage Exclusions. These only control which entries are listed; exclusions remain your choice."));
    addSpin(filters, "defaults/iso/folderMinimumMB", tr("Show folders larger than"), 1, 1000000);
    addSpin(filters, "defaults/iso/fileMinimumMB", tr("Show files larger than"), 10, 1000000);
}

void PreferencesDialog::loadWidgets() {
    m_loading = true;
    for (auto it = m_controls.begin(); it != m_controls.end(); ++it) {
        const QVariant value = m_draft.value(it.key());
        if (auto *check = qobject_cast<QCheckBox *>(it.value())) check->setChecked(value.toBool());
        else if (auto *combo = qobject_cast<QComboBox *>(it.value())) combo->setCurrentIndex(combo->findData(value));
        else if (auto *spin = qobject_cast<QSpinBox *>(it.value())) spin->setValue(value.toInt());
    }
    m_loading = false;
    loadToolLists();
    updateStartupChoices();
    updateThemePreview();
    m_controls["defaults/drives/minimumMB"]->setEnabled(m_draft["defaults/drives/minimumEnabled"].toBool());
}

void PreferencesDialog::updateStartupChoices() {
    auto *combo = qobject_cast<QComboBox *>(m_controls["preferences/startupTab"]);
    QSignalBlocker blocker(combo);
    combo->clear();combo->addItem(tr("Control Panel — all tools"),"home");
    for (const auto &tool : AppPreferences::tools())
        if (!tool.path.isEmpty() && m_draft.value(AppPreferences::toolKey(tool.id), true).toBool()) combo->addItem(tool.title, tool.id);
    m_draft["preferences/startupTab"] = AppPreferences::startupTool(m_draft["preferences/startupTab"].toString());
    int index = combo->findData(m_draft["preferences/startupTab"]);
    if (index < 0 && combo->count()) index = 0;
    combo->setCurrentIndex(index);
    if (index >= 0) m_draft["preferences/startupTab"] = combo->currentData();
}

void PreferencesDialog::updateThemePreview() {
    return; // The inherited theme has no local preview controls.

    QColor bg(m_draft["theme/background"].toString());
    if (!bg.isValid()) bg = QApplication::palette().color(QPalette::Window);
    QColor fg(m_draft["theme/text"].toString());
    if (!fg.isValid()) fg = bg.lightness() < 128 ? QColor("#e6e6e6") : QColor("#1c1c1c");
    QString accent = m_draft["theme/accent"].toString();
    m_themePreview->setStyleSheet(QString(
        "QWidget#preferencesThemePreview {background:%1;border:1px solid %3;border-radius:8px;}"
        "QLabel {color:%2;background:transparent;} QLabel#previewAccent {color:%3;font-weight:bold;}"
        "QProgressBar {border:0;background:rgba(127,127,127,0.2);border-radius:3px;}"
        "QProgressBar::chunk {background:%3;border-radius:3px;}").arg(bg.name(), fg.name(), accent));
    for (const QString &key : {QString("theme/accent"), QString("theme/background"), QString("theme/text")}) {
        auto *button = qobject_cast<QPushButton *>(m_controls[key]);
        QString color = m_draft[key].toString();
        button->setText(color.isEmpty() ? (key == "theme/background" ? tr("System palette") : tr("Automatic")) : color.toUpper());
        button->setStyleSheet(color.isEmpty() ? QString() : QString("background:%1;color:%2;font-weight:bold;").arg(color, QColor(color).lightness() < 128 ? "white" : "black"));
    }
}

void PreferencesDialog::styleDialog() {
    setStyleSheet(QString()); return; // Inherit the Hyprland master theme.

    QColor bg(m_saved["theme/background"].toString());
    if (!bg.isValid()) bg = QApplication::palette().color(QPalette::Window);
    const bool dark = bg.lightness() < 128;
    QString fg = m_saved["theme/text"].toString();
    if (fg.isEmpty()) fg = dark ? "#e6e6e6" : "#1c1c1c";
    QColor accent(m_saved["theme/accent"].toString());
    const QColor base = dark ? bg.lighter(125) : bg.darker(103);
    QPalette colors = QApplication::palette();
    colors.setColor(QPalette::Window, bg);
    colors.setColor(QPalette::Base, base);
    colors.setColor(QPalette::AlternateBase, bg);
    colors.setColor(QPalette::Button, base);
    colors.setColor(QPalette::WindowText, QColor(fg));
    colors.setColor(QPalette::Text, QColor(fg));
    colors.setColor(QPalette::ButtonText, QColor(fg));
    colors.setColor(QPalette::PlaceholderText, QColor(dark ? "#9ca2ad" : "#626a76"));
    colors.setColor(QPalette::Highlight, accent);
    colors.setColor(QPalette::HighlightedText, accent.lightness() < 128 ? Qt::white : Qt::black);
    for (auto role : {QPalette::Text, QPalette::WindowText, QPalette::ButtonText})
        colors.setColor(QPalette::Disabled, role, QColor(dark ? "#777d87" : "#888e96"));
    setPalette(colors);
    const QString selected = QString("rgba(%1,%2,%3,0.20)").arg(accent.red()).arg(accent.green()).arg(accent.blue());
    setStyleSheet(QString(
        "QDialog#preferencesDialog {background:%1;} QWidget {color:%2;}"
        "QLabel#preferencesTitle {font-size:25px;font-weight:bold;}"
        "QLabel[prefHeading=\"true\"] {font-size:18px;font-weight:bold;}"
        "QLabel[prefHint=\"true\"] {color:%3;}"
        "QFrame#preferencesSidebar {background:rgba(127,127,127,0.07);border:1px solid rgba(127,127,127,0.16);border-radius:10px;}"
        "QListWidget#preferencesNavigation {background:transparent;border:0;outline:0;}"
        "QListWidget#preferencesNavigation::item {border:1px solid transparent;border-radius:7px;padding:5px;}"
        "QListWidget#preferencesNavigation::item:selected {background:%5;border-color:%4;color:%2;font-weight:bold;}"
        "QListWidget#preferencesNavigation::item:hover:!selected {background:rgba(127,127,127,0.10);}"
        "QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;border:0;}"
        "QScrollBar:vertical {background:transparent;width:10px;margin:2px;}"
        "QScrollBar::handle:vertical {background:rgba(127,127,127,0.45);min-height:24px;border-radius:4px;}"
        "QScrollBar::handle:vertical:hover {background:%4;}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}"
        "QGroupBox {background:rgba(127,127,127,0.05);border:1px solid rgba(127,127,127,0.24);border-top:2px solid %4;border-radius:9px;margin-top:10px;padding:4px;font-weight:bold;}"
        "QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 5px;}"
        "QGroupBox QLabel, QGroupBox QCheckBox {font-weight:normal;}"
        "QPushButton {background:%6;border:1px solid rgba(127,127,127,0.3);border-radius:6px;padding:5px 10px;}"
        "QPushButton:hover {background:%5;border-color:%4;}"
        "QPushButton:disabled {color:%3;background:rgba(127,127,127,0.06);border-color:rgba(127,127,127,0.15);}"
        "QLineEdit, QComboBox, QSpinBox {background:%6;color:%2;border:1px solid rgba(127,127,127,0.3);border-radius:6px;padding:5px 8px;min-height:20px;}"
        "QComboBox QAbstractItemView {background:%6;color:%2;selection-background-color:%4;}"
        "QSpinBox:disabled {color:%3;}"
        "QLineEdit#preferencesSearch {padding:9px 12px;border:1px solid rgba(127,127,127,0.3);border-radius:8px;}"
        "QLineEdit#preferencesSearch:focus {border-color:%4;}"
        "QPushButton#preferencesDone {background:%5;border:1px solid %4;font-weight:bold;padding:7px 15px;}"
        "QPushButton#preferencesApply, QPushButton#preferencesCancel, QPushButton#preferencesReset {padding:7px 12px;}"
    ).arg(bg.name(), fg, dark ? "#a0a6af" : "#626a76", accent.name(), selected, base.name()));
}

QString PreferencesDialog::validationError() const {
    return {}; // Home and the header Settings button remain usable with every tool hidden.
}

void PreferencesDialog::edited(bool stageOnly) {
    if (m_loading) return;
    m_saveFailed = false;
    updateStartupChoices();
    updateThemePreview();
    m_controls["defaults/drives/minimumMB"]->setEnabled(m_draft["defaults/drives/minimumEnabled"].toBool());
    if (!stageOnly && m_draft["preferences/autoSaveEnabled"].toBool() && validationError().isEmpty()) apply();
    else updateFooter();
}

bool PreferencesDialog::apply() {
    if (!validationError().isEmpty()) { updateFooter(); return false; }
    if (m_draft != m_saved) {
        if (!m_save(m_draft)) { m_saveFailed = true; updateFooter(); return false; }
        m_saved = m_draft;
        m_saveFailed = false;
        styleDialog();
    }
    updateFooter();
    return true;
}

void PreferencesDialog::updateFooter() {
    bool dirty = m_saved != m_draft;
    QString error = validationError();
    m_apply->setEnabled(dirty && error.isEmpty());
    m_done->setEnabled(error.isEmpty());
    m_done->setText(dirty ? tr("Save && Close") : tr("Done"));
    m_cancel->setVisible(dirty);
    if (m_saveFailed) m_status->setText(tr("Could not save. Check access to your settings folder and try Apply again."));
    else if (!error.isEmpty()) m_status->setText(error);
    else if (dirty) m_status->setText(tr("Unsaved changes"));
    else m_status->setText(m_draft["preferences/autoSaveEnabled"].toBool() ? tr("Changes save automatically") : tr("All changes saved"));
    m_status->setStyleSheet(m_saveFailed || !error.isEmpty() ? "color:#d98235;" : "");
}

void PreferencesDialog::resetPage() {
    int page = m_pages->currentIndex();
    if (page < 0 || page >= m_sections.size()) return;
    const auto defaults = AppPreferences::defaults();
    for (const auto &key : m_sections[page].keys) m_draft[key] = defaults[key];
    if (m_sections[page].keys.contains("appearance/showWindowControls")) m_draft["appearance/showWindowControls"] = false;
    loadWidgets();
    edited(true);
}

void PreferencesDialog::filter(const QString &query) {
    const QStringList words = query.trimmed().split(QRegularExpression("\\s+"), Qt::SkipEmptyParts);
    QVector<bool> matches(m_sections.size(), false);
    for (const auto &card : m_cards) {
        QString text = m_sections[card.page].title + ' ' + card.widget->title();
        for (auto *label : card.widget->findChildren<QLabel *>()) text += ' ' + label->text();
        for (auto *box : card.widget->findChildren<QCheckBox *>()) text += ' ' + box->text() + ' ' + box->toolTip();
        for (auto *combo : card.widget->findChildren<QComboBox *>())
            for (int i = 0; i < combo->count(); ++i) text += ' ' + combo->itemText(i);
        for (auto *list : card.widget->findChildren<QListWidget *>())
            for (int i = 0; i < list->count(); ++i) text += ' ' + list->item(i)->text() + ' ' + list->item(i)->toolTip();
        bool match = true;
        for (const QString &word : words) if (!text.contains(word, Qt::CaseInsensitive)) match = false;
        card.widget->setVisible(match);
        matches[card.page] = matches[card.page] || match;
    }
    int first = -1;
    for (int i = 0; i < matches.size(); ++i) {
        m_navigation->item(i)->setHidden(!matches[i]);
        if (matches[i] && first < 0) first = i;
    }
    if (first < 0) { m_pages->setCurrentIndex(m_sections.size()); m_reset->setEnabled(false); }
    else {
        int current = m_navigation->currentRow();
        if (current < 0 || !matches[current]) current = first;
        m_navigation->setCurrentRow(current);
        m_pages->setCurrentIndex(current);
        m_reset->setEnabled(true);
    }
}

bool PreferencesDialog::eventFilter(QObject *object, QEvent *event) {
    if (object == m_search && event->type() == QEvent::KeyPress) {
        auto *key = static_cast<QKeyEvent *>(event);
        if (key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter) {
            m_navigation->setFocus();
            return true;
        }
        if (key->key() == Qt::Key_Escape && !m_search->text().isEmpty()) {
            m_search->clear();
            return true;
        }
    }
    return QDialog::eventFilter(object, event);
}

void PreferencesDialog::resizeEvent(QResizeEvent *event) {
    QDialog::resizeEvent(event);
    if (!m_navigation) return;
    const bool compact = height() < 640;
    m_navigation->setSpacing(compact ? 3 : 5);
    for (int i = 0; i < m_navigation->count(); ++i)
        m_navigation->item(i)->setSizeHint(QSize(150, compact ? 36 : 48));
}
