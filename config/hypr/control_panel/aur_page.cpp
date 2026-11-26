#include "aur_page.h"
#include "aur_helpers.h"
#include "backend/package_install.h"
#include "terminal_exit.h"
#include <QtWidgets>

namespace {
QLabel *label(const QString &text, const char *name = "aurMuted") {
    auto *value = new QLabel(text); value->setObjectName(name);
    value->setTextFormat(Qt::PlainText); value->setWordWrap(true); return value;
}
QString title(const QString &helper) { return helper == "pacman" ? "Pacman" : helper == "yay" ? "Yay" : helper == "paru" ? "Paru" : "Yay and Paru"; }
QString terminalCommand(const QString &command) {
    return command + "\naur_action_status=$?\nprintf '\\n'\n"
        "if [ \"$aur_action_status\" -ne 0 ]; then printf '%s\\n' 'Action did not complete. Review the output above.'; fi\n"
        "read -r -p 'Press Enter to close…'\nexit \"$aur_action_status\"\n";
}
}

AurPage::AurPage(const QString &profileRoot, const QString &terminal, QWidget *parent, Mode mode)
    : QWidget(parent), root(profileRoot), terminal(terminal), mode(mode) {
    setObjectName(mode == Mode::Repositories ? "softwareBrowseTab" : "aurTab");
    setStyleSheet(
        "QWidget#aurTab,QWidget#softwareBrowseTab {background:transparent;}"
        "QFrame#aurCard {background:palette(alternate-base);border:1px solid palette(mid);border-radius:10px;}"
        "QFrame#aurCard QLabel {background:transparent;border:0;}"
        "QLabel#aurHeading {font-size:26px;font-weight:650;}"
        "QLabel#aurCardTitle {font-size:16px;font-weight:600;}"
        "QFrame#aurCard QLabel#aurRecommended {background:palette(highlight);color:palette(highlighted-text);border-radius:5px;padding:4px 8px;font-size:11px;font-weight:600;}"
        "QLabel#aurEmptyTitle {font-size:20px;font-weight:600;}"
        "QLabel#aurMuted,QLabel#aurStatus {color:palette(placeholder-text);}"
        "QPushButton[aurPrimary=\"true\"]:enabled {background:palette(highlight);color:palette(highlighted-text);border:1px solid palette(highlight);font-weight:600;}"
        "QTableWidget#aurResults {background:transparent;alternate-background-color:transparent;border:0;}"
        "QTableWidget#aurResults::item {padding:6px;border:0;}"
        "QTableWidget#aurResults QHeaderView::section {border:0;border-bottom:1px solid palette(mid);padding:8px;background:transparent;}"
        "QToolButton#aurDetailsToggle {background:transparent;border:0;}");
    auto *outer = new QVBoxLayout(this); outer->setContentsMargins(6, 6, 6, 6); outer->setSpacing(14);
    auto *headingWidget = new QWidget;
    auto *heading = new QHBoxLayout(headingWidget); heading->setContentsMargins(0, 0, 0, 0);
    auto *titles = new QVBoxLayout; titles->setSpacing(4);
    titles->addWidget(label("Yay & Paru", "aurHeading"));
    titles->addWidget(label("Find and manage Arch and AUR packages."));
    heading->addLayout(titles, 1);
    auto *manageButton = new QPushButton(QIcon::fromTheme("configure"), "Manage helpers"); manageButton->setObjectName("aurManage");
    manage = new QMenu(manageButton); manage->setObjectName("aurHelperMenu"); manageButton->setMenu(manage);
    connect(manage, &QMenu::aboutToShow, this, &AurPage::rebuildMenu);
    heading->addWidget(manageButton);
    auto *refresh = new QPushButton(QIcon::fromTheme("view-refresh"), "Refresh"); refresh->setObjectName("aurRefresh");
    connect(refresh, &QPushButton::clicked, this, &AurPage::refresh);
    heading->addWidget(refresh); outer->addWidget(headingWidget);
    headingWidget->setVisible(mode == Mode::Helpers);
    auto *choices=new QWidget;choices->setObjectName("aurHelperChoices");
    auto *choiceLayout=new QHBoxLayout(choices);choiceLayout->setContentsMargins(0,0,0,0);choiceLayout->setSpacing(12);
    auto helperCard=[&](const QString &name,QLabel *&state,QPushButton *&button){
        auto *card=new QFrame;card->setObjectName("aurCard");
        auto *row=new QHBoxLayout(card);row->setContentsMargins(16,14,16,14);row->setSpacing(12);
        auto *text=new QVBoxLayout;text->setSpacing(6);auto *titleRow=new QHBoxLayout;
        titleRow->addWidget(label(title(name),"aurCardTitle"));
        if(name=="yay"){
            auto *recommended=label("Recommended","aurRecommended");recommended->setWordWrap(false);
            recommended->setToolTip("Our recommended package helper for HyperFusion.");titleRow->addWidget(recommended);
        }
        titleRow->addStretch();text->addLayout(titleRow);state=label({});text->addWidget(state);row->addLayout(text,1);
        button=new QPushButton;button->setObjectName(name=="yay"?"aurInstallYay":"aurInstallParu");button->setMinimumHeight(40);
        button->setProperty("aurPrimary",name=="yay");row->addWidget(button);
        connect(button,&QPushButton::clicked,this,[this,name]{helperAction(name,"install");});
        choiceLayout->addWidget(card,1);
    };
    helperCard("yay",yayStatus,installYay);helperCard("paru",paruStatus,installParu);
    outer->addWidget(choices);choices->setVisible(mode==Mode::Helpers);

    auto *searchCard = new QFrame; searchCard->setObjectName("aurCard");
    auto *searchLayout = new QVBoxLayout(searchCard); searchLayout->setContentsMargins(16, 14, 16, 14); searchLayout->setSpacing(10);
    auto *searchRow = new QHBoxLayout;
    query = new QLineEdit; query->setObjectName("aurQuery"); query->setPlaceholderText("Search packages by name or description…");
    query->setAccessibleName("Search packages"); query->setClearButtonEnabled(true);
    query->setMinimumHeight(30); searchRow->addWidget(query, 1);
    search = new QPushButton(QIcon::fromTheme("edit-find"), "Search"); search->setObjectName("aurSearch"); search->setProperty("aurPrimary", true);
    searchRow->addWidget(search); searchLayout->addLayout(searchRow);
    auto *filters = new QHBoxLayout; filters->setSpacing(10);
    helper = new QComboBox; helper->setObjectName("aurHelper"); helper->setAccessibleName("Package helper");
    helper->addItem("Automatic", ""); helper->addItem("Yay", "yay"); helper->addItem("Paru", "paru");
    auto *helperLabel = label("Use"); filters->addWidget(helperLabel); filters->addWidget(helper);
    helperLabel->setVisible(mode == Mode::Helpers); helper->setVisible(mode == Mode::Helpers);
    field = new QComboBox; field->setObjectName("aurField"); field->setAccessibleName("Search field");
    field->addItems({"Name or description", "Name", "Description"});
    filters->addSpacing(8); filters->addWidget(label("Match")); filters->addWidget(field);
    match = new QComboBox; match->setObjectName("aurMatch"); match->setAccessibleName("Match type");
    match->addItems({"Contains", "Exact"}); filters->addWidget(match); filters->addStretch(); searchLayout->addLayout(filters);
    QSettings settings("XetalHyperland", "ControlPanel");
    field->setCurrentIndex((qBound(0, settings.value("defaults/packages/searchMode", 2).toInt(), 2) + 1) % 3);
    match->setCurrentIndex(1 - qBound(0, settings.value("defaults/packages/searchType", 1).toInt(), 1));
    outer->addWidget(searchCard);

    auto *resultCard = new QFrame; resultCard->setObjectName("aurCard");
    auto *resultLayout = new QVBoxLayout(resultCard); resultLayout->setContentsMargins(16, 14, 16, 14); resultLayout->setSpacing(10);
    resultTitle = label("Packages", "aurCardTitle"); resultLayout->addWidget(resultTitle);
    results = new QStackedWidget; results->setObjectName("aurResultStack"); results->setMinimumHeight(230);
    auto *empty = new QWidget; auto *emptyLayout = new QVBoxLayout(empty); emptyLayout->setSpacing(10); emptyLayout->addStretch();
    auto *icon = new QLabel; icon->setAlignment(Qt::AlignCenter); icon->setPixmap(QIcon::fromTheme("system-software-install", style()->standardIcon(QStyle::SP_FileDialogContentsView)).pixmap(48));
    emptyLayout->addWidget(icon);
    emptyTitle = label("Find your next app", "aurEmptyTitle"); emptyTitle->setAlignment(Qt::AlignCenter); emptyLayout->addWidget(emptyTitle);
    emptyHint = label("Search above to see packages from your repositories and the AUR."); emptyHint->setAlignment(Qt::AlignCenter);
    emptyLayout->addWidget(emptyHint); emptyLayout->addStretch(); results->addWidget(empty);
    table = new QTableWidget(0, 5); table->setObjectName("aurResults");
    table->setHorizontalHeaderLabels({"Package", "Version", "Source", "Votes", "Description"});
    table->setSelectionBehavior(QAbstractItemView::SelectRows); table->setSelectionMode(QAbstractItemView::SingleSelection);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers); table->setWordWrap(false); table->setShowGrid(false);
    table->verticalHeader()->hide(); table->verticalHeader()->setDefaultSectionSize(42);
    table->horizontalHeader()->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    for (int c = 0; c < 4; ++c) table->horizontalHeader()->setSectionResizeMode(c, QHeaderView::Interactive);
    table->setColumnWidth(0, 230); table->setColumnWidth(1, 140); table->setColumnWidth(2, 90); table->setColumnWidth(3, 60);
    table->setColumnHidden(3, mode == Mode::Repositories);
    table->horizontalHeader()->setSectionResizeMode(4, QHeaderView::Stretch);
    table->horizontalHeader()->setMinimumSectionSize(50); table->setTextElideMode(Qt::ElideRight);
    table->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    results->addWidget(table); resultLayout->addWidget(results, 1);
    auto *actions = new QHBoxLayout;
    install = new QPushButton(QIcon::fromTheme("list-add"), "Install selected…"); install->setObjectName("aurInstall"); install->setProperty("aurPrimary", true);
    remove = new QPushButton(QIcon::fromTheme("edit-delete"), "Uninstall selected…"); remove->setObjectName("aurRemove");
    remove->setVisible(mode == Mode::Helpers);
    actions->addWidget(install); actions->addWidget(remove); actions->addStretch();
    auto *actionHint = label("Package changes open in a terminal."); actionHint->setWordWrap(false);
    actions->addWidget(actionHint); resultLayout->addLayout(actions);
    outer->addWidget(resultCard, 1);
    status = label("Ready to search.", "aurStatus"); outer->addWidget(status);
    auto *detailToggle = new QToolButton; detailToggle->setObjectName("aurDetailsToggle"); detailToggle->setText("Details");
    detailToggle->setCheckable(true); detailToggle->setArrowType(Qt::RightArrow); detailToggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    outer->addWidget(detailToggle, 0, Qt::AlignLeft);
    details = new QPlainTextEdit; details->setObjectName("aurDetails"); details->setReadOnly(true); details->setMaximumHeight(130);
    details->setMinimumHeight(80); details->hide(); outer->addWidget(details);
    connect(detailToggle, &QToolButton::toggled, this, [this, detailToggle](bool open) { details->setVisible(open); detailToggle->setArrowType(open ? Qt::DownArrow : Qt::RightArrow); });
    connect(search, &QPushButton::clicked, this, &AurPage::startSearch);
    connect(query, &QLineEdit::returnPressed, this, [this] { if (!busy) startSearch(); });
    connect(helper, &QComboBox::currentIndexChanged, this, &AurPage::refreshHelpers);
    connect(field, &QComboBox::currentIndexChanged, this, &AurPage::showResults);
    connect(match, &QComboBox::currentIndexChanged, this, &AurPage::showResults);
    connect(table, &QTableWidget::itemSelectionChanged, this, &AurPage::updateActions);
    connect(install, &QPushButton::clicked, this, [this] { packageAction(false); });
    connect(remove, &QPushButton::clicked, this, [this] { packageAction(true); });
    connect(&worker, &QProcess::readyReadStandardOutput, this, [this] {
        output += worker.readAllStandardOutput();
        if (output.size() > 4 * 1024 * 1024) { tooLarge = true; worker.kill(); }
    });
    connect(&worker, &QProcess::readyReadStandardError, this, [this] {
        errors += worker.readAllStandardError();
        if (errors.size() > 1024 * 1024) { tooLarge = true; worker.kill(); }
    });
    connect(&worker, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, &AurPage::finishSearch);
    connect(&worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) { errors = worker.errorString().toUtf8(); finishSearch(-1, QProcess::CrashExit); }
    });
    deadline.setSingleShot(true); deadline.setInterval(60000);
    connect(&deadline, &QTimer::timeout, this, [this] { timedOut = true; worker.kill(); });
    poll.setInterval(2000); connect(&poll, &QTimer::timeout, this, [this] { if (isVisible()) refreshHelpers(); }); poll.start();
    refreshHelpers();
}

AurPage::~AurPage() { worker.disconnect(this); if (worker.state() != QProcess::NotRunning) { worker.kill(); worker.waitForFinished(1000); } }
void AurPage::refresh() { refreshHelpers(); if (!busy && !searchedQuery.isEmpty()) startSearch(); }
void AurPage::focusSearch() { query->setFocus(); }
void AurPage::showEvent(QShowEvent *event) { QWidget::showEvent(event); refreshHelpers(); }
QString AurPage::selectedHelper() const {
    if (mode == Mode::Repositories) return QStandardPaths::findExecutable("pacman").isEmpty() ? QString() : QString("pacman");
    const auto chosen = helper->currentData().toString();
    if (!chosen.isEmpty()) return HyperPanel::aurHelperInstalled(chosen) ? chosen : QString();
    for (const auto &name : {QString("yay"), QString("paru")}) if (HyperPanel::aurHelperInstalled(name)) return name;
    return {};
}
void AurPage::refreshHelpers() {
    for(const auto &name:{QString("yay"),QString("paru")}){
        const bool installed=HyperPanel::aurHelperInstalled(name);
        auto *button=name=="yay"?installYay:installParu;auto *state=name=="yay"?yayStatus:paruStatus;
        state->setText(installed?"Installed · ready to use":"Not installed");
        button->setText(installed?title(name)+" installed":"Install "+title(name));button->setEnabled(!installed);
        button->setIcon(installed?style()->standardIcon(QStyle::SP_DialogApplyButton):QIcon::fromTheme("system-software-install",style()->standardIcon(QStyle::SP_ArrowDown)));
        button->setToolTip(installed?"Reinstall or remove this helper in Manage helpers.":"Install "+title(name)+" to find repository and AUR packages.");
    }
    const auto chosen = selectedHelper();
    const auto automatic = HyperPanel::aurHelperInstalled("yay") ? "Yay" : HyperPanel::aurHelperInstalled("paru") ? "Paru" : "none installed";
    helper->setItemText(0, "Automatic · " + QString(automatic));
    search->setEnabled(busy || !chosen.isEmpty());
    search->setToolTip(chosen.isEmpty() ? "Install Yay above (recommended), or choose Paru." : "Search using " + title(chosen));
    if (!busy && packages.isEmpty() && searchedQuery.isEmpty()) {
        emptyTitle->setText(chosen.isEmpty() ? "Choose a package helper" : "Find your next app");
        emptyHint->setText(chosen.isEmpty() ? (mode == Mode::Repositories ? "Pacman is not available on this system." : "Install Yay above (recommended), or choose Paru. One helper is enough to get started.") : mode == Mode::Repositories ? "Search the configured repositories. Community packages are in Yay & Paru." : "Search above to see packages from your repositories and the AUR.");
    }
    updateActions();
}
void AurPage::rebuildMenu() {
    manage->clear();
    auto *both = manage->addAction("Install both helpers…", this, [this] { helperAction("both", "install"); });
    both->setEnabled(!HyperPanel::aurHelperInstalled("yay") || !HyperPanel::aurHelperInstalled("paru"));
    for (const auto &name : {QString("yay"), QString("paru")}) {
        const bool installed = HyperPanel::aurHelperInstalled(name);
        auto *menu = manage->addMenu(title(name) + (installed ? " · Installed" : " · Not installed"));
        menu->addAction(installed ? "Reinstall…" : "Install…", this, [this, name, installed] { helperAction(name, installed ? "reinstall" : "install"); });
        if (installed) menu->addAction("Uninstall…", this, [this, name] { helperAction(name, "remove"); });
    }
    manage->addSeparator(); manage->addAction("Clear package cache…", this, &AurPage::clearCacheRequested);
}
void AurPage::startSearch() {
    if (busy) { cancelled = true; worker.kill(); return; }
    const auto chosen = selectedHelper(); const auto text = query->text().trimmed();
    if (chosen.isEmpty() || text.isEmpty()) { query->setFocus(); return; }
    busy = true; cancelled = timedOut = tooLarge = false; output.clear(); errors.clear(); packages.clear();
    searchedQuery = text; table->setRowCount(0); results->setCurrentIndex(0);
    emptyTitle->setText("Searching…"); emptyHint->setText("Looking for “" + text + "” using " + title(chosen) + '.');
    resultTitle->setText("Packages"); search->setText("Cancel"); search->setIcon(QIcon::fromTheme("process-stop"));
    query->setEnabled(false); helper->setEnabled(false); field->setEnabled(false); match->setEnabled(false); updateActions();
    setStatus("Searching with " + title(chosen) + "…");
    auto env = QProcessEnvironment::systemEnvironment(); env.insert("LC_ALL", "C"); worker.setProcessEnvironment(env);
    // Separate argv keeps names beginning with '-' and shell metacharacters out of options/shell code.
    worker.start(QStandardPaths::findExecutable(chosen), {"-Ss", "--color", "never", "--", text}); deadline.start();
}
void AurPage::finishSearch(int code, QProcess::ExitStatus exit) {
    if (!busy) return;
    deadline.stop(); busy = false; output += worker.readAllStandardOutput(); errors += worker.readAllStandardError();
    query->setEnabled(true); helper->setEnabled(true); field->setEnabled(true); match->setEnabled(true);
    search->setText("Search"); search->setIcon(QIcon::fromTheme("edit-find"));
    if (!cancelled && !timedOut && !tooLarge && exit == QProcess::NormalExit && (code == 0 || (code == 1 && errors.trimmed().isEmpty()))) {
        packages = AurSearch::parse(QString::fromUtf8(output)); showResults();
        setStatus(QString("%1 packages shown.").arg(table->rowCount()), QString::fromUtf8(errors));
    } else {
        packages.clear(); results->setCurrentIndex(0); emptyTitle->setText(cancelled ? "Search cancelled" : "Search could not finish");
        const auto message = cancelled ? "Change your search and try again." : timedOut ? "The search timed out. Check your connection and try again." : tooLarge ? "Too many results. Try a more specific package name." : "Check your connection and helper setup. Details are available below.";
        emptyHint->setText(message); setStatus(message, QString::fromUtf8(errors));
    }
    refreshHelpers();
}
void AurPage::showResults() {
    if (busy || searchedQuery.isEmpty()) return;
    table->setRowCount(0);
    for (int index = 0; index < packages.size(); ++index) {
        const auto &package = packages[index];
        if (!AurSearch::matches(package, searchedQuery, field->currentIndex(), match->currentIndex() == 1)) continue;
        const int row = table->rowCount(); table->insertRow(row);
        const QStringList values{package.name, package.version, package.repository, package.votes.isEmpty() ? "—" : package.votes, package.description};
        for (int column = 0; column < values.size(); ++column) {
            auto *item = new QTableWidgetItem(values[column]); item->setData(Qt::UserRole, index);
            item->setToolTip(column == 0 && package.installed ? package.name + " · Installed" : values[column]);
            if (column == 0) { auto font = item->font(); font.setBold(true); item->setFont(font); if (package.installed) item->setIcon(QIcon::fromTheme("emblem-default", style()->standardIcon(QStyle::SP_DialogApplyButton))); }
            table->setItem(row, column, item);
        }
    }
    resultTitle->setText(QString("Packages · %1").arg(table->rowCount()));
    results->setCurrentIndex(table->rowCount() ? 1 : 0);
    if (!table->rowCount()) { emptyTitle->setText("No matching packages"); emptyHint->setText("Try another name or a broader match."); }
    setStatus(QString("%1 packages shown.").arg(table->rowCount()), QString::fromUtf8(errors));
    updateActions();
}
void AurPage::updateActions() {
    const auto *item = table->item(table->currentRow(), 0);
    const bool selected = !busy && item && !selectedHelper().isEmpty();
    install->setEnabled(selected);
    const bool installed = selected && packages.value(item->data(Qt::UserRole).toInt()).installed;
    install->setText(installed ? "Reinstall selected…" : "Install selected…");
    remove->setEnabled(installed);
}
void AurPage::setStatus(const QString &message, const QString &detail) { status->setText(message); details->setPlainText(detail.isEmpty() ? message : detail); }
bool AurPage::launch(const QStringList &arguments, const QString &message) {
    qint64 pid = 0;
    if (!QProcess::startDetached(terminal, arguments, QString(), &pid)) {
        setStatus("Could not open the terminal. Check your terminal settings."); return false;
    }
    setStatus(message);
    TerminalExit::watch(this, pid, [this] { refreshHelpers(); }); return true;
}
void AurPage::packageAction(bool uninstall) {
    const auto *item = table->item(table->currentRow(), 0); const auto chosen = selectedHelper();
    if (busy || !item || chosen.isEmpty()) return;
    const auto package = packages.value(item->data(Qt::UserRole).toInt());
    if (uninstall && !package.installed) return;
    QMessageBox prompt(QMessageBox::Question, uninstall ? "Uninstall package" : "Install package",
        QString("%1 %2 using %3?").arg(uninstall ? "Uninstall" : package.installed ? "Reinstall" : "Install", package.name, title(chosen)),
        QMessageBox::Yes | QMessageBox::No, this);
    prompt.setTextFormat(Qt::PlainText); prompt.setProperty("xetalWindowSized", true);
    prompt.setInformativeText(chosen == "pacman" ? "Repositories will be refreshed and pending system updates included. Review the full transaction in the terminal." : "Review the package changes and password prompts in the terminal.");
    QCheckBox *skipReview = nullptr;
    if (!uninstall && chosen != "pacman") { skipReview = new QCheckBox("Skip build-file review", &prompt); prompt.setCheckBox(skipReview); }
    if (prompt.exec() != QMessageBox::Yes) return;
    const auto script = uninstall ? terminalCommand((chosen == "pacman" ? "sudo pacman" : shQuote(chosen)) + " -Rns -- " + shQuote(package.name))
        : PackageInstall::script(chosen, title(chosen), package.target(), skipReview && skipReview->isChecked());
    launch({"-e", "bash", "-c", script}, "Opened in the terminal. Review and confirm the package changes there.");
}
void AurPage::helperAction(const QString &name, const QString &action) {
    QMessageBox prompt(QMessageBox::Question, "Manage helpers",
        QString("%1 %2?").arg(action == "remove" ? "Uninstall" : action == "reinstall" ? "Reinstall" : "Install", title(name)),
        QMessageBox::Yes | QMessageBox::No, this);
    prompt.setTextFormat(Qt::PlainText); prompt.setProperty("xetalWindowSized", true);
    prompt.setInformativeText("Review the changes in the terminal. Sudo asks for your password there.");
    if (prompt.exec() != QMessageBox::Yes) return;
    if (action == "remove") {
        launch({"-e", "bash", "-c", terminalCommand("sudo pacman -Rns -- " + shQuote(name))}, "Helper removal opened in the terminal."); return;
    }
    const auto script = root + "/control_panel/aur_helper_install.py";
    if (!QFileInfo::exists(script)) { setStatus("The helper installer is missing. Please update Hyper Fusion."); return; }
    QStringList args{"-e", "python3", script, "--wait"}; if (action == "reinstall") args << "--reinstall"; args << name;
    launch(args, "Helper setup opened in the terminal. This page updates when installation finishes.");
}
