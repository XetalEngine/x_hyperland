#include "page.h"
#include "src/util.h"
#include <QDesktopServices>
#include <QMimeData>
#include <QUrl>
#include <tuple>

namespace XetalProton {
namespace Ui {
namespace {
// Paint the native themed button at a slightly smaller size while pressed.
// Only the paint changes: the layout and clickable area stay in place.
class FeedbackButton final : public QPushButton {
    QVariantAnimation releaseAnimation;
    qreal pressure=0;
    void releasePressure() {
        releaseAnimation.setStartValue(pressure);releaseAnimation.setEndValue(0.);releaseAnimation.start();
    }
public:
    explicit FeedbackButton(const QString &text) : QPushButton(text) {
        setCursor(Qt::PointingHandCursor);
        releaseAnimation.setDuration(280);releaseAnimation.setEasingCurve(QEasingCurve::OutCubic);
        connect(&releaseAnimation,&QVariantAnimation::valueChanged,this,[this](const QVariant &value){pressure=value.toReal();update();});
        connect(this,&QPushButton::pressed,this,[this]{releaseAnimation.stop();pressure=1;repaint();});
        connect(this,&QPushButton::released,this,[this]{releasePressure();});
    }
protected:
    bool event(QEvent *event) override {
        const bool handled=QPushButton::event(event);
        // Popup menus and canceled presses can clear isDown without emitting
        // released. Their highlight must settle back too.
        if(pressure>0 && !isDown() && releaseAnimation.state()!=QAbstractAnimation::Running)releasePressure();
        return handled;
    }
    void paintEvent(QPaintEvent *) override {
        QStylePainter painter(this);QStyleOptionButton option;initStyleOption(&option);
        const qreal inset=1.5*pressure;
        painter.translate(inset,inset);
        painter.scale((width()-2*inset)/qMax(1,width()),(height()-2*inset)/qMax(1,height()));
        painter.setOpacity(1.-.25*pressure);
        painter.drawControl(QStyle::CE_PushButton,option);
        if(pressure>0){
            auto tint=palette().color(objectName()=="protonLaunch"?QPalette::HighlightedText:QPalette::ButtonText);
            tint.setAlphaF(.24*pressure);painter.setOpacity(1.);painter.setRenderHint(QPainter::Antialiasing);
            painter.setPen(Qt::NoPen);painter.setBrush(tint);painter.drawRoundedRect(option.rect.adjusted(2,2,-2,-2),6,6);
        }
    }
};
}
QString text(const std::string &value) { return QString::fromStdString(value); }
QPushButton *button(const QString &text,const QString &name,QBoxLayout *layout,std::function<void()> action) {
    auto *result=new FeedbackButton(text); result->setObjectName(name); layout->addWidget(result);
    QObject::connect(result,&QPushButton::clicked,result,std::move(action)); return result;
}
QIcon icon(const QString &name,QStyle::StandardPixmap fallback) {
    static const QMap<QString,QStyle::StandardPixmap> fallbacks={
        {"media-playback-start",QStyle::SP_MediaPlay},{"utilities-system-monitor",QStyle::SP_ComputerIcon},
        {"list-add",QStyle::SP_FileDialogNewFolder},{"preferences-system",QStyle::SP_FileDialogDetailedView},
        {"folder-open",QStyle::SP_DirOpenIcon},{"document-open",QStyle::SP_DialogOpenButton},
        {"drive-harddisk",QStyle::SP_DriveHDIcon},{"view-refresh",QStyle::SP_BrowserReload},
        {"view-grid",QStyle::SP_FileDialogListView},{"view-more-symbolic",QStyle::SP_ArrowDown},
        {"applications-system",QStyle::SP_ComputerIcon},{"download",QStyle::SP_ArrowDown},
        {"edit-delete",QStyle::SP_TrashIcon},{"document-save-as",QStyle::SP_DialogSaveButton},
        {"internet-web-browser",QStyle::SP_DialogHelpButton},{"dialog-ok-apply",QStyle::SP_DialogApplyButton}};
    fallback=fallbacks.value(name,fallback);
    return QIcon::fromTheme(name,QApplication::style()->standardIcon(fallback));
}
void decorate(QAbstractButton *button,const QString &iconName,const QString &description,bool iconOnly) {
    const auto label=description.isEmpty()?button->text():description;
    button->setIcon(icon(iconName));button->setIconSize({20,20});
    button->setToolTip(label);button->setAccessibleName(label);button->setMinimumHeight(36);
    if(iconOnly){button->setText({});button->setFixedSize(40,38);}
}
QLabel *hint(const QString &text,QBoxLayout *layout) {
    auto *label=new QLabel(text); label->setWordWrap(true); label->setTextFormat(Qt::PlainText);
    label->setObjectName("muted"); layout->addWidget(label); return label;
}
QTableWidget *table(const QStringList &headers,const QString &name) {
    auto *result=new QTableWidget(0,headers.size()); result->setObjectName(name);
    result->setHorizontalHeaderLabels(headers); result->verticalHeader()->hide();
    result->setSelectionBehavior(QAbstractItemView::SelectRows);
    result->setSelectionMode(QAbstractItemView::SingleSelection);
    result->setEditTriggers(QAbstractItemView::NoEditTriggers);
    result->setAlternatingRowColors(true); result->setWordWrap(false);
    result->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
    result->horizontalHeader()->setStretchLastSection(true);
    result->setMinimumHeight(120); return result;
}
void row(QTableWidget *table,int index,const QStringList &values,const QVariant &key) {
    for (int column=0;column<values.size();++column) {
        auto *item=new QTableWidgetItem(values[column]); item->setToolTip(values[column]);
        if (!column) item->setData(Qt::UserRole,key);
        table->setItem(index,column,item);
    }
}
}
using namespace Ui;
Page::Page(QWidget *parent) : QWidget(parent), model(this) {
    setObjectName("protonTab"); setAcceptDrops(true);
    auto *layout=new QVBoxLayout(this); layout->setContentsMargins(8,8,8,8);
    auto *header=new QHBoxLayout;auto *titles=new QVBoxLayout;titles->setSpacing(3);
    auto *intro=new QLabel("Windows apps");intro->setObjectName("protonHeading");intro->setStyleSheet("font-size:26px;font-weight:700;background:transparent;");titles->addWidget(intro);
    hint("Your apps, ready when you are.",titles);header->addLayout(titles,1);
    header->addWidget(new QLabel("Environment"));prefixChoice=new QComboBox;prefixChoice->setObjectName("protonPrefix");
    prefixChoice->setMinimumWidth(150);prefixChoice->setMaximumWidth(290);prefixChoice->setMinimumHeight(36);
    prefixChoice->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    prefixChoice->setToolTip("Choose the Windows environment whose apps you want to use. Manage environments in Settings.");
    prefixChoice->setAccessibleName("Windows environment");header->addWidget(prefixChoice);layout->addLayout(header);
    tabs=new QTabWidget; tabs->setObjectName("protonSections"); layout->addWidget(tabs,1);
    buildLibrary(); buildTools(); buildDependencies(); buildProcesses(); buildSettings();
    const QStringList tabIcons={"view-grid","download","applications-system","utilities-system-monitor","preferences-system"};
    for(int i=0;i<tabs->count();++i)tabs->setTabIcon(i,icon(tabIcons[i]));
    auto *jobRow=new QHBoxLayout; progress=new QProgressBar; progress->setObjectName("protonProgress"); jobRow->addWidget(progress,1);
    cancelButton=button("Cancel","protonCancel",jobRow,[this]{model.cancel();}); layout->addLayout(jobRow);
    status=hint("Get Proton in Downloads, then create an environment in Settings.",layout); status->setObjectName("protonStatus");
    connect(prefixChoice,qOverload<int>(&QComboBox::currentIndexChanged),this,[this](int i){if(!refreshing && i>=0) model.selectPrefix(prefixChoice->itemData(i).toString().toStdString());});
    connect(protonChoice,qOverload<int>(&QComboBox::currentIndexChanged),this,[this](int i){if(!refreshing && i>=0) model.selectProton(protonChoice->itemData(i).toString().toStdString());});
    connect(&model,&Controller::changed,this,&Page::refresh);
    connect(&model,&Controller::taskChanged,this,&Page::refreshTask);
    connect(&model,&Controller::processChanged,this,&Page::refreshProcesses);
    connect(&model,&Controller::message,this,[this](const QString &s){status->setText(s); events->appendPlainText(s);});
    connect(tabs,&QTabWidget::currentChanged,this,[this]{if(model.loaded) {refreshDependencies();refreshProcesses();}});
    logTimer.setInterval(700); connect(&logTimer,&QTimer::timeout,this,&Page::readLog); logTimer.start();
    progress->hide(); cancelButton->hide();
}
void Page::showEvent(QShowEvent *event) {
    QWidget::showEvent(event);
    if (!firstShow) return;
    firstShow=false;
    QTimer::singleShot(0,this,[this]{if(model.reload() && !model.installed.empty() && !qEnvironmentVariableIsSet("XETALPROTON_OFFLINE")) model.checkUpdates();});
}
void Page::focusSearch() {tabs->setCurrentIndex(0);librarySearch->setFocus();librarySearch->selectAll();}
void Page::refresh() {
    refreshing=true;
    prefixChoice->clear(); for(const auto &p:model.prefixes) prefixChoice->addItem(text(p.name),text(p.path));
    prefixChoice->setCurrentIndex(prefixChoice->findData(text(model.current)));
    protonChoice->clear(); for(const auto &p:model.discovery.protons) protonChoice->addItem(text(p.name)+" · "+text(p.version),text(p.dir));
    const auto *chosen=model.proton(model.current);
    if(chosen) protonChoice->setCurrentIndex(protonChoice->findData(text(chosen->dir)));
    else {
        const auto it=model.config.prefix_proton.find(model.current);
        if(it!=model.config.prefix_proton.end() && !it->second.empty()) {protonChoice->addItem("Unavailable: "+text(util::basename(it->second)),text(it->second));protonChoice->setCurrentIndex(protonChoice->count()-1);}
        else protonChoice->setCurrentIndex(-1);
    }
    protonChoice->setEnabled(!model.current.empty()); prefixPath->setText(text(model.current));
    for(const auto *name:{"protonManagePrefix","protonDriveC","protonRunOnce","protonHelpers","protonInit"})findChild<QPushButton *>(name)->setEnabled(!model.current.empty());
    discoverSteam->setChecked(model.config.discover_steam); iconSize->setValue(std::clamp(model.config.icon_size,32,128));
    settingsPaths->setText("Prefixes: "+text(model.config.prefixes_root)+"\nTools and runtimes: "+text(util::data_dir())+"\nConfiguration: "+text(config_path()));
    if(model.notice.isEmpty())status->setText(model.current.empty() ? "Get Proton in Downloads, then create an environment in Settings." : "Double-click an app to launch it.");
    refreshing=false;
    refreshLibrary();refreshTools();refreshDependencies();refreshProcesses();refreshTask();
}
void Page::refreshTask() {
    progress->setVisible(model.busy()); cancelButton->setVisible(model.busy()); cancelButton->setEnabled(model.task!=Controller::Remove);
    progress->setRange(0,model.total ? 1000 : 0);
    if(model.total) progress->setValue(int(std::min(1000.0,double(model.done)/double(model.total)*1000)));
    progress->setFormat(model.phase+(model.total ? " · "+text(util::human_size(model.done))+" / "+text(util::human_size(model.total)) : ""));
    providers->setEnabled(!model.busy()); older->setEnabled(!model.busy() && model.more);
    removeInstalled->setEnabled(!model.busy() && installedTable->currentRow()>=0);
    useInstalled->setEnabled(!model.current.empty() && installedTable->currentRow()>=0);
    selectDownload();selectDependency();
}
bool Page::confirm(const QString &title,const QString &text) {
    return QMessageBox::question(this,title,text,QMessageBox::Yes|QMessageBox::Cancel,QMessageBox::Cancel)==QMessageBox::Yes;
}
void Page::openFolder(const QString &path) {
    if(!QFileInfo(path).isDir()) return;
    const auto root=qEnvironmentVariable("XETAL_HYPR_ROOT",QDir::homePath()+"/.config/hypr");
    const auto helper=root+"/scripts/file-manager.sh";
    if(QFileInfo::exists(helper)) QProcess::startDetached(helper,{path});
    else QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}
void Page::openFile(const QString &path) { QDesktopServices::openUrl(QUrl::fromLocalFile(path)); }
void Page::buildProcesses() {
    auto *page=new QWidget; auto *layout=new QVBoxLayout(page);
    hint("Launched applications and installers keep running when you close this panel. Logs include first-launch runtime downloads.",layout);
    processTable=table({"Application","PID","State","Started","Prefix"},"protonProcesses");layout->addWidget(processTable,1);
    auto *actions=new QHBoxLayout;
    button("Show log","protonProcessLog",actions,[this]{const auto row=processTable->currentRow();if(row>=0)viewLog(processTable->item(row,0)->data(Qt::UserRole+1).toString());});
    for(bool force:{false,true}) button(force?"Force stop":"Terminate",force?"protonKill":"protonTerminate",actions,[this,force]{
        const int row=processTable->currentRow();if(row<0)return;
        if(force && !confirm("Force stop application","Force stopping may lose unsaved Windows data. Continue?"))return;
        model.stopProcess(processTable->item(row,0)->data(Qt::UserRole).toLongLong(),force);
    });
    button("Open full log","protonOpenLog",actions,[this]{if(!activeLog.isEmpty())openFile(activeLog);});
    button("Open logs folder","protonLogsFolder",actions,[]{openFolder(text(util::logs_dir()));}); actions->addStretch();layout->addLayout(actions);
    processLog=new QPlainTextEdit;processLog->setObjectName("protonLog");processLog->setReadOnly(true);processLog->setMaximumBlockCount(2000);layout->addWidget(processLog,1);
    events=new QPlainTextEdit;events->setObjectName("protonEvents");events->setReadOnly(true);events->setMaximumBlockCount(250);events->setMaximumHeight(115);layout->addWidget(events);
    connect(processTable,&QTableWidget::itemSelectionChanged,this,[this]{const int row=processTable->currentRow();if(row>=0){activeLog=processTable->item(row,0)->data(Qt::UserRole+1).toString();readLog();}});
    tabs->addTab(page,"Processes and logs");
}
void Page::refreshProcesses() {
    const auto row=processTable->currentRow();const auto id=row>=0?processTable->item(row,0)->data(Qt::UserRole):QVariant();
    const QSignalBlocker block(processTable);processTable->setRowCount(int(model.processes.size()));
    int i=0;for(const auto &p:model.processes) {
        Ui::row(processTable,i,{text(p.label),QString::number(p.pid),p.running?"Running":"Exited · "+QString::number(p.exit_code),text(p.started),text(p.prefix_path)},qlonglong(p.pid));
        processTable->item(i,0)->setData(Qt::UserRole+1,text(p.log_path));
        if(id.toLongLong()==p.pid)processTable->selectRow(i);++i;
    }
    if(activeLog.isEmpty() && !model.processes.empty()) activeLog=text(model.processes.back().log_path);
    selectDependency();
}
void Page::viewLog(const QString &path) {activeLog=path;tabs->setCurrentIndex(3);readLog();}
void Page::readLog() {
    if(activeLog.isEmpty() || !isVisible() || tabs->currentIndex()!=3)return;
    QFile file(activeLog);if(!file.open(QIODevice::ReadOnly))return;
    if(file.size()>65536)file.seek(file.size()-65536);
    const auto text=QString::fromUtf8(file.read(65536));
    if(processLog->toPlainText()!=text) {
        auto *bar=processLog->verticalScrollBar();const bool follow=bar->value()>=bar->maximum()-2;const int old=bar->value();
        processLog->setPlainText(text);bar->setValue(follow?bar->maximum():old);
    }
}
void Page::buildSettings() {
    auto *scroll=new QScrollArea;scroll->setObjectName("protonSettings");scroll->setWidgetResizable(true);scroll->setFrameShape(QFrame::NoFrame);
    auto *page=new QWidget;auto *layout=new QVBoxLayout(page);layout->setContentsMargins(16,18,16,18);layout->setSpacing(18);scroll->setWidget(page);
    auto section=[layout](const QString &title){auto *group=new QGroupBox(title);auto *content=new QVBoxLayout(group);content->setContentsMargins(16,20,16,16);content->setSpacing(12);layout->addWidget(group);return content;};
    auto *environment=section("Windows environment");
    hint("Each environment (a Wine prefix) keeps its own apps, Windows files and settings. Choose the active one at the top of this page.",environment);
    auto *prefixRow=new QHBoxLayout;
    auto *create=button("New…","protonNewPrefix",prefixRow,[this]{bool ok=false;const auto name=QInputDialog::getText(this,"New Windows environment","Name:",QLineEdit::Normal,{},&ok);if(ok)model.createPrefix(name);});decorate(create,"list-add");
    auto *import=button("Import…","protonImportPrefix",prefixRow,[this]{const auto path=QFileDialog::getExistingDirectory(this,"Import Proton environment",text(model.config.prefixes_root));if(!path.isEmpty())model.importPrefix(path);});decorate(import,"document-open");
    auto *manage=button("Manage…","protonManagePrefix",prefixRow,[this]{managePrefix();});decorate(manage,"preferences-system");
    auto *reload=button("Reload","protonReload",prefixRow,[this]{if(!model.busy())model.reload();});decorate(reload,"view-refresh","Reload environments and installed Proton versions",true);
    prefixRow->addStretch();environment->addLayout(prefixRow);
    auto *runnerRow=new QHBoxLayout;runnerRow->addWidget(new QLabel("Proton version"));
    protonChoice=new QComboBox;protonChoice->setObjectName("protonVersion");protonChoice->setMinimumContentsLength(22);
    protonChoice->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);runnerRow->addWidget(protonChoice,1);
    auto *get=button("Get Proton","protonGetProton",runnerRow,[this]{tabs->setCurrentIndex(1);});decorate(get,"download");environment->addLayout(runnerRow);
    prefixPath=hint({},environment);prefixPath->setTextInteractionFlags(Qt::TextSelectableByMouse);
    auto *tools=section("Windows tools");
    hint("Tools and maintenance for the selected environment.",tools);
    auto *toolRow=new QHBoxLayout;
    auto *drive=button("Open C: drive","protonDriveC",toolRow,[this]{openFolder(text(model.current)+"/pfx/drive_c");});decorate(drive,"drive-harddisk");
    auto *run=button("Run a file…","protonRunOnce",toolRow,[this]{addShortcut(true);});decorate(run,"system-run","Run a Windows file without adding it to your library");
    auto *helpers=button("More tools","protonHelpers",toolRow,[]{});decorate(helpers,"applications-system");auto *menu=new QMenu(helpers);
    for(const auto &entry:std::vector<std::tuple<QString,std::string,QString>>{
        {"Wine configuration","winecfg","preferences-system"},{"Registry Editor","regedit","preferences-other"},
        {"Windows Control Panel","control","preferences-system"},{"Task Manager","taskmgr","utilities-system-monitor"},
        {"Explorer","explorer","system-file-manager"},{"Command prompt","cmd","utilities-terminal"}}){
        auto *action=menu->addAction(icon(std::get<2>(entry)),std::get<0>(entry));connect(action,&QAction::triggered,this,[this,entry]{model.runTool(std::get<1>(entry));});
    }
    menu->addSeparator();connect(menu->addAction(icon("folder-open"),"Open environment folder"),&QAction::triggered,this,[this]{openFolder(text(model.current));});
    menu->addSeparator();
    connect(menu->addAction("Stop all programs in this environment"),&QAction::triggered,this,[this]{if(confirm("Stop environment","Stop all Windows programs in the selected environment?"))model.runTool("wineboot","-k");});
    connect(menu->addAction("Force stop this environment's wineserver"),&QAction::triggered,this,[this]{if(confirm("Force stop environment","Unsaved Windows data may be lost. Force stop this environment?"))model.forceStopPrefix();});
    helpers->setMenu(menu);toolRow->addStretch();tools->addLayout(toolRow);
    auto *maintenance=new QHBoxLayout;auto *init=button("Initialize / repair environment","protonInit",maintenance,[this]{model.runTool("wineboot","-u");});decorate(init,"view-refresh");
    auto *repair=button("Repair browser links","protonSettingsRepairHandlers",maintenance,[this]{if(model.syncDesktopHandlers())model.report("Browser sign-in handlers refreshed.");});decorate(repair,"internet-web-browser");maintenance->addStretch();tools->addLayout(maintenance);
    auto *library=section("Library preferences");
    discoverSteam=new QCheckBox("Include environments and Proton versions from Steam");discoverSteam->setObjectName("protonDiscoverSteam");library->addWidget(discoverSteam);
    connect(discoverSteam,&QCheckBox::toggled,this,[this](bool value){if(!refreshing){auto next=model.config;next.discover_steam=value;model.save(next);}});
    launchAdded=new QCheckBox("Launch apps immediately after adding them");launchAdded->setChecked(true);launchAdded->setObjectName("protonLaunchAdded");library->addWidget(launchAdded);
    auto *sizeRow=new QHBoxLayout;sizeRow->addWidget(new QLabel("App icon size"));iconSize=new QSpinBox;iconSize->setRange(32,128);iconSize->setSingleStep(8);sizeRow->addWidget(iconSize);sizeRow->addStretch();library->addLayout(sizeRow);
    connect(iconSize,qOverload<int>(&QSpinBox::valueChanged),this,[this](int size){if(!refreshing){auto next=model.config;next.icon_size=size;model.save(next);}});
    auto *storage=section("Storage");settingsPaths=hint({},storage);settingsPaths->setTextInteractionFlags(Qt::TextSelectableByMouse);
    auto *row=new QHBoxLayout;
    auto *choose=button("Choose folder…","protonPrefixesRoot",row,[this]{const auto path=QFileDialog::getExistingDirectory(this,"New environments folder",text(model.config.prefixes_root));if(!path.isEmpty()){auto next=model.config;next.prefixes_root=QFileInfo(path).absoluteFilePath().toStdString();model.save(next);}});decorate(choose,"folder-open");
    auto *prefixes=button("Environments","protonOpenPrefixes",row,[this]{openFolder(text(model.config.prefixes_root));});decorate(prefixes,"folder-open","Open the environments folder");
    auto *store=button("Tools and runtimes","protonOpenStorage",row,[]{openFolder(text(util::data_dir()));});decorate(store,"folder-open","Open downloaded Proton tools and runtimes");row->addStretch();storage->addLayout(row);
    hint("Apps, environments and downloaded tools are kept separately from desktop updates. The first app launch may download the UMU runtime.",storage);
    layout->addStretch();tabs->addTab(scroll,"Settings");
}
void Page::dragEnterEvent(QDragEnterEvent *event) {
    if(!event->mimeData()->hasUrls())return;
    for(const auto &url:event->mimeData()->urls()) if(url.isLocalFile() && QStringList{"exe","msi","bat","cmd"}.contains(QFileInfo(url.toLocalFile()).suffix().toLower())){event->acceptProposedAction();return;}
}
void Page::dropEvent(QDropEvent *event) {
    if(model.current.empty()){model.report("Create or select a prefix before dropping Windows programs.");return;}
    for(const auto &url:event->mimeData()->urls()) if(url.isLocalFile() && QStringList{"exe","msi","bat","cmd"}.contains(QFileInfo(url.toLocalFile()).suffix().toLower()))model.addShortcut(url.toLocalFile(),launchAdded->isChecked());
    event->acceptProposedAction();
}
}
