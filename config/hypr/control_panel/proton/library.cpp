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
    auto *page=new QWidget;page->setObjectName("protonLibrary");auto *layout=new QVBoxLayout(page);layout->setContentsMargins(14,16,14,12);layout->setSpacing(14);
    page->setStyleSheet(R"(
        QListWidget#protonShortcuts { background: transparent; border: none; outline: none; padding: 4px; }
        QListWidget#protonShortcuts::item { padding: 8px; border: 1px solid transparent; border-radius: 12px; }
        QListWidget#protonShortcuts::item:hover:!selected { background: palette(alternate-base); border-color: palette(mid); }
        QListWidget#protonShortcuts::item:selected { background: palette(highlight); color: palette(highlighted-text); border-color: palette(highlight); }
        QFrame#protonAppCard { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 16px; }
        QFrame#protonAppCard QLabel { background: transparent; border: none; }
        QLabel#protonAppName { font-size: 22px; font-weight: 600; }
        QLabel#protonEmptyTitle { font-size: 20px; font-weight: 600; }
        QLabel#protonAppEyebrow { font-size: 10px; letter-spacing: 1px; }
        QPushButton#protonLaunch { background: palette(highlight); color: palette(highlighted-text); border: none; border-radius: 9px; padding: 10px; font-weight: bold; }
        QPushButton#protonLaunch:disabled { background: palette(button); color: palette(mid); }
        QPushButton#protonLaunch[launchPending="true"]:disabled { background: palette(highlight); color: palette(highlighted-text); }
        QLineEdit#protonLibrarySearch { padding: 8px 10px; border-radius: 8px; }
    )");
    auto *toolbar=new QHBoxLayout;toolbar->setSpacing(10);
    librarySearch=new QLineEdit;librarySearch->setObjectName("protonLibrarySearch");librarySearch->setPlaceholderText("Search your apps…");
    librarySearch->setClearButtonEnabled(true);librarySearch->setAccessibleName("Search your Windows apps");
    librarySearch->addAction(icon("edit-find",QStyle::SP_FileDialogContentsView),QLineEdit::LeadingPosition);toolbar->addWidget(librarySearch,1);
    auto *add=button("Add app","protonAddShortcut",toolbar,[this]{addShortcut();});decorate(add,"list-add","Add a Windows app or installer to this environment");
    auto *tasks=button("Task Manager","protonTaskManager",toolbar,[this]{model.runTaskManager(selectedShortcut);});
    decorate(tasks,"utilities-system-monitor","Task Manager — view programs in this app's Windows environment",true);layout->addLayout(toolbar);
    auto *split=new QSplitter;split->setObjectName("protonLibrarySplit");split->setChildrenCollapsible(false);split->setHandleWidth(12);
    auto *gallery=new QWidget;gallery->setMinimumWidth(220);auto *left=new QVBoxLayout(gallery);left->setContentsMargins(0,0,0,0);left->setSpacing(8);
    libraryCount=hint("Your applications",left);libraryCount->setObjectName("protonLibraryCount");
    libraryStack=new QStackedWidget;left->addWidget(libraryStack,1);
    shortcuts=new QListWidget;shortcuts->setObjectName("protonShortcuts");
    shortcuts->setViewMode(QListView::IconMode);shortcuts->setResizeMode(QListView::Adjust);shortcuts->setMovement(QListView::Static);
    shortcuts->setWordWrap(true);shortcuts->setTextElideMode(Qt::ElideRight);shortcuts->setSpacing(8);shortcuts->setSelectionMode(QAbstractItemView::SingleSelection);
    shortcuts->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);shortcuts->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    shortcuts->setAcceptDrops(false);shortcuts->viewport()->setAcceptDrops(false);libraryStack->addWidget(shortcuts);
    auto *empty=new QWidget;auto *emptyLayout=new QVBoxLayout(empty);emptyLayout->addStretch();
    auto *emptyIcon=new QLabel;emptyIcon->setPixmap(icon("application-x-executable",QStyle::SP_ComputerIcon).pixmap(64,64));emptyIcon->setAlignment(Qt::AlignCenter);emptyLayout->addWidget(emptyIcon);
    emptyTitle=new QLabel;emptyTitle->setObjectName("protonEmptyTitle");emptyTitle->setAlignment(Qt::AlignCenter);emptyTitle->setWordWrap(true);
    auto heading=emptyTitle->font();heading.setPointSize(17);heading.setBold(true);emptyTitle->setFont(heading);emptyLayout->addWidget(emptyTitle);
    emptyDescription=hint({},emptyLayout);emptyDescription->setAlignment(Qt::AlignCenter);
    auto *emptyRow=new QHBoxLayout;emptyRow->addStretch();emptyAction=button("Add app","protonEmptyAction",emptyRow,[this]{
        if(!librarySearch->text().isEmpty())librarySearch->clear();else if(model.current.empty())tabs->setCurrentIndex(4);else addShortcut();
    });emptyRow->addStretch();emptyLayout->addLayout(emptyRow);emptyLayout->addStretch();libraryStack->addWidget(empty);
    split->addWidget(gallery);
    auto *sidebar=new QWidget;sidebar->setMinimumWidth(260);sidebar->setMaximumWidth(340);auto *sideLayout=new QVBoxLayout(sidebar);sideLayout->setContentsMargins(0,0,0,0);
    auto *card=new QFrame;card->setObjectName("protonAppCard");auto *right=new QVBoxLayout(card);right->setContentsMargins(22,24,22,22);right->setSpacing(14);
    auto *eyebrow=hint("SELECTED APP",right);eyebrow->setObjectName("protonAppEyebrow");eyebrow->setAlignment(Qt::AlignCenter);
    shortcutArtwork=new QLabel;shortcutArtwork->setObjectName("protonAppArtwork");shortcutArtwork->setAlignment(Qt::AlignCenter);shortcutArtwork->setMinimumHeight(104);right->addWidget(shortcutArtwork);
    shortcutTitle=new QLabel;shortcutTitle->setObjectName("protonAppName");shortcutTitle->setTextFormat(Qt::PlainText);shortcutTitle->setAlignment(Qt::AlignCenter);shortcutTitle->setWordWrap(true);
    auto appFont=shortcutTitle->font();appFont.setPointSize(20);appFont.setBold(true);shortcutTitle->setFont(appFont);right->addWidget(shortcutTitle);
    shortcutInfo=hint({},right);shortcutInfo->setAlignment(Qt::AlignCenter);shortcutInfo->setSizePolicy(QSizePolicy::Preferred,QSizePolicy::Minimum);
    right->addSpacing(6);
    auto *launch=button("Launch","protonLaunch",right,[this]{launchApp(selectedShortcut);});decorate(launch,"media-playback-start");launch->setMinimumHeight(46);
    auto *edit=button("App settings","protonEditShortcut",right,[this]{editShortcut();});decorate(edit,"preferences-system","App settings — launch options, compatibility and browser sign-in");
    auto *moreRow=new QHBoxLayout;
    auto *folder=button("App folder","protonAppFolder",moreRow,[this]{if(const auto *s=model.shortcut(selectedShortcut))openFolder(text(util::dirname(s->exe)));});decorate(folder,"folder-open","Open this app's folder",true);
    auto *more=button("More","protonAppMore",moreRow,[]{});decorate(more,"view-more-symbolic","More actions for this app");moreRow->setStretch(1,1);right->addLayout(moreRow);
    sideLayout->addWidget(card);sideLayout->addStretch();split->addWidget(sidebar);split->setStretchFactor(0,1);split->setStretchFactor(1,0);split->setSizes({820,300});layout->addWidget(split,1);
    appMenu=new QMenu(this);appMenu->setObjectName("protonAppMenu");more->setMenu(appMenu);
    auto action=[this](const QString &title,const QString &name,const QString &iconName,std::function<void()> callback){
        auto *result=appMenu->addAction(icon(iconName),title);result->setObjectName(name);connect(result,&QAction::triggered,this,std::move(callback));return result;
    };
    action("Launch","protonMenuLaunch","media-playback-start",[this]{launchApp(selectedShortcut);});
    action("App settings…","protonMenuEdit","preferences-system",[this]{editShortcut();});
    action("Browser sign-in…","protonBrowserSignIn","internet-web-browser",[this]{editShortcut(true);});
    action("Task Manager in this environment","protonMenuTaskManager","utilities-system-monitor",[this]{model.runTaskManager(selectedShortcut);});
    appMenu->addSeparator();
    action("Export launcher…","protonExport","document-save-as",[this]{exportShortcut();});
    action("Duplicate","protonDuplicate","edit-copy",[this]{model.duplicateShortcut(selectedShortcut);});
    action("Launch command…","protonShowCommand","utilities-terminal",[this]{showCommand();});
    action("Repair browser sign-in","protonRepairHandlers","view-refresh",[this]{if(model.syncDesktopHandlers())model.report("Browser sign-in handlers refreshed.");});
    appMenu->addSeparator();
    action("Remove from library…","protonRemoveShortcut","edit-delete",[this]{if(model.shortcut(selectedShortcut) && confirm("Remove shortcut","Remove this shortcut from the library? The Windows application and its files will remain."))model.removeShortcut(selectedShortcut);});
    connect(librarySearch,&QLineEdit::textChanged,this,&Page::filterLibrary);
    connect(shortcuts,&QListWidget::itemSelectionChanged,this,&Page::selectShortcut);
    connect(shortcuts,&QListWidget::itemDoubleClicked,this,[this](QListWidgetItem *item){launchApp(item->data(Qt::UserRole).toString().toStdString());});
    shortcuts->setContextMenuPolicy(Qt::CustomContextMenu);connect(shortcuts,&QWidget::customContextMenuRequested,this,[this](QPoint point){
        auto *item=shortcuts->itemAt(point);if(!item)return;shortcuts->setCurrentItem(item);appMenu->exec(shortcuts->viewport()->mapToGlobal(point));
    });
    for(const auto key:{Qt::Key_Return,Qt::Key_Enter}){
        auto *launchKey=new QShortcut(QKeySequence(key),shortcuts);launchKey->setContext(Qt::WidgetShortcut);
        connect(launchKey,&QShortcut::activated,this,[this]{launchApp(selectedShortcut);});
    }
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
        if(const auto *selected=model.shortcut(selectedShortcut))shortcutArtwork->setPixmap(shortcutIcon(*selected).pixmap(96,96));
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
    const int size=std::clamp(model.config.icon_size,32,128);shortcuts->setIconSize({size,size});shortcuts->setGridSize({size+92,size+86});
    for(const auto &s:model.config.shortcuts)if(s.prefix==model.current){
        auto *item=new QListWidgetItem(shortcutIcon(s),text(s.name),shortcuts);item->setData(Qt::UserRole,text(s.id));item->setToolTip(text(s.name)+"\n"+text(s.exe));
        if(s.id==selectedShortcut)shortcuts->setCurrentItem(item);
    }
    filterLibrary();
}
void Page::filterLibrary() {
    const QSignalBlocker block(shortcuts);const auto query=librarySearch->text().trimmed();QListWidgetItem *first=nullptr;int visible=0;
    for(int i=0;i<shortcuts->count();++i){
        auto *item=shortcuts->item(i);const bool matches=item->text().contains(query,Qt::CaseInsensitive);item->setHidden(!matches);
        if(matches){++visible;if(!first)first=item;}
    }
    if(!shortcuts->currentItem() || shortcuts->currentItem()->isHidden())shortcuts->setCurrentItem(first);
    libraryCount->setText(query.isEmpty()?QString::number(visible)+(visible==1?" application":" applications"):
                          QString::number(visible)+" of "+QString::number(shortcuts->count())+" applications");
    libraryStack->setCurrentIndex(visible?0:1);
    const bool searching=!query.isEmpty();
    emptyTitle->setText(searching?"No matching apps":model.current.empty()?"Make room for your Windows apps":"Add your first app");
    emptyDescription->setText(searching?"Try another name or clear your search.":model.current.empty()?
        "Create an environment in Settings, then add your apps here.":"Add a Windows app or installer, or drop its file into this window.");
    emptyAction->setText(searching?"Clear search":model.current.empty()?"Set up an environment":"Add app");
    selectShortcut();
}
void Page::selectShortcut() {
    selectedShortcut=shortcuts->currentItem()?shortcuts->currentItem()->data(Qt::UserRole).toString().toStdString():"";
    const auto *s=model.shortcut(selectedShortcut);
    shortcutTitle->setText(s?text(s->name):"Choose an app");
    shortcutArtwork->setPixmap((s?shortcutIcon(*s):icon("application-x-executable",QStyle::SP_ComputerIcon)).pixmap(96,96));
    shortcutInfo->setText(s?(prefixChoice->currentText()+(s->desktop.enabled?"\nBrowser sign-in enabled":"")):"Select an app from your library to launch it or change its settings.");
    shortcutTitle->setToolTip(s?text(s->exe):QString());
    for(const auto *name:{"protonLaunch","protonEditShortcut","protonAppFolder","protonAppMore"})findChild<QPushButton *>(name)->setEnabled(s!=nullptr);
    for(auto *action:appMenu->actions())if(!action->isSeparator())action->setEnabled(s!=nullptr);
    const auto feedback=launchFeedback.find(selectedShortcut);const bool pending=feedback!=launchFeedback.end();
    auto *launch=findChild<QPushButton *>("protonLaunch");
    launch->setEnabled(s && !pending);findChild<QAction *>("protonMenuLaunch")->setEnabled(s && !pending);
    launch->setText(pending?(feedback->second?"Launch sent":"Launching…"):"Launch");
    launch->setAccessibleName(launch->text());
    launch->setIcon(icon(pending?(feedback->second?"dialog-ok-apply":"view-refresh"):"media-playback-start"));
    if(launch->property("launchPending").toBool()!=pending){
        launch->setProperty("launchPending",pending);launch->style()->unpolish(launch);launch->style()->polish(launch);launch->update();
    }
    findChild<QAction *>("protonRepairHandlers")->setEnabled((s && s->desktop.enabled) || QFileInfo::exists(Desktop::storage()+"/registry.json"));
    findChild<QPushButton *>("protonTaskManager")->setEnabled(!model.current.empty());
    findChild<QPushButton *>("protonAddShortcut")->setEnabled(!model.current.empty());
}
void Page::launchApp(std::string id) {
    if(!model.shortcut(id) || launchFeedback.count(id))return;
    launchFeedback[id]=false;selectShortcut();
    // Give the compositor a frame to show the acknowledgement before launch
    // setup (including browser-handler registration) can briefly block.
    QTimer::singleShot(40,this,[this,id]{
        if(model.launchShortcut(id)<=0){launchFeedback.erase(id);selectShortcut();return;}
        launchFeedback[id]=true;selectShortcut();
        // This acknowledges the request, not whether the Windows app is ready.
        QTimer::singleShot(1400,this,[this,id]{launchFeedback.erase(id);selectShortcut();});
    });
}
void Page::showCommand() {
    const auto *s=model.shortcut(selectedShortcut);if(!s)return;
    QDialog dialog(this);dialog.setObjectName("protonCommandDialog");dialog.setWindowTitle("Launch command · "+text(s->name));dialog.resize(780,560);
    auto *layout=new QVBoxLayout(&dialog);hint("The command used to launch this app, including its environment and saved options.",layout);
    auto *command=new QPlainTextEdit(text(spec_to_shell(Desktop::managedLaunch(model.command(*s),*s))));command->setObjectName("protonCommand");command->setReadOnly(true);layout->addWidget(command,1);
    auto *row=new QHBoxLayout;auto *copy=button("Copy command","protonCopyCommand",row,[command]{QApplication::clipboard()->setText(command->toPlainText());});decorate(copy,"edit-copy");row->addStretch();
    button("Close","protonCloseCommand",row,[&dialog]{dialog.accept();});layout->addLayout(row);dialog.exec();
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
    auto *schemes=new QLineEdit(text(draft.desktop.schemes));schemes->setObjectName("protonUrlSchemes");schemes->setPlaceholderText("example-app, another-app");integrationForm->addRow("URL schemes:",schemes);
    schemes->setToolTip("Names before ://, separated by commas or spaces. For example-app:// links, enter example-app.");
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
