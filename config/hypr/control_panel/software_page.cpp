#include "software_page.h"
#include "software_packages.h"
#include "software_catalog.h"
#include "native.h"
#include "backend/package_install.h"
#include "software_actions.h"
#include "terminal_exit.h"
#include <QtWidgets>

namespace {
template<class T> T *take(QWidget *root, const char *name) {
    auto *widget = root->findChild<T *>(name);
    if (!widget) qFatal("Software page is missing its backend widget: %s", name);
    return widget;
}
void add(QBoxLayout *layout, QWidget *widget, int stretch = 0) { layout->addWidget(widget, stretch); widget->show(); }
QLabel *label(const QString &text, const char *name = "softwareMuted") {
    auto *result = new QLabel(text); result->setObjectName(name); result->setWordWrap(true); result->setTextFormat(Qt::PlainText); return result;
}
void retire(QLayout *layout, QWidget *storage) {
    while (auto *item = layout->takeAt(0)) {
        if (auto *widget = item->widget()) { widget->setParent(storage); widget->hide(); }
        if (item->layout()) retire(item->layout(), storage);
        delete item;
    }
}
QVBoxLayout *card(QBoxLayout *parent, const QString &title, int stretch = 0) {
    auto *frame = new QFrame; frame->setObjectName("softwareCard");
    auto *layout = new QVBoxLayout(frame); layout->setContentsMargins(16, 14, 16, 14); layout->setSpacing(10);
    if (!title.isEmpty()) layout->addWidget(label(title, "softwareCardTitle"));
    parent->addWidget(frame, stretch); return layout;
}
QVBoxLayout *fold(QVBoxLayout *parent, const QString &title, const char *name) {
    auto *box = card(parent, {});
    auto *toggle = new QToolButton; toggle->setObjectName(name); toggle->setProperty("softwareFold", true);
    toggle->setText(title); toggle->setCheckable(true); toggle->setArrowType(Qt::RightArrow); toggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    box->addWidget(toggle, 0, Qt::AlignLeft);
    auto *body = new QWidget; auto *content = new QVBoxLayout(body); content->setContentsMargins(0, 4, 0, 0); content->setSpacing(12);
    box->addWidget(body); body->hide();
    QObject::connect(toggle, &QToolButton::toggled, body, [body, toggle](bool expanded) { body->setVisible(expanded); toggle->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow); });
    return content;
}
class NumericItem final : public QTableWidgetItem {
public:
    NumericItem(const QString &text, qint64 value) : QTableWidgetItem(text) { setData(Qt::UserRole, value); }
    bool operator<(const QTableWidgetItem &other) const override { return data(Qt::UserRole).toLongLong() < other.data(Qt::UserRole).toLongLong(); }
};
}

SoftwarePage::SoftwarePage(QWidget *legacy, const QString &root, const QString &terminal, QWidget *parent)
    : QWidget(parent), legacy(legacy), root(root), terminal(terminal) {
    setObjectName("softwareTab");
    setStyleSheet(
        "QWidget#softwareTab,QWidget#softwareRepairCanvas {background:transparent;}"
        "QFrame#softwareCard {background:palette(alternate-base);border:1px solid palette(mid);border-radius:10px;}"
        "QFrame#softwareCard QLabel {background:transparent;border:0;}"
        "QLabel#softwareHeading {font-size:26px;font-weight:650;}"
        "QLabel#softwareCardTitle {font-size:16px;font-weight:600;}"
        "QLabel#softwareMetric {font-size:22px;font-weight:600;}"
        "QLabel#softwareMuted {color:palette(placeholder-text);}"
        "QPushButton[softwarePrimary=\"true\"]:enabled {background:palette(highlight);color:palette(highlighted-text);border:1px solid palette(highlight);font-weight:600;}"
        "QTableWidget[softwareList=\"true\"],QTreeWidget#softwareDiagnosis {background:transparent;alternate-background-color:transparent;border:0;}"
        "QTableWidget[softwareList=\"true\"]::item,QTreeWidget#softwareDiagnosis::item {padding:6px;border:0;}"
        "QTableWidget[softwareList=\"true\"] QHeaderView::section,QTreeWidget#softwareDiagnosis QHeaderView::section {background:transparent;border:0;border-bottom:1px solid palette(mid);padding:6px;}"
        "QToolButton[softwareFold=\"true\"] {background:transparent;border:0;text-align:left;font-size:14px;font-weight:600;}");
    auto *outer = new QVBoxLayout(this); outer->setContentsMargins(6, 6, 6, 6); outer->setSpacing(12);
    auto *heading = new QHBoxLayout; auto *titles = new QVBoxLayout; titles->setSpacing(4);
    titles->addWidget(label("Software", "softwareHeading")); titles->addWidget(label("Find your next app. Make this desktop yours.")); heading->addLayout(titles, 1);
    auto *aur = new QPushButton(QIcon::fromTheme("package-x-generic"), "Yay && Paru");
    connect(aur, &QPushButton::clicked, this, [this] { emit openTool("aur"); }); heading->addWidget(aur);
    auto *updates = new QPushButton(QIcon::fromTheme("system-software-update"), "Updates");
    connect(updates, &QPushButton::clicked, this, [this] { emit openTool("updates"); }); heading->addWidget(updates);
    refresh = new QPushButton(QIcon::fromTheme("view-refresh"), "Refresh"); refresh->setObjectName("softwareRefresh");
    connect(refresh, &QPushButton::clicked, this, &SoftwarePage::refreshSection); heading->addWidget(refresh); outer->addLayout(heading);

    sections = new PanelTabs(this); sections->setObjectName("softwareSections"); sections->setDocumentMode(true); outer->addWidget(sections, 1);
    browser = new SoftwareCatalogPage(root, terminal, sections); sections->addTab(browser, "Browse");
    connect(browser, &SoftwareCatalogPage::openTool, this, &SoftwarePage::openTool);
    connect(browser, &SoftwareCatalogPage::installDebRequested, this, &SoftwarePage::installDebRequested);
    connect(browser, &SoftwareCatalogPage::packagesChanged, this, [this] { loaded = false; if (isVisible() && sections->currentIndex() == 1) refreshInstalled(); });
    auto *storage = new QWidget(this); storage->setObjectName("retiredSoftwareWidgets"); storage->hide();
    auto *installedPage = take<QWidget>(legacy, "uninstallTab");
    auto *repairPage = take<QWidget>(legacy, "pacmanDoctorTab");
    for (auto *page : {installedPage, repairPage}) retire(page->layout(), storage);
    sections->addTab(installedPage, "Installed"); sections->addTab(repairPage, "Repair");

    auto *installedLayout = qobject_cast<QVBoxLayout *>(installedPage->layout()); installedLayout->setContentsMargins(0, 12, 0, 0); installedLayout->setSpacing(12);
    auto *metrics = new QHBoxLayout; metrics->setSpacing(12); installedLayout->addLayout(metrics);
    count = label("—", "softwareMetric"); space = label("—", "softwareMetric"); foreign = label("—", "softwareMetric");
    const QList<QPair<QLabel *, QString>> metricValues{{count, "Installed packages"}, {space, "Installed size"}, {foreign, "AUR / local packages"}};
    for (const auto &entry : metricValues) { auto *layout = card(metrics, {}, 1); layout->addWidget(label(entry.second)); layout->addWidget(entry.first); }
    auto *listCard = card(installedLayout, {}, 1);
    auto *filters = new QHBoxLayout;
    filter = take<QLineEdit>(legacy, "uninstallSearch"); filter->setClearButtonEnabled(true); filter->setPlaceholderText("Filter installed packages…"); add(filters, filter, 1);
    auto *source = take<QComboBox>(legacy, "uninstallSourceFilter"); add(filters, source); listCard->addLayout(filters);
    installed = take<QTableWidget>(legacy, "uninstallTable"); installed->setProperty("softwareList", true);
    installed->setEditTriggers(QAbstractItemView::NoEditTriggers); installed->setShowGrid(false); installed->verticalHeader()->hide(); installed->verticalHeader()->setDefaultSectionSize(36);
    installed->setWordWrap(false); installed->setTextElideMode(Qt::ElideRight); installed->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    installed->setMinimumHeight(220); add(listCard, installed, 1);
    auto *actions = new QHBoxLayout;
    remove = take<QPushButton>(legacy, "uninstallButton"); remove->setText("Uninstall selected…"); remove->setIcon(QIcon::fromTheme("edit-delete")); remove->setProperty("softwarePrimary", true); add(actions, remove);
    reinstall = new QPushButton(QIcon::fromTheme("view-refresh"), "Reinstall…"); reinstall->setObjectName("softwareReinstall"); actions->addWidget(reinstall);
    connect(reinstall, &QPushButton::clicked, this, &SoftwarePage::reinstallPackage);
    details = new QPushButton(QIcon::fromTheme("dialog-information"), "Details"); details->setObjectName("softwareDetails"); actions->addWidget(details);
    connect(details, &QPushButton::clicked, this, &SoftwarePage::showPackageDetails);
    actions->addStretch(); add(actions, take<QLabel>(legacy, "uninstallSelectedSizeLabel"));
    auto *more = new QPushButton("More"); more->setObjectName("softwareInstalledMore"); auto *menu = new QMenu(more); more->setMenu(menu);
    menu->addAction("Remove unused dependencies…", take<QPushButton>(legacy, "orphanCleanButton"), &QPushButton::click);
    menu->addAction("Clean package cache…", take<QPushButton>(legacy, "cacheCleanButton"), &QPushButton::click);
    actions->addWidget(more); listCard->addLayout(actions);
    auto *options = fold(installedLayout, "Removal options", "softwareRemovalOptions"); auto *optionRow = new QHBoxLayout;
    auto *helperLabel = take<QLabel>(legacy, "uninstallHelperLabel"); add(optionRow, helperLabel); add(optionRow, take<QComboBox>(legacy, "uninstallHelperCombo"));
    auto *deps = take<QCheckBox>(legacy, "uninstallDepsCheckBox"); deps->setText("Also remove dependencies no longer needed"); add(optionRow, deps); optionRow->addStretch(); options->addLayout(optionRow);
    installedStatus = take<QLabel>(legacy, "uninstallCountLabel"); installedStatus->setWordWrap(true); installedStatus->setText("Open Installed to load your packages."); add(installedLayout, installedStatus);
    connect(installed, &QTableWidget::itemSelectionChanged, this, &SoftwarePage::updateActions);
    connect(installed, &QTableWidget::cellDoubleClicked, this, [this] { showPackageDetails(); });
    disconnect(filter, nullptr, legacy, nullptr); disconnect(source, nullptr, legacy, nullptr);
    connect(filter, &QLineEdit::textChanged, this, &SoftwarePage::filterInstalled);
    connect(source, &QComboBox::currentIndexChanged, this, &SoftwarePage::filterInstalled);

    auto *repairLayout = qobject_cast<QVBoxLayout *>(repairPage->layout()); repairLayout->setContentsMargins(0, 12, 0, 0);
    repairScroll = new QScrollArea; repairScroll->setObjectName("softwareRepairScroll"); repairScroll->setFrameShape(QFrame::NoFrame); repairScroll->setWidgetResizable(true);
    auto *canvas = new QWidget; canvas->setObjectName("softwareRepairCanvas"); auto *repairBody = new QVBoxLayout(canvas); repairBody->setContentsMargins(0, 0, 4, 8); repairBody->setSpacing(12);
    repairScroll->setWidget(canvas); repairLayout->addWidget(repairScroll); repairScroll->viewport()->installEventFilter(this);
    auto *statusRow = new QHBoxLayout; auto *repairStatus = take<QLabel>(legacy, "pacDocStatus"); repairStatus->setWordWrap(true); repairStatus->setStyleSheet({}); add(statusRow, repairStatus, 1);
    auto *diagnose = take<QPushButton>(legacy, "pacDocDiagnose"); diagnose->setText("Check now"); diagnose->setIcon(QIcon::fromTheme("view-refresh")); add(statusRow, diagnose); repairBody->addLayout(statusRow);
    repairColumns = new QBoxLayout(QBoxLayout::LeftToRight); repairColumns->setSpacing(12); repairBody->addLayout(repairColumns);
    auto *health = card(repairColumns, "Package health", 1); health->addWidget(label("Read-only checks. Hover a result for advice."));
    diagnostics = new QTreeWidget; diagnostics->setObjectName("softwareDiagnosis"); diagnostics->setHeaderLabels({"Check", "Result"}); diagnostics->setRootIsDecorated(false); diagnostics->setIndentation(0);
    diagnostics->setSelectionMode(QAbstractItemView::NoSelection); diagnostics->setUniformRowHeights(true);
    diagnostics->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents); diagnostics->header()->setSectionResizeMode(1, QHeaderView::Stretch);
    diagnostics->setMinimumHeight(330); health->addWidget(diagnostics, 1);
    diagnosisSource = take<QLabel>(legacy, "pacDocDiagnosis"); diagnosisSource->installEventFilter(this);
    auto *tools = card(repairColumns, "Repair tools", 1);
    struct Action { const char *name; const char *title; const char *description; };
    for (const auto &action : {
        Action{"pacDocMirrors", "Rank mirrors…", "Slow downloads or missing packages"},
        Action{"pacDocKeys", "Repair keyring…", "Signature and trust errors"},
        Action{"pacDocUnlock", "Remove stale lock…", "A package operation was interrupted"},
        Action{"pacDocDowngrade", "Downgrade…", "Restore a cached package version"},
        Action{"pacDocTrim", "Trim cache…", "Free space while keeping older versions"},
        Action{"pacDocSync", "Refresh && upgrade…", "Rebuild repository lists and update"}}) {
        auto *row = new QHBoxLayout; auto *button = take<QPushButton>(legacy, action.name); button->setText(action.title); button->setMinimumWidth(165);
        row->addWidget(label(action.description), 1); add(row, button); tools->addLayout(row);
    }
    tools->addStretch();
    auto *pending = fold(repairBody, "Configuration updates", "softwareConfigFilesToggle");
    pending->addWidget(label("Review new package defaults before merging them into your configuration."));
    auto *files = take<QListWidget>(legacy, "pacDocFiles"); files->setMaximumHeight(170); files->setMinimumHeight(80); add(pending, files);
    auto *fileActions = new QHBoxLayout;
    const QList<QPair<const char *, QString>> fileButtons{{"pacDocMerge", "Merge all…"}, {"pacDocOpenNew", "Open selected"}, {"pacDocOpenCurrent", "Open current version"}};
    for (const auto &entry : fileButtons) { auto *button = take<QPushButton>(legacy, entry.first); button->setText(entry.second); add(fileActions, button); }
    fileActions->addStretch(); pending->addLayout(fileActions);
    connect(files, &QListWidget::itemSelectionChanged, this, &SoftwarePage::syncConfigFiles);
    connect(files->model(), &QAbstractItemModel::rowsInserted, this, [this] { syncConfigFiles(); });
    connect(files->model(), &QAbstractItemModel::modelReset, this, &SoftwarePage::syncConfigFiles);

    auto *settings = fold(repairBody, "Pacman settings", "softwarePacmanSettings");
    auto *parallel = new QHBoxLayout; parallel->addWidget(label("Parallel downloads")); add(parallel, take<QSpinBox>(legacy, "pacDocParallel")); parallel->addStretch(); settings->addLayout(parallel);
    auto *checks = new QGridLayout; int index = 0;
    const QList<QPair<const char *, QString>> optionsText{{"pacDocColor", "Show colors"}, {"pacDocCandy", "Animated progress bar"}, {"pacDocVerbose", "Show detailed package lists"}, {"pacDocCheckSpace", "Check free space before installing"}, {"pacDocTimeout", "Allow slow downloads"}};
    for (const auto &entry : optionsText) { auto *check = take<QCheckBox>(legacy, entry.first); check->setText(entry.second); checks->addWidget(check, index / 2, index % 2); check->show(); ++index; }
    settings->addLayout(checks);
    auto *configActions = new QHBoxLayout;
    for (const auto &name : {"pacDocApply", "pacDocBackup", "pacDocEdit"}) add(configActions, take<QPushButton>(legacy, name));
    configActions->addStretch(); settings->addLayout(configActions); repairBody->addStretch();
    syncDiagnosis(); syncConfigFiles(); updateActions();

    connect(sections, &QTabWidget::currentChanged, this, [this](int index) {
        refresh->setVisible(index != 2);
        if (!isVisible()) return;
        if (index == 1 && !loaded) refreshInstalled();
        if (index == 2) take<QPushButton>(this->legacy, "pacDocDiagnose")->click();
    });
    deadline.setSingleShot(true); deadline.setInterval(60000);
    connect(&deadline, &QTimer::timeout, this, [this] { timedOut = true; loader.kill(); });
    connect(&loader, &QProcess::readyReadStandardOutput, this, [this] { output += loader.readAllStandardOutput(); if (output.size() > 32 * 1024 * 1024) { errors = "Package data exceeded the display limit."; loader.kill(); } });
    connect(&loader, &QProcess::readyReadStandardError, this, [this] { errors += loader.readAllStandardError(); });
    connect(&loader, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, &SoftwarePage::readFinished);
    connect(&loader, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) { if (error == QProcess::FailedToStart) { errors = loader.errorString().toUtf8(); readFinished(-1, QProcess::CrashExit); } });
}

SoftwarePage::~SoftwarePage() {
    // Item models emit reset/selection signals as their widgets are destroyed.
    // Stop these callbacks before sibling controls and the legacy owner vanish.
    for (auto *object : findChildren<QObject *>()) { object->disconnect(this); object->removeEventFilter(this); }
    loader.disconnect(this);
    if (loader.state() != QProcess::NotRunning) { loader.kill(); loader.waitForFinished(1000); }
}
void SoftwarePage::openSection(int index) { if (index >= 0 && index < sections->count()) sections->setCurrentIndex(index); }
void SoftwarePage::focusSearch() { if (sections->currentIndex() == 1) filter->setFocus(); else { sections->setCurrentIndex(0); browser->focusSearch(); } }
void SoftwarePage::showEvent(QShowEvent *event) {
    QWidget::showEvent(event);
    QTimer::singleShot(0, this, [this] { if (isVisible() && sections->currentIndex() == 1 && !loaded) refreshInstalled(); });
}
void SoftwarePage::refreshSection() {
    if (sections->currentIndex() == 0) browser->refresh();
    else if (sections->currentIndex() == 1) refreshInstalled();
    else take<QPushButton>(legacy, "pacDocDiagnose")->click();
}
void SoftwarePage::refreshInstalled() {
    if (loading) return;
    selectedNames.clear();
    for (const auto &index : installed->selectionModel()->selectedRows()) if (auto *item = installed->item(index.row(), 0)) selectedNames.insert(item->text());
    loading = true; stage = 0; timedOut = false; foreignNames.clear();
    installedStatus->setText("Reading installed packages…"); installed->setEnabled(false); updateActions(); runRead({"-Qmq"});
}
void SoftwarePage::runRead(const QStringList &args) {
    output.clear(); errors.clear(); auto env = QProcessEnvironment::systemEnvironment(); env.insert("LC_ALL", "C"); loader.setProcessEnvironment(env);
    deadline.start(); loader.start("pacman", args);
}
void SoftwarePage::readFinished(int code, QProcess::ExitStatus exit) {
    if (!loading) return;
    deadline.stop(); output += loader.readAllStandardOutput(); errors += loader.readAllStandardError();
    const bool emptyForeign = stage == 0 && code == 1 && output.trimmed().isEmpty() && errors.trimmed().isEmpty();
    if (timedOut || exit != QProcess::NormalExit || (code != 0 && !emptyForeign)) {
        loading = false; installed->setEnabled(true);
        installedStatus->setText(timedOut ? "Reading packages timed out. Try Refresh again." : "Could not refresh packages. " + QString::fromUtf8(errors).trimmed().left(500)); updateActions(); return;
    }
    if (stage == 0) { for (const auto &name : QString::fromUtf8(output).split('\n', Qt::SkipEmptyParts)) foreignNames.insert(name.trimmed()); stage = 1; runRead({"-Qi"}); return; }
    const auto packages = SoftwarePackages::parse(QString::fromUtf8(output));
    // A successful but malformed read must not replace a previously useful list.
    if (packages.isEmpty() && !output.trimmed().isEmpty()) { loading = false; installed->setEnabled(true); installedStatus->setText("Package metadata could not be read. Your previous list has been kept."); updateActions(); return; }
    const int sortColumn = installed->columnCount() ? installed->horizontalHeader()->sortIndicatorSection() : 2;
    const auto order = installed->columnCount() ? installed->horizontalHeader()->sortIndicatorOrder() : Qt::DescendingOrder;
    installed->setSortingEnabled(false); installed->setRowCount(0); installed->setColumnCount(6);
    installed->setHorizontalHeaderLabels({"Package", "Version", "Size", "Source", "Description", "Installed"});
    installed->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
    const int widths[]{210, 140, 95, 115, 260, 100}; for (int i = 0; i < 6; ++i) installed->setColumnWidth(i, widths[i]);
    installed->horizontalHeader()->setSectionResizeMode(4, QHeaderView::Stretch);
    installed->horizontalHeader()->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    qint64 bytes = 0; int foreignCount = 0;
    for (const auto &package : packages) {
        const int row = installed->rowCount(); installed->insertRow(row); bytes += package.bytes;
        auto *name = new QTableWidgetItem(package.name); auto font = name->font(); font.setBold(true); name->setFont(font);
        name->setToolTip(package.description); installed->setItem(row, 0, name); installed->setItem(row, 1, new QTableWidgetItem(package.version));
        installed->setItem(row, 2, new NumericItem(SoftwarePackages::sizeText(package.bytes), package.bytes));
        const bool isForeign = foreignNames.contains(package.name); if (isForeign) ++foreignCount;
        auto *source = new QTableWidgetItem(isForeign ? "AUR / local" : "Repository"); source->setData(Qt::UserRole, isForeign); installed->setItem(row, 3, source);
        auto *description = new QTableWidgetItem(package.description); description->setToolTip(package.description); installed->setItem(row, 4, description);
        const auto date = QLocale::c().toDateTime(package.date.simplified(), "ddd MMM d HH:mm:ss yyyy");
        auto *dateItem = new NumericItem(date.isValid() ? date.toString("yyyy-MM-dd") : package.date, date.toSecsSinceEpoch()); dateItem->setToolTip(package.date); installed->setItem(row, 5, dateItem);
    }
    installed->setSortingEnabled(true); installed->sortByColumn(qBound(0, sortColumn, 5), order);
    filterInstalled();
    for (int row = 0; row < installed->rowCount(); ++row)
        if (!installed->isRowHidden(row) && selectedNames.contains(installed->item(row, 0)->text()))
            installed->selectionModel()->select(installed->model()->index(row, 0), QItemSelectionModel::Select | QItemSelectionModel::Rows);
    loading = false; loaded = true; installed->setEnabled(true);
    count->setText(QString::number(packages.size())); space->setText(SoftwarePackages::sizeText(bytes)); foreign->setText(QString::number(foreignCount));
    installedStatus->setText("Select packages to manage them. Double-click a row for details."); updateActions();
}
void SoftwarePage::updateActions() {
    const auto rows = installed->selectionModel()->selectedRows();
    remove->setEnabled(!loading && !rows.isEmpty()); details->setEnabled(!loading && rows.size() == 1);
    const bool official = rows.size() == 1 && installed->item(rows.first().row(), 3) && !installed->item(rows.first().row(), 3)->data(Qt::UserRole).toBool();
    reinstall->setEnabled(!loading && official);
    reinstall->setToolTip(official ? "Reinstall from the configured repositories." : "Select one repository package. Reinstall AUR or local packages from their original source.");
    qint64 bytes = 0; for (const auto &index : rows) if (auto *item = installed->item(index.row(), 2)) bytes += item->data(Qt::UserRole).toLongLong();
    take<QLabel>(legacy, "uninstallSelectedSizeLabel")->setText(rows.isEmpty() ? "No selection" : QString("%1 selected · %2").arg(rows.size()).arg(SoftwarePackages::sizeText(bytes)));
}
void SoftwarePage::filterInstalled() {
    const int source = take<QComboBox>(legacy, "uninstallSourceFilter")->currentIndex();
    for (int row = 0; row < installed->rowCount(); ++row) {
        const auto *name = installed->item(row, 0); const auto *description = installed->item(row, 4); const auto *origin = installed->item(row, 3);
        if (!name || !description || !origin) continue;
        const bool foreign = origin->data(Qt::UserRole).toBool();
        const bool visible = (source == 0 || (source == 1 && !foreign) || (source == 2 && foreign)) &&
            (filter->text().isEmpty() || name->text().contains(filter->text(), Qt::CaseInsensitive) || description->text().contains(filter->text(), Qt::CaseInsensitive));
        installed->setRowHidden(row, !visible);
        if (!visible) installed->selectionModel()->select(installed->model()->index(row, 0), QItemSelectionModel::Deselect | QItemSelectionModel::Rows);
    }
    updateActions();
}
void SoftwarePage::syncDiagnosis() {
    diagnostics->clear();
    const auto rows = diagnosisSource->property("softwareDiagnostics").toList();
    for (const auto &value : rows) {
        const auto data = value.toMap(); auto *row = new QTreeWidgetItem(diagnostics, {data["check"].toString(), data["result"].toString()});
        const int severity = data["severity"].toInt(); const auto fallback = severity == 2 ? QStyle::SP_MessageBoxCritical : severity == 1 ? QStyle::SP_MessageBoxWarning : QStyle::SP_DialogApplyButton;
        row->setIcon(0, QIcon::fromTheme(severity == 2 ? "dialog-error" : severity == 1 ? "dialog-warning" : "emblem-default", style()->standardIcon(fallback)));
        const auto hint = data["result"].toString() + (data["advice"].toString().isEmpty() ? QString() : "\n" + data["advice"].toString()); row->setToolTip(0, hint); row->setToolTip(1, hint);
    }
    if (rows.isEmpty()) new QTreeWidgetItem(diagnostics, {"Not checked yet", "Choose Check now"});
}
void SoftwarePage::syncConfigFiles() {
    auto *files = take<QListWidget>(legacy, "pacDocFiles"); int pending = 0;
    for (int row = 0; row < files->count(); ++row) if (QDir::isAbsolutePath(files->item(row)->text())) ++pending;
    take<QToolButton>(this, "softwareConfigFilesToggle")->setText(QString("Configuration updates · %1").arg(pending));
    const bool selected = files->currentItem() && QDir::isAbsolutePath(files->currentItem()->text());
    take<QPushButton>(legacy, "pacDocOpenNew")->setEnabled(selected); take<QPushButton>(legacy, "pacDocOpenCurrent")->setEnabled(selected);
    take<QPushButton>(legacy, "pacDocMerge")->setEnabled(pending > 0);
}
bool SoftwarePage::eventFilter(QObject *object, QEvent *event) {
    if (object == diagnosisSource && event->type() == QEvent::DynamicPropertyChange && static_cast<QDynamicPropertyChangeEvent *>(event)->propertyName() == "softwareDiagnostics") syncDiagnosis();
    if (object == repairScroll->viewport() && event->type() == QEvent::Resize) repairColumns->setDirection(repairScroll->viewport()->width() < 1000 ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    return QWidget::eventFilter(object, event);
}
void SoftwarePage::showPackageDetails() {
    const auto rows = installed->selectionModel()->selectedRows(); if (loading || rows.size() != 1) return;
    const int row = rows.first().row(); auto *dialog = new QDialog(this); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setProperty("xetalWindowSized", true);
    dialog->setObjectName("softwarePackageDetails"); dialog->setWindowTitle("Package details"); dialog->setWindowModality(Qt::WindowModal); dialog->resize(580, 360);
    auto *layout = new QVBoxLayout(dialog); layout->setContentsMargins(20, 18, 20, 18); layout->setSpacing(12);
    layout->addWidget(label(installed->item(row, 0)->text(), "softwareCardTitle")); layout->addWidget(label(installed->item(row, 4)->text()));
    auto *form = new QFormLayout;
    for (int column : {1, 2, 3, 5}) { auto *value = label(installed->item(row, column)->text()); value->setTextInteractionFlags(Qt::TextSelectableByMouse); form->addRow(installed->horizontalHeaderItem(column)->text(), value); }
    layout->addLayout(form); layout->addStretch(); auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close); connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject); layout->addWidget(buttons); dialog->open();
}
void SoftwarePage::reinstallPackage() {
    const auto rows = installed->selectionModel()->selectedRows(); if (loading || rows.size() != 1 || !reinstall->isEnabled()) return;
    const auto package = installed->item(rows.first().row(), 0)->text();
    QMessageBox confirmation(QMessageBox::Question, "Reinstall package", "Reinstall " + package + '?', QMessageBox::Yes | QMessageBox::No, this);
    confirmation.setTextFormat(Qt::PlainText); confirmation.setProperty("xetalWindowSized", true);
    confirmation.setInformativeText("Repositories will be refreshed and pending system updates included. Review the full transaction in the terminal.");
    if (confirmation.exec() != QMessageBox::Yes) return;
    qint64 pid = 0;
    if (!QProcess::startDetached(terminal, {"-e", "bash", "-c", PackageInstall::script("pacman", "Pacman", package, false, SoftwareActions::pinCommand(root,package))}, {}, &pid)) { installedStatus->setText("Could not open the installation terminal."); return; }
    installedStatus->setText("Reinstallation opened in the terminal. Review the changes there."); TerminalExit::watch(this, pid, [this] { refreshInstalled(); });
}
