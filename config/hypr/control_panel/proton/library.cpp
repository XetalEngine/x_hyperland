#include "page.h"
#include "options.h"
#include "desktop.h"
#include "src/icons.h"
#include "src/util.h"
#include <QDesktopServices>
#include <QFutureWatcher>
#include <QtConcurrent/QtConcurrentRun>

namespace XetalProton {
using namespace Ui;
void Page::buildLibrary() {
    auto *page=new QWidget;auto *layout=new QVBoxLayout(page);
    auto *actions=new QHBoxLayout;
    button("Add shortcut…","protonAddShortcut",actions,[this]{addShortcut();});
    button("Run once…","protonRunOnce",actions,[this]{addShortcut(true);});
    button("Open C:\\","protonDriveC",actions,[this]{openFolder(text(model.current)+"/pfx/drive_c");});
    button("Initialize / update prefix","protonInit",actions,[this]{model.runTool("wineboot","-u");});
    button("Task Manager","protonTaskManager",actions,[this]{model.runTaskManager(selectedShortcut);});
    auto *helpers=new QPushButton("Prefix tools");helpers->setObjectName("protonHelpers");auto *menu=new QMenu(helpers);
    for(const auto &entry:std::vector<std::pair<QString,std::string>>{{"Wine configuration","winecfg"},{"Registry Editor","regedit"},{"Windows Control Panel","control"},{"Task Manager","taskmgr"},{"Explorer","explorer"},{"Command prompt","cmd"}})
        connect(menu->addAction(entry.first),&QAction::triggered,this,[this,entry]{model.runTool(entry.second);});
    menu->addSeparator();connect(menu->addAction("Open prefix folder"),&QAction::triggered,this,[this]{openFolder(text(model.current));});
    connect(menu->addAction("Stop all programs in this prefix"),&QAction::triggered,this,[this]{if(confirm("Stop prefix","Stop all Windows programs in the selected prefix?"))model.runTool("wineboot","-k");});
    connect(menu->addAction("Force stop this prefix's wineserver"),&QAction::triggered,this,[this]{if(confirm("Force stop prefix","Unsaved Windows data may be lost. Force stop this prefix?"))model.forceStopPrefix();});
    helpers->setMenu(menu);actions->addWidget(helpers);actions->addStretch();layout->addLayout(actions);
    auto *split=new QSplitter;shortcuts=new QListWidget;shortcuts->setObjectName("protonShortcuts");
    shortcuts->setViewMode(QListView::IconMode);shortcuts->setResizeMode(QListView::Adjust);shortcuts->setMovement(QListView::Static);
    shortcuts->setWordWrap(true);shortcuts->setSpacing(12);shortcuts->setSelectionMode(QAbstractItemView::SingleSelection);
    shortcuts->setAcceptDrops(false);shortcuts->viewport()->setAcceptDrops(false);split->addWidget(shortcuts);
    auto *detail=new QWidget;auto *right=new QVBoxLayout(detail);shortcutInfo=hint("Add an installer or Windows program to this prefix. Double-click a shortcut to launch it.",right);
    shortcutInfo->setSizePolicy(QSizePolicy::Preferred,QSizePolicy::Minimum);
    auto *launchRow=new QHBoxLayout;
    button("Launch","protonLaunch",launchRow,[this]{model.launchShortcut(selectedShortcut);});
    button("Edit…","protonEditShortcut",launchRow,[this]{editShortcut();});
    button("Duplicate","protonDuplicate",launchRow,[this]{model.duplicateShortcut(selectedShortcut);});right->addLayout(launchRow);
    auto *more=new QHBoxLayout;
    button("Export .sh…","protonExport",more,[this]{exportShortcut();});
    button("Open app folder","protonAppFolder",more,[this]{if(const auto *s=model.shortcut(selectedShortcut))openFolder(text(util::dirname(s->exe)));});
    button("Remove shortcut","protonRemoveShortcut",more,[this]{if(model.shortcut(selectedShortcut) && confirm("Remove shortcut","Remove this shortcut from the library? The Windows application and its files will remain."))model.removeShortcut(selectedShortcut);});right->addLayout(more);
    auto *integration=new QHBoxLayout;
    button("Browser sign-in…","protonBrowserSignIn",integration,[this]{editShortcut(true);});
    button("Repair link handlers","protonRepairHandlers",integration,[this]{if(model.syncDesktopHandlers())model.report("Browser sign-in handlers refreshed.");});
    integration->addStretch();right->addLayout(integration);
    right->addWidget(new QLabel("Launch command"));commandPreview=new QPlainTextEdit;commandPreview->setObjectName("protonCommand");commandPreview->setReadOnly(true);right->addWidget(commandPreview,1);
    auto *copyRow=new QHBoxLayout;button("Copy command","protonCopyCommand",copyRow,[this]{QApplication::clipboard()->setText(commandPreview->toPlainText());});copyRow->addStretch();right->addLayout(copyRow);
    split->addWidget(detail);split->setStretchFactor(0,1);split->setStretchFactor(1,1);layout->addWidget(split,1);
    connect(shortcuts,&QListWidget::itemSelectionChanged,this,&Page::selectShortcut);
    connect(shortcuts,&QListWidget::itemDoubleClicked,this,[this]{model.launchShortcut(selectedShortcut);});
    shortcuts->setContextMenuPolicy(Qt::CustomContextMenu);connect(shortcuts,&QWidget::customContextMenuRequested,this,[this](QPoint point){
        auto *item=shortcuts->itemAt(point);if(!item)return;shortcuts->setCurrentItem(item);
        QMenu menu;auto *run=menu.addAction("Launch"),*edit=menu.addAction("Edit…"),*login=menu.addAction("Browser sign-in…"),*taskManager=menu.addAction("Task Manager in this prefix");menu.addSeparator();
        auto *duplicate=menu.addAction("Duplicate"),*folder=menu.addAction("Open app folder"),*exporter=menu.addAction("Export .sh…"),*remove=menu.addAction("Remove shortcut");
        const auto *action=menu.exec(shortcuts->viewport()->mapToGlobal(point));
        if(action==run)model.launchShortcut(selectedShortcut);else if(action==edit)editShortcut();else if(action==duplicate)model.duplicateShortcut(selectedShortcut);
        else if(action==login)editShortcut(true);else if(action==taskManager)model.runTaskManager(selectedShortcut);
        else if(action==folder){if(const auto *s=model.shortcut(selectedShortcut))openFolder(text(util::dirname(s->exe)));}
        else if(action==exporter)exportShortcut();else if(action==remove && confirm("Remove shortcut","Remove this shortcut while keeping the Windows application?"))model.removeShortcut(selectedShortcut);
    });
    tabs->addTab(page,"Library");
}
QIcon Page::shortcutIcon(const Shortcut &s) {
    const auto path=text(s.icon_override.empty()?s.exe:s.icon_override);
    const QFileInfo file(path);const auto key=path+":"+QString::number(file.lastModified().toMSecsSinceEpoch());
    if(iconCache.contains(key))return iconCache[key];
    const auto icon=QIcon::fromTheme("application-x-executable",style()->standardIcon(QStyle::SP_ComputerIcon));iconCache.insert(key,icon);
    auto *watcher=new QFutureWatcher<QImage>(this);
    connect(watcher,&QFutureWatcher<QImage>::finished,this,[this,watcher,key]{
        const auto image=watcher->result();watcher->deleteLater();if(image.isNull())return;
        const QIcon icon(QPixmap::fromImage(image));iconCache[key]=icon;
        for(int i=0;i<shortcuts->count();++i) {
            auto *item=shortcuts->item(i);const auto *shortcut=model.shortcut(item->data(Qt::UserRole).toString().toStdString());
            if(shortcut)item->setIcon(shortcutIcon(*shortcut));
        }
    });
    watcher->setFuture(QtConcurrent::run([path]{
        IconImage result;
        if(!load_icon_for_exe(path.toStdString(),result) || !result.valid())return QImage();
        shrink_icon(result,128);return QImage(result.rgba.data(),result.w,result.h,QImage::Format_RGBA8888).copy();
    }));
    return icon;
}
void Page::refreshLibrary() {
    const QSignalBlocker block(shortcuts);shortcuts->clear();
    const int size=std::clamp(model.config.icon_size,32,128);shortcuts->setIconSize({size,size});shortcuts->setGridSize({size+70,size+65});
    for(const auto &s:model.config.shortcuts)if(s.prefix==model.current){
        auto *item=new QListWidgetItem(shortcutIcon(s),text(s.name),shortcuts);item->setData(Qt::UserRole,text(s.id));item->setToolTip(text(s.exe));
        if(s.id==selectedShortcut)shortcuts->setCurrentItem(item);
    }
    if(!shortcuts->currentItem() && shortcuts->count())shortcuts->setCurrentRow(0);
    selectShortcut();
}
void Page::selectShortcut() {
    selectedShortcut=shortcuts->currentItem()?shortcuts->currentItem()->data(Qt::UserRole).toString().toStdString():"";
    const auto *s=model.shortcut(selectedShortcut);
    if(!s){shortcutInfo->setText(model.current.empty()?"Create or import a prefix, then add your Windows programs.":"Add a Windows program or installer to this prefix.");commandPreview->clear();}
    else {shortcutInfo->setText(text(s->name)+"\n"+text(s->exe)+(s->desktop.enabled?"\nBrowser sign-in: "+Desktop::schemes(s->desktop.schemes).join(", "):QString()));commandPreview->setPlainText(text(spec_to_shell(Desktop::managedLaunch(model.command(*s),*s))));}
    for(const auto *name:{"protonLaunch","protonEditShortcut","protonDuplicate","protonExport","protonAppFolder","protonRemoveShortcut","protonCopyCommand","protonBrowserSignIn"})findChild<QPushButton *>(name)->setEnabled(s!=nullptr);
    findChild<QPushButton *>("protonRepairHandlers")->setEnabled((s && s->desktop.enabled) || QFileInfo::exists(Desktop::storage()+"/registry.json"));
    findChild<QPushButton *>("protonTaskManager")->setEnabled(!model.current.empty());
}
void Page::addShortcut(bool once) {
    if(model.current.empty()){model.report("Create or select a prefix first.");return;}
    const auto drive=text(model.current)+"/pfx/drive_c";
    const auto file=QFileDialog::getOpenFileName(this,once?"Run Windows program once":"Add Windows shortcut",QFileInfo(drive).isDir()?drive:QDir::homePath(),"Windows programs (*.exe *.msi *.bat *.cmd);;All files (*)");
    if(file.isEmpty())return;
    if(once){Shortcut s;s.prefix=model.current;s.exe=file.toStdString();s.name=QFileInfo(file).completeBaseName().toStdString();model.launch(model.command(s));}
    else model.addShortcut(file,launchAdded->isChecked());
}
void Page::exportShortcut() {
    const auto *s=model.shortcut(selectedShortcut);if(!s)return;
    const auto file=QFileDialog::getSaveFileName(this,"Export launch script",QDir::homePath()+"/"+text(util::sanitize_filename(s->name))+".sh","Shell script (*.sh)");
    if(!file.isEmpty())model.exportScript(selectedShortcut,file);
}
void Page::managePrefix() {
    if(model.current.empty())return;
    QDialog dialog(this);dialog.setWindowTitle("Manage Windows prefix");auto *layout=new QVBoxLayout(&dialog);
    const auto selected=model.current;auto found=std::find_if(model.prefixes.begin(),model.prefixes.end(),[&](const auto &p){return p.path==selected;});
    if(found==model.prefixes.end())return;
    auto *name=new QLineEdit(text(found->name));name->setObjectName("protonPrefixName");layout->addWidget(name);name->setEnabled(found->custom);
    hint(text(selected),layout);auto *usage=hint("Disk usage has not been measured.",layout);auto *row=new QHBoxLayout;
    auto *measure=button("Measure disk usage","protonMeasurePrefix",row,[&dialog,usage,selected]{
        auto *process=new QProcess(&dialog);QObject::connect(process,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),usage,[process,usage](int code,QProcess::ExitStatus){
            const auto number=process->readAllStandardOutput().split('\t').value(0).toULongLong();usage->setText(code==0?"Disk usage: "+text(util::human_size(number)):"Could not measure this folder.");process->deleteLater();});
        process->start("du",{"-sb","--",text(selected)});
    });Q_UNUSED(measure);button("Open folder","protonManageOpen",row,[selected]{openFolder(text(selected));});row->addStretch();layout->addLayout(row);
    auto *removeFiles=new QCheckBox("Also permanently delete this prefix's Windows files");removeFiles->setObjectName("protonDeletePrefixFiles");layout->addWidget(removeFiles);removeFiles->setEnabled(found->custom);
    hint("Removing a prefix from this list also removes its shortcuts. By default, its Windows files stay on disk.",layout);
    auto *buttons=new QDialogButtonBox(QDialogButtonBox::Save|QDialogButtonBox::Cancel);layout->addWidget(buttons);
    auto *remove=buttons->addButton("Remove prefix…",QDialogButtonBox::DestructiveRole);remove->setEnabled(found->custom);
    connect(buttons,&QDialogButtonBox::accepted,&dialog,[this,name,&dialog]{if(model.renamePrefix(name->text()))dialog.accept();});connect(buttons,&QDialogButtonBox::rejected,&dialog,&QDialog::reject);
    connect(remove,&QPushButton::clicked,&dialog,[this,removeFiles,&dialog]{if(confirm("Remove prefix",removeFiles->isChecked()?"Permanently delete this prefix and its installed Windows applications?":"Remove this prefix and its shortcuts from the list, keeping Windows files on disk?") && model.removePrefix(removeFiles->isChecked()))dialog.accept();});
    dialog.exec();
}
void Page::editShortcut(bool browserSignIn) {
    const auto *original=model.shortcut(selectedShortcut);if(!original)return;Shortcut draft=*original;
    QDialog dialog(this);dialog.setWindowTitle("Edit Proton shortcut");dialog.setObjectName("protonShortcutEditor");dialog.resize(900,720);
    auto *layout=new QVBoxLayout(&dialog);auto *pages=new QTabWidget;layout->addWidget(pages,1);
    auto *general=new QWidget;auto *form=new QFormLayout(general);pages->addTab(general,"Program");
    auto field=[&](const QString &label,const QString &name,const std::string &value,bool browse=false,bool directory=false){
        auto *edit=new QLineEdit(text(value));edit->setObjectName(name);
        if(!browse)form->addRow(label,edit);else {auto *container=new QWidget;auto *row=new QHBoxLayout(container);row->setContentsMargins(0,0,0,0);row->addWidget(edit,1);
            button("Browse…",name+"Browse",row,[this,edit,directory]{const auto chosen=directory?QFileDialog::getExistingDirectory(this,"Choose folder",edit->text()):QFileDialog::getOpenFileName(this,"Choose file",edit->text());if(!chosen.isEmpty())edit->setText(chosen);});form->addRow(label,container);}
        return edit;
    };
    auto *name=field("Name:","protonShortcutName",draft.name),*exe=field("Executable:","protonShortcutExe",draft.exe,true),*args=field("Arguments:","protonShortcutArgs",draft.args),*workdir=field("Working folder:","protonShortcutWorkdir",draft.workdir,true,true),*icon=field("Icon override:","protonShortcutIcon",draft.icon_override,true);
    auto *prefix=new QComboBox;prefix->setObjectName("protonShortcutPrefix");for(const auto &p:model.prefixes)prefix->addItem(text(p.name),text(p.path));prefix->setCurrentIndex(prefix->findData(text(draft.prefix)));form->addRow("Prefix:",prefix);
    auto *runner=new QComboBox;runner->setObjectName("protonShortcutVersion");runner->addItem("Use prefix default","");for(const auto &p:model.discovery.protons)runner->addItem(text(p.name),text(p.dir));
    int runnerIndex=runner->findData(text(draft.proton));if(runnerIndex<0){runner->addItem("Unavailable: "+text(draft.proton),text(draft.proton));runnerIndex=runner->count()-1;}runner->setCurrentIndex(runnerIndex);form->addRow("Proton override:",runner);
    auto *verb=new QComboBox;verb->setObjectName("protonVerb");verb->addItems({"run","waitforexitandrun","runinprefix"});verb->setCurrentText(text(draft.verb));form->addRow("Launch verb:",verb);
    auto *runtime=new QCheckBox("Use the managed UMU runtime");runtime->setObjectName("protonUseRuntime");runtime->setChecked(draft.use_runtime);form->addRow(runtime);
    auto *explain=new QLabel("run allows related applications in the same prefix. waitforexitandrun waits for existing prefix programs to finish. runinprefix runs a Wine helper.");explain->setWordWrap(true);form->addRow(explain);
    auto *integration=new QWidget;auto *integrationLayout=new QVBoxLayout(integration);pages->addTab(integration,"Browser sign-in");
    hint("Let your Linux browser return sign-in links to this Windows app. Use the installed application's executable and start sign-in from that app.",integrationLayout);
    auto *receive=new QCheckBox("Receive browser sign-in links for this app");receive->setObjectName("protonHandleUrls");receive->setChecked(draft.desktop.enabled);integrationLayout->addWidget(receive);
    auto *integrationFields=new QWidget;auto *integrationForm=new QFormLayout(integrationFields);integrationForm->setContentsMargins(0,0,0,0);integrationLayout->addWidget(integrationFields);
    auto *schemes=new QLineEdit(text(draft.desktop.schemes));schemes->setObjectName("protonUrlSchemes");schemes->setPlaceholderText("grasshopper, another-app");integrationForm->addRow("URL schemes:",schemes);
    schemes->setToolTip("Names before ://, separated by commas or spaces. For grasshopper:// links, enter grasshopper.");
    auto *argument=new QLineEdit(text(draft.desktop.argument));argument->setObjectName("protonUrlArgument");integrationForm->addRow("URL argument:",argument);
    argument->setToolTip("One argument containing {url}. Usually {url}; some apps need --url={url}. The link is passed intact.");
    auto *includeArgs=new QCheckBox("Include the app's normal launch arguments");includeArgs->setObjectName("protonUrlIncludeArgs");includeArgs->setChecked(draft.desktop.include_args);integrationForm->addRow(includeArgs);
    auto *makeDefault=new QCheckBox("Keep this app as the default for these links in Hyprland");makeDefault->setObjectName("protonUrlDefault");makeDefault->setChecked(draft.desktop.make_default);integrationForm->addRow(makeDefault);
    auto *privateOutput=new QCheckBox("Hide app output and Proton debug logs during sign-in");privateOutput->setObjectName("protonUrlPrivateOutput");privateOutput->setChecked(draft.desktop.private_output);integrationForm->addRow(privateOutput);
    privateOutput->setToolTip("Recommended: some apps print sign-in tokens. Callback launches always hide their output; this option also hides the original app's output.");
    integrationFields->setEnabled(receive->isChecked());connect(receive,&QCheckBox::toggled,integrationFields,&QWidget::setEnabled);
    hint("Save installs the link handlers. Callbacks use the same prefix and runner as the app's latest launch. Disabling this option removes its handlers and restores defaults that are still owned by this shortcut.",integrationLayout);
    hint("Changes apply to future launches. An already-open app may still be writing its existing log. Export .sh includes this sign-in setup.",integrationLayout);
    integrationLayout->addStretch();if(browserSignIn)pages->setCurrentWidget(integration);
    std::map<std::string,QWidget *> options;
    for(const auto &group:OPTION_GROUPS) {
        auto *scroll=new QScrollArea;scroll->setWidgetResizable(true);auto *content=new QWidget;auto *fields=new QFormLayout(content);fields->setFieldGrowthPolicy(QFormLayout::ExpandingFieldsGrow);scroll->setWidget(content);pages->addTab(scroll,group.name);
        for(const auto &option:group.opts) {
            QWidget *widget=nullptr;const auto value=draft.env[option.key];
            if(option.kind==OptKind::Bool){auto *check=new QCheckBox(option.label);check->setChecked(value=="1");widget=check;fields->addRow(check);}
            else if(option.kind==OptKind::Choice){auto *choice=new QComboBox;choice->setEditable(true);choice->addItem("Default","");for(const auto *item:option.choices)choice->addItem(item,item);if(!value.empty())choice->setCurrentText(text(value));widget=choice;fields->addRow(option.label,choice);}
            else {auto *edit=new QLineEdit(text(value));widget=edit;fields->addRow(option.label,edit);}
            widget->setObjectName(QString("protonOption_")+option.key);widget->setToolTip(option.tip);options[option.key]=widget;
        }
    }
    auto *advanced=new QWidget;auto *advancedForm=new QFormLayout(advanced);pages->addTab(advanced,"Environment");
    auto *wrapper=new QLineEdit(text(draft.env["@wrapper"]));wrapper->setObjectName("protonWrapper");advancedForm->addRow("Wrapper command:",wrapper);
    auto *environment=new QPlainTextEdit(text(draft.custom_env));environment->setObjectName("protonCustomEnv");environment->setPlaceholderText("KEY=VALUE, one per line");advancedForm->addRow("Extra environment:",environment);
    auto *buttons=new QDialogButtonBox(QDialogButtonBox::Save|QDialogButtonBox::Cancel);layout->addWidget(buttons);
    connect(buttons,&QDialogButtonBox::rejected,&dialog,&QDialog::reject);
    connect(buttons,&QDialogButtonBox::accepted,&dialog,[&,this]{
        draft.name=name->text().trimmed().toStdString();draft.exe=exe->text().toStdString();draft.args=args->text().toStdString();draft.workdir=workdir->text().toStdString();draft.icon_override=icon->text().toStdString();
        draft.prefix=prefix->currentData().toString().toStdString();draft.proton=runner->currentData().toString().toStdString();draft.verb=verb->currentText().toStdString();draft.use_runtime=runtime->isChecked();
        draft.desktop.enabled=receive->isChecked();draft.desktop.schemes=schemes->text().trimmed().toStdString();draft.desktop.argument=argument->text().toStdString();
        draft.desktop.include_args=includeArgs->isChecked();draft.desktop.make_default=makeDefault->isChecked();draft.desktop.private_output=privateOutput->isChecked();
        for(const auto &[key,widget]:options) {
            std::string value;
            if(auto *check=qobject_cast<QCheckBox *>(widget))value=check->isChecked()?"1":"";
            else if(auto *choice=qobject_cast<QComboBox *>(widget))value=(choice->currentIndex()==0 && choice->currentText()=="Default")?"":choice->currentText().toStdString();
            else value=qobject_cast<QLineEdit *>(widget)->text().toStdString();
            if(value.empty())draft.env.erase(key);else draft.env[key]=value;
        }
        draft.env["@wrapper"]=wrapper->text().toStdString();draft.custom_env=environment->toPlainText().toStdString();
        if(model.updateShortcut(draft))dialog.accept();else QMessageBox::warning(&dialog,"Shortcut not saved",model.notice);
    });
    dialog.exec();
}
}
