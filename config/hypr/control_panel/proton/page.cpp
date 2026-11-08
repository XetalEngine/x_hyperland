#include "page.h"
#include "src/util.h"
#include <QDesktopServices>
#include <QMimeData>
#include <QUrl>

namespace XetalProton {
namespace Ui {
QString text(const std::string &value) { return QString::fromStdString(value); }
QPushButton *button(const QString &text,const QString &name,QBoxLayout *layout,std::function<void()> action) {
    auto *result=new QPushButton(text); result->setObjectName(name); layout->addWidget(result);
    QObject::connect(result,&QPushButton::clicked,result,std::move(action)); return result;
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
    auto *intro=new QLabel("<b>Proton · Windows applications</b>"); layout->addWidget(intro);
    hint("Create a separate Windows prefix for each app, or share one between related apps. Download and run Proton here without Steam.",layout);
    auto *prefixRow=new QHBoxLayout;
    prefixRow->addWidget(new QLabel("Prefix:")); prefixChoice=new QComboBox; prefixChoice->setObjectName("protonPrefix"); prefixChoice->setMinimumWidth(180);
    prefixChoice->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); prefixRow->addWidget(prefixChoice,1);
    button("New…","protonNewPrefix",prefixRow,[this]{bool ok=false; const auto name=QInputDialog::getText(this,"New Windows prefix","Name:",QLineEdit::Normal,{},&ok); if(ok) model.createPrefix(name);});
    button("Import…","protonImportPrefix",prefixRow,[this]{const auto path=QFileDialog::getExistingDirectory(this,"Import Proton prefix",text(model.config.prefixes_root)); if(!path.isEmpty()) model.importPrefix(path);});
    button("Manage…","protonManagePrefix",prefixRow,[this]{managePrefix();});
    prefixRow->addWidget(new QLabel("Proton:")); protonChoice=new QComboBox; protonChoice->setObjectName("protonVersion");
    protonChoice->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); prefixRow->addWidget(protonChoice,1);
    button("Reload","protonReload",prefixRow,[this]{if(!model.busy()) model.reload();}); layout->addLayout(prefixRow);
    prefixPath=hint({},layout); prefixPath->setTextInteractionFlags(Qt::TextSelectableByMouse);
    tabs=new QTabWidget; tabs->setObjectName("protonSections"); layout->addWidget(tabs,1);
    buildLibrary(); buildTools(); buildDependencies(); buildProcesses(); buildSettings();
    auto *jobRow=new QHBoxLayout; progress=new QProgressBar; progress->setObjectName("protonProgress"); jobRow->addWidget(progress,1);
    cancelButton=button("Cancel","protonCancel",jobRow,[this]{model.cancel();}); layout->addLayout(jobRow);
    status=hint("Choose Downloads to install Proton, then create a prefix in Library.",layout); status->setObjectName("protonStatus");
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
    discoverSteam->setChecked(model.config.discover_steam); iconSize->setValue(std::clamp(model.config.icon_size,32,128));
    settingsPaths->setText("Prefixes: "+text(model.config.prefixes_root)+"\nTools and runtimes: "+text(util::data_dir())+"\nConfiguration: "+text(config_path()));
    if(model.notice.isEmpty())status->setText(model.current.empty() ? "Choose Downloads to install Proton, then create a prefix in Library." : "Ready to launch programs in the selected prefix.");
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
    auto *page=new QWidget;auto *layout=new QVBoxLayout(page);
    hint("Each prefix keeps its own Windows files, registry and installed dependencies. Prefixes separate application environments; they are not a security sandbox.",layout);
    settingsPaths=hint({},layout);settingsPaths->setTextInteractionFlags(Qt::TextSelectableByMouse);
    auto *row=new QHBoxLayout;
    button("Choose prefixes folder…","protonPrefixesRoot",row,[this]{const auto path=QFileDialog::getExistingDirectory(this,"New prefixes folder",text(model.config.prefixes_root));if(!path.isEmpty()){auto next=model.config;next.prefixes_root=QFileInfo(path).absoluteFilePath().toStdString();model.save(next);}});
    button("Open prefixes","protonOpenPrefixes",row,[this]{openFolder(text(model.config.prefixes_root));});
    button("Open tool storage","protonOpenStorage",row,[]{openFolder(text(util::data_dir()));});row->addStretch();layout->addLayout(row);
    discoverSteam=new QCheckBox("Discover existing Steam tools and prefixes (optional)");discoverSteam->setObjectName("protonDiscoverSteam");layout->addWidget(discoverSteam);
    connect(discoverSteam,&QCheckBox::toggled,this,[this](bool value){if(!refreshing){auto next=model.config;next.discover_steam=value;model.save(next);}});
    launchAdded=new QCheckBox("Launch programs immediately after adding a shortcut");launchAdded->setChecked(true);launchAdded->setObjectName("protonLaunchAdded");layout->addWidget(launchAdded);
    auto *sizeRow=new QHBoxLayout;sizeRow->addWidget(new QLabel("Shortcut icon size:"));iconSize=new QSpinBox;iconSize->setRange(32,128);iconSize->setSingleStep(8);sizeRow->addWidget(iconSize);sizeRow->addStretch();layout->addLayout(sizeRow);
    connect(iconSize,qOverload<int>(&QSpinBox::valueChanged),this,[this](int size){if(!refreshing){auto next=model.config;next.icon_size=size;model.save(next);}});
    hint("The first launch may download the UMU runtime. Dependencies, prefixes and downloaded Proton versions are stored separately from Hyper Fusion updates.",layout);
    hint("Optional wrappers need their corresponding host tools: GameMode, gamescope, MangoHud or vkBasalt. Winetricks components may also need cabextract. Errors and download progress appear in Processes and logs.",layout);
    layout->addStretch();tabs->addTab(page,"Settings");
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
