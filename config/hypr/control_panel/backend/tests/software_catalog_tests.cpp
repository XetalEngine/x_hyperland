#include "software_catalog.h"
#include "software_actions.h"
#include "software_page.h"
#include <QtTest>
#include <QtWidgets>

namespace {
bool write(const QString &path,const QByteArray &data,bool executable=false) {
    QFile f(path);if(!f.open(QIODevice::WriteOnly))return false;f.write(data);f.close();
    return !executable||f.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner);
}
QByteArray read(const QString &path){QFile f(path);return f.open(QIODevice::ReadOnly)?f.readAll():QByteArray();}
QString sourceRoot(){return QDir(QFileInfo(__FILE__).absolutePath()).absoluteFilePath("../../..");}
QTreeWidgetItem *category(QTreeWidget *tree,const QString &id) {for(QTreeWidgetItemIterator i(tree);*i;++i)if((*i)->data(0,Qt::UserRole).toString()==id)return *i;return nullptr;}
QJsonObject app(const QString &package,const QString &tag="Utility",const QString &source="pacman") {
    return {{"id",source+'/'+package},{"package",package},{"name",package},{"summary","An app for your desktop"},{"source",source},{"repository",source=="pacman"?"extra":"AUR"},{"categories",QJsonArray{tag}},{"available",true},{"essential",true}};
}
template<class T>T *widget(QWidget *parent,const char *name){auto *w=new T(parent);w->setObjectName(name);return w;}
class SoftwareFrame:public QWidget {
public:
    SoftwarePage *page;
    explicit SoftwareFrame(const QString &root){
        for(const auto *n:{"uninstallTab","pacmanDoctorTab"})new QVBoxLayout(widget<QWidget>(this,n));
        for(const auto *n:{"uninstallCountLabel","uninstallSelectedSizeLabel","uninstallHelperLabel","pacDocStatus","pacDocDiagnosis"})widget<QLabel>(this,n);
        for(const auto *n:{"uninstallButton","orphanCleanButton","cacheCleanButton","pacDocDiagnose","pacDocMirrors","pacDocKeys","pacDocUnlock","pacDocDowngrade","pacDocTrim","pacDocSync","pacDocMerge","pacDocOpenNew","pacDocOpenCurrent","pacDocApply","pacDocBackup","pacDocEdit"})widget<QPushButton>(this,n);
        for(const auto *n:{"uninstallDepsCheckBox","pacDocColor","pacDocCandy","pacDocVerbose","pacDocCheckSpace","pacDocTimeout"})widget<QCheckBox>(this,n);
        widget<QSpinBox>(this,"pacDocParallel");widget<QListWidget>(this,"pacDocFiles");widget<QComboBox>(this,"uninstallHelperCombo");widget<QComboBox>(this,"uninstallSourceFilter");widget<QLineEdit>(this,"uninstallSearch");widget<QTableWidget>(this,"uninstallTable")->setColumnCount(6);
        for(auto *w:findChildren<QWidget *>())w->hide();
        page=new SoftwarePage(this,root,root+"/fixture-terminal",this);auto *layout=new QVBoxLayout(this);layout->setContentsMargins(18,16,18,16);layout->addWidget(page);setAutoFillBackground(true);
    }
};
}

class SoftwareCatalogTests:public QObject {
    Q_OBJECT
    QTemporaryDir directory;
    QString root;
    QJsonObject packet;
    QList<QUrl> openedUrls;
    void save(){QVERIFY(write(root+"/packet.json",QJsonDocument(packet).toJson(QJsonDocument::Compact)));}
    std::unique_ptr<SoftwareCatalogPage> page(){auto p=std::make_unique<SoftwareCatalogPage>(root,root+"/terminal");p->resize(1300,760);p->show();return p;}
private slots:
    void initTestCase(){qApp->setQuitOnLastWindowClosed(false);qApp->setAttribute(Qt::AA_DontUseNativeDialogs);qApp->setStyle("Fusion");QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());}
    void init(){
        openedUrls.clear();QDesktopServices::setUrlHandler("https",this,"recordUrl");QDesktopServices::setUrlHandler("file",this,"recordUrl");
        QSettings("XetalHyperland","ControlPanel").clear();QSettings("XetalHyperland","ControlPanel").setValue("software/catalog/repositoriesInitialized",true);root=directory.filePath(QUuid::createUuid().toString(QUuid::WithoutBraces));QDir().mkpath(root+"/control_panel/software");
        QVERIFY(QFile::copy(sourceRoot()+"/control_panel/software/catalog.json",root+"/control_panel/software/catalog.json"));
        packet={{"type","catalog"},{"schema",1},{"generated",1700000000},{"helpers",QJsonObject{{"pacman",true},{"yay",true},{"paru",true}}},{"multilib",true},
            {"apps",QJsonArray{app("alpha"),app("beta","Development"),app("chromium","WebBrowser"),app("community","Utility","aur")}}};save();
        QVERIFY(write(root+"/control_panel/software_catalog.py",R"PY(import json,pathlib,sys,time
p=pathlib.Path(__file__).parent.parent
with (p/'calls').open('a') as f:f.write(' '.join(sys.argv[1:])+'\n')
time.sleep(.06)
if (p/'fail').exists():print(json.dumps({'type':'error','message':'Fixture refresh unavailable'}));sys.exit(1)
if '--vendor' in sys.argv:print((p/'vendor.json').read_text())
elif '--aur' in sys.argv and (p/'aur-fail').exists():print(json.dumps({'type':'error','message':'AUR fixture unavailable'}))
elif '--aur' in sys.argv:print(json.dumps({'type':'aur','apps':[{'id':'aur/additional','package':'additional','name':'Additional','summary':'hello fixture','source':'aur','available':True}]}))
else:print((p/'packet.json').read_text())
)PY"));
        QVERIFY(write(root+"/terminal",("#!/bin/sh\nprintf '%s\\n' \"$@\" > '"+root+"/transaction'\n").toUtf8(),true));
    }
    void cleanup(){QDesktopServices::unsetUrlHandler("https");QDesktopServices::unsetUrlHandler("file");}
    void recordUrl(const QUrl &url){openedUrls<<url;}
    void immediateFeaturedAndPacmanDefault(){
        auto p=page();QVERIFY(p->findChild<QCheckBox *>("softwareSourcePacman")->isChecked());QVERIFY(!p->findChild<QCheckBox *>("softwareSourceYay")->isChecked());QVERIFY(!p->findChild<QCheckBox *>("softwareSourceParu")->isChecked());
        auto *initial=p->findChild<QListView *>("softwareAppGrid");
        const QStringList featured{"echo","linuxstudio","xmusic","xvideo","discord","google-chrome"};
        for(int i=0;i<featured.size();++i)QVERIFY(initial->model()->index(i,0).data(Qt::UserRole+1).toString().endsWith('/'+featured[i]));
        bool tick=false;QTimer::singleShot(1,p.get(),[&]{tick=true;});QTRY_VERIFY(tick);
        QTRY_VERIFY(p->findChild<QLabel *>("softwareCatalogStatus")->text().contains("multilib enabled"));
        auto *grid=p->findChild<QListView *>("softwareAppGrid");QCOMPARE(grid->model()->rowCount(),3);
        QVERIFY(!read(root+"/calls").contains("--aur"));
    }
    void categoriesAndLocalSearchDoNotStartNetworkOrReload(){
        auto p=page();auto *tree=p->findChild<QTreeWidget *>("softwareCategories");auto *grid=p->findChild<QListView *>("softwareAppGrid");
        QTRY_VERIFY(p->findChild<QLabel *>("softwareCatalogStatus")->text().contains("refreshed"));const auto before=read(root+"/calls");
        tree->setCurrentItem(category(tree,"development"));QCOMPARE(grid->model()->rowCount(),1);QCOMPARE(grid->model()->index(0,0).data(Qt::UserRole+1).toString(),QString("pacman/beta"));
        p->findChild<QLineEdit *>("softwareAppSearch")->setText("alpha");QTRY_COMPARE(grid->model()->rowCount(),1);QTRY_COMPARE(grid->model()->index(0,0).data(Qt::UserRole+1).toString(),QString("pacman/alpha"));
        QTest::qWait(750);QCOMPARE(read(root+"/calls"),before);
        p->findChild<QCheckBox *>("softwareSourceYay")->setChecked(true);QTRY_VERIFY(read(root+"/calls").contains("--aur alpha"));
        p->findChild<QCheckBox *>("softwareSourceParu")->setChecked(true);QTest::qWait(800);QCOMPARE(read(root+"/calls").count("--aur alpha"),1);
    }
    void explicitRefreshRechecksAurAndFailureDoesNotRelabelOldResults(){
        auto p=page();QTRY_VERIFY(p->findChild<QCheckBox *>("softwareSourceYay")->isEnabled());p->findChild<QCheckBox *>("softwareSourceYay")->setChecked(true);
        auto *search=p->findChild<QLineEdit *>("softwareAppSearch");auto *grid=p->findChild<QListView *>("softwareAppGrid");search->setText("hello");
        QTRY_COMPARE(grid->model()->rowCount(),1);QCOMPARE(grid->model()->index(0,0).data(Qt::UserRole+1).toString(),QString("aur/additional"));
        p->refresh();QTRY_VERIFY(read(root+"/calls").contains("--aur hello --refresh"));
        QVERIFY(write(root+"/aur-fail","1"));search->setText("fixture");QTRY_VERIFY(p->findChild<QLabel *>("catalogNotice")->text().contains("AUR fixture unavailable"));QCOMPARE(grid->model()->rowCount(),0);
    }
    void vendorDownloadsSaveTheFileWithoutOpeningTheBrowser(){
        auto value=app("xmusic","Music","vendor");value["name"]="XMusic";value["website"]="https://www.xetal.net/community/site/?p=xmusic";
        packet["apps"]=QJsonArray{value};save();
        QJsonObject choice{{"label","Installer · .run"},{"size",1024},{"filename","XMusic-fixture.run"},{"url","https://www.xetal.net/community/site/Downloads/xmusic/XMusic-fixture.run"},{"instructions","Run the downloaded installer when ready."}};
        QVERIFY(write(root+"/vendor.json",QJsonDocument(QJsonObject{{"type","vendor"},{"product","xmusic"},{"version","0.1.2"},{"choices",QJsonArray{choice}}}).toJson()));
        auto p=page();auto *grid=p->findChild<QListView *>("softwareAppGrid");QTRY_COMPARE(grid->model()->rowCount(),1);QVERIFY(!read(root+"/calls").contains("--vendor"));QVERIFY(openedUrls.isEmpty());
        QVERIFY(write(root+"/control_panel/software_download.py",R"PY(import json,pathlib,sys
p=pathlib.Path(sys.argv[sys.argv.index('--output')+1]);p.write_bytes(b'fixture installer')
(pathlib.Path(__file__).parent.parent/'download-target').write_text(str(p))
print(json.dumps({'type':'progress','current':17,'total':17}),flush=True)
print(json.dumps({'type':'downloaded','path':str(p)}),flush=True)
)PY"));
        QDir().mkpath(root+"/scripts");
        QVERIFY(write(root+"/scripts/files.sh",("#!/bin/sh\nprintf '%s\\n' \"$@\" > '"+root+"/fusion-files-folder'\n").toUtf8(),true));
        bool offered=false,saved=false,fileChosen=false;QTimer check;check.setInterval(20);
        connect(&check,&QTimer::timeout,p.get(),[&]{
            if(auto *progress=p->findChild<QDialog *>("softwareDownloadProgress")){
                auto *status=progress->findChild<QLabel *>("softwareDownloadStatus");
                if(status&&status->text().contains("checksum verified")){saved=true;auto *folder=progress->findChild<QPushButton *>("softwareOpenDownloadFolder");if(folder)folder->click();progress->reject();}return;
            }
            for(auto *w:qApp->topLevelWidgets())if(auto *file=qobject_cast<QFileDialog *>(w)){
                if(file->isVisible()){
                    if(!fileChosen){fileChosen=true;file->setDirectory(root);QTimer::singleShot(40,file,[file]{if(auto *name=file->findChild<QLineEdit *>("fileNameEdit"))name->setText("saved.run");QMetaObject::invokeMethod(file,"accept",Qt::QueuedConnection);});}
                    return;
                }
            }
            auto *dialog=p->findChild<QDialog *>("softwareVendorDownloads");if(!dialog)return;
            if(saved){dialog->reject();return;}
            auto *formats=dialog->findChild<QComboBox *>("softwareDownloadFormat");if(!formats||!formats->isEnabled()||offered)return;
            offered=formats->count()==1;QTimer::singleShot(0,dialog->findChild<QPushButton *>("catalogAction"),&QPushButton::click);
        });check.start();
        QTimer::singleShot(5000,p.get(),[&]{for(auto *w:qApp->topLevelWidgets())if(auto *dialog=qobject_cast<QDialog *>(w))dialog->reject();});
        QTest::qWait(20);const auto rect=grid->visualRect(grid->model()->index(0,0));QTest::mouseClick(grid->viewport(),Qt::LeftButton,Qt::NoModifier,QPoint(rect.right()-70,rect.bottom()-30));check.stop();
        QVERIFY(offered);QVERIFY(saved);QCOMPARE(QString::fromUtf8(read(root+"/download-target")),root+"/saved.run");QCOMPARE(read(root+"/saved.run"),QByteArray("fixture installer"));QVERIFY(openedUrls.isEmpty());
        QTRY_COMPARE(QString::fromUtf8(read(root+"/fusion-files-folder")),root+'\n');
        QVERIFY(read(root+"/calls").contains("--vendor xmusic"));QVERIFY(!QFileInfo::exists(root+"/transaction"));
    }
    void failedRefreshKeepsCardsAndSelection(){
        auto p=page();auto *grid=p->findChild<QListView *>("softwareAppGrid");QTRY_COMPARE(grid->model()->rowCount(),3);grid->setCurrentIndex(grid->model()->index(1,0));const auto selected=grid->currentIndex().data(Qt::UserRole+1);
        QVERIFY(write(root+"/fail","1"));p->refresh();QTRY_VERIFY(p->findChild<QLabel *>("catalogNotice")->text().contains("Fixture"));QCOMPARE(grid->model()->rowCount(),3);QCOMPARE(grid->currentIndex().data(Qt::UserRole+1),selected);
    }
    void validatedAppOffersPackageAndDebInstallerRoutes(){
        auto value=app("discord");value["deb_id"]="discord";value["deb_note"]="Tested working";packet["apps"]=QJsonArray{value};save();
        auto p=page();QSignalSpy selected(p.get(),&SoftwareCatalogPage::installDebRequested);auto *grid=p->findChild<QListView *>("softwareAppGrid");QTRY_COMPARE(grid->model()->rowCount(),1);
        bool offered=false;QTimer::singleShot(40,p.get(),[&]{auto *dialog=p->findChild<QDialog *>("softwareAppDetails");if(!dialog)return;auto *package=dialog->findChild<QPushButton *>("softwareInstallPackage");auto *deb=dialog->findChild<QPushButton *>("softwareInstallDeb");offered=package&&package->text()=="Install with Pacman"&&deb&&deb->isEnabled();if(deb)deb->click();else dialog->reject();});
        QTest::mouseClick(grid->viewport(),Qt::LeftButton,Qt::NoModifier,grid->visualRect(grid->model()->index(0,0)).topLeft()+QPoint(90,50));
        QVERIFY(offered);QCOMPARE(selected.size(),1);QCOMPARE(selected[0][0].toString(),QString("discord"));QVERIFY(!QFileInfo::exists(root+"/transaction"));
    }
    void uninstallUsesActualInstalledAliasAndKeepsReview(){
        auto value=app("google-chrome");value["installed"]=true;value["installed_package"]="google-chrome-stable";packet["apps"]=QJsonArray{value};save();
        auto p=page();auto *grid=p->findChild<QListView *>("softwareAppGrid");QTRY_COMPARE(grid->model()->rowCount(),1);
        QTimer check;check.setInterval(20);bool clicked=false,confirmed=false;
        connect(&check,&QTimer::timeout,p.get(),[&]{
            if(auto *confirm=p->findChild<QMessageBox *>("softwareUninstallConfirm")){confirmed=confirm->informativeText().contains("google-chrome-stable");confirm->done(QMessageBox::Yes);return;}
            if(auto *dialog=p->findChild<QDialog *>("softwareAppDetails")){if(!clicked){clicked=true;auto *button=dialog->findChild<QPushButton *>("softwareUninstallApp");if(button)QTimer::singleShot(0,button,&QPushButton::click);else dialog->reject();}}
        });check.start();
        QTest::mouseClick(grid->viewport(),Qt::LeftButton,Qt::NoModifier,grid->visualRect(grid->model()->index(0,0)).topLeft()+QPoint(90,50));check.stop();
        QVERIFY(confirmed);QTRY_VERIFY(QFileInfo::exists(root+"/transaction"));const auto command=read(root+"/transaction");QVERIFY(command.contains("sudo pacman -R -- 'google-chrome-stable'"));QVERIFY(!command.contains("--noconfirm"));QVERIFY(!command.contains("-Rns"));
        QVERIFY(SoftwareActions::removePackage("bad; touch /tmp/unsafe").isEmpty());
    }
    void firstVisitRefreshesOnlyListsAndRemembersSuccess(){
        QSettings("XetalHyperland","ControlPanel").setValue("software/catalog/repositoriesInitialized",false);
        QDir().mkpath(root+"/bin");QDir().mkpath(root+"/scripts");QVERIFY(write(root+"/scripts/sudo-askpass.sh","#!/bin/sh\n",true));
        QVERIFY(write(root+"/bin/sudo",("#!/bin/sh\nprintf '%s\\n' \"$@\" > '"+root+"/sync-command'\nprintf 'Package lists refreshed\\n'\n").toUtf8(),true));
        const auto old=qgetenv("PATH");qputenv("PATH",root.toUtf8()+"/bin:"+old);const auto restore=qScopeGuard([old]{qputenv("PATH",old);});
        auto p=page();QTimer check;check.setInterval(20);int prompts=0;
        connect(&check,&QTimer::timeout,p.get(),[&]{
            if(auto *prompt=p->findChild<QMessageBox *>("softwareRepositoryPrompt");prompt&&prompt->isVisible()){++prompts;prompt->done(QMessageBox::Yes);return;}
            if(auto *dialog=p->findChild<QDialog *>("softwareRepositorySync")){auto *status=dialog->findChild<QLabel *>("softwareRepositoryStatus");if(status&&status->text().contains("catalog is ready"))dialog->reject();}
        });check.start();QTRY_VERIFY(QSettings("XetalHyperland","ControlPanel").value("software/catalog/repositoriesInitialized").toBool());check.stop();
        QCOMPARE(prompts,1);QCOMPARE(read(root+"/sync-command"),QByteArray("-A\n-k\n--\npacman\n-Sy\n"));
        p->hide();p->show();p->refresh();QTest::qWait(120);QCOMPARE(prompts,1);
    }
    void localUninstallRecognizesOnlyInstallerFolders(){
        const QString home=root+"/home",folder=home+"/.local/opt/XMusic",desktop=home+"/.local/share/applications/xmusic.desktop";
        QDir().mkpath(folder);QDir().mkpath(QFileInfo(desktop).absolutePath());QVERIFY(write(folder+"/run.sh","#!/bin/sh\n"));
        QVERIFY(write(desktop,("[Desktop Entry]\nExec=\""+folder+"/run.sh\" %F\n").toUtf8()));
        QCOMPARE(SoftwareActions::localRemovalPaths("xmusic",desktop,home),QStringList({folder,desktop}));
        QVERIFY(write(desktop,("[Desktop Entry]\nExec="+home+"/Desktop/source/run.sh\n").toUtf8()));
        QVERIFY(SoftwareActions::localRemovalPaths("xmusic",desktop,home).isEmpty());
        QVERIFY(SoftwareActions::localRemovalPaths("other",desktop,home).isEmpty());
    }
    void failedRepositoryAuthenticationCanBeRetried(){
        QDir().mkpath(root+"/bin");QDir().mkpath(root+"/scripts");QVERIFY(write(root+"/scripts/sudo-askpass.sh","#!/bin/sh\n",true));
        QVERIFY(write(root+"/bin/sudo","#!/bin/sh\nprintf 'Authentication cancelled\\n'\nexit 1\n",true));
        const auto old=qgetenv("PATH");qputenv("PATH",root.toUtf8()+"/bin:"+old);const auto restore=qScopeGuard([old]{qputenv("PATH",old);});
        auto p=page();QTRY_VERIFY(p->findChild<QLabel *>("softwareCatalogStatus")->text().contains("refreshed"));
        QSettings("XetalHyperland","ControlPanel").setValue("software/catalog/repositoriesInitialized",false);
        bool sawFailure=false,sawRetry=false;QTimer check;check.setInterval(20);
        connect(&check,&QTimer::timeout,p.get(),[&]{
            if(auto *dialog=p->findChild<QDialog *>("softwareRepositorySync")){
                auto *status=dialog->findChild<QLabel *>("softwareRepositoryStatus");if(!status||!status->text().contains("could not"))return;
                sawFailure=true;for(auto *button:dialog->findChildren<QPushButton *>())if(button->text()=="Retry")sawRetry=button->isVisible()&&button->isEnabled();dialog->reject();
            }
        });check.start();p->findChild<QPushButton *>("softwareSyncRepositories")->click();check.stop();
        QVERIFY(sawFailure);QVERIFY(sawRetry);QVERIFY(!QSettings("XetalHyperland","ControlPanel").value("software/catalog/repositoriesInitialized").toBool());
        QCOMPARE(p->findChild<QListView *>("softwareAppGrid")->model()->rowCount(),3);
    }
    void sourceChoicePersistsAndNarrowLayoutKeepsFeatured(){
        {auto p=page();QTRY_VERIFY(p->findChild<QCheckBox *>("softwareSourceParu")->isEnabled());p->findChild<QCheckBox *>("softwareSourceParu")->setChecked(true);}
        auto p=page();QVERIFY(p->findChild<QCheckBox *>("softwareSourceParu")->isChecked());p->resize(740,640);QTest::qWait(30);
        QCOMPARE(p->findChild<QListView *>("softwareAppGrid")->horizontalScrollBar()->maximum(),0);
    }
    void installationUsesReviewedPacmanTransaction(){
        auto p=page();auto *grid=p->findChild<QListView *>("softwareAppGrid");QTRY_COMPARE(grid->model()->rowCount(),3);QTest::qWait(20);
        QTimer::singleShot(30,p.get(),[]{for(auto *w:qApp->topLevelWidgets())if(auto *box=qobject_cast<QMessageBox *>(w))box->done(QMessageBox::Yes);});
        const auto rect=grid->visualRect(grid->model()->index(0,0));QTest::mouseClick(grid->viewport(),Qt::LeftButton,Qt::NoModifier,QPoint(rect.right()-70,rect.bottom()-30));
        QTRY_VERIFY(read(root+"/transaction").contains("sudo pacman -Syu -- 'extra/alpha'"));auto transaction=read(root+"/transaction");QVERIFY(!transaction.contains("--noconfirm"));QVERIFY(!transaction.contains("--skipreview"));
    }
    void realCatalogPreview(){
        const auto profile=qEnvironmentVariable("FUSION_SOFTWARE_PREVIEW_ROOT");if(profile.isEmpty())QSKIP("Optional real-data, read-only preview");
        const auto output=qEnvironmentVariable("FUSION_SOFTWARE_PREVIEW_DIR");QVERIFY(!output.isEmpty());QDir().mkpath(output);
        QIcon::setThemeName("Papirus-Dark");QPalette palette;
        QFile file(profile+"/theme/palettes.json");QVERIFY(file.open(QIODevice::ReadOnly));auto colors=QJsonDocument::fromJson(file.readAll()).object()["polaris"].toObject()["dark"].toObject();
        const QHash<QString,QPalette::ColorRole> roles{{"Window",QPalette::Window},{"WindowText",QPalette::WindowText},{"Base",QPalette::Base},{"AlternateBase",QPalette::AlternateBase},{"Text",QPalette::Text},{"Button",QPalette::Button},{"ButtonText",QPalette::ButtonText},{"Highlight",QPalette::Highlight},{"HighlightedText",QPalette::HighlightedText},{"PlaceholderText",QPalette::PlaceholderText},{"Mid",QPalette::Mid},{"Midlight",QPalette::Midlight},{"Link",QPalette::Link}};
        const auto themePath=qEnvironmentVariable("FUSION_SOFTWARE_PREVIEW_THEME");QJsonObject theme;
        if(!themePath.isEmpty()){QFile style(themePath);QVERIFY(style.open(QIODevice::ReadOnly));theme=QJsonDocument::fromJson(style.readAll()).object();colors=theme["colors"].toObject();}
        for(auto i=roles.cbegin();i!=roles.cend();++i)palette.setColor(i.value(),QColor(colors[i.key()].toString()));qApp->setPalette(palette);
        if(!theme.isEmpty()){QStringList paths;for(auto path:theme["iconSearchPaths"].toArray())paths<<path.toString();QIcon::setThemeSearchPaths(paths);QIcon::setThemeName(theme["iconTheme"].toString());qApp->setStyleSheet(theme["stylesheet"].toString());qApp->setFont(QFont(theme["font"].toString(),10));}
        QElapsedTimer timer;timer.start();SoftwareFrame frame(profile);frame.resize(1600,900);frame.show();const qint64 initial=timer.elapsed();
        QTRY_VERIFY_WITH_TIMEOUT(frame.findChild<QLabel *>("softwareCatalogStatus")->text().contains("refreshed"),15000);const qint64 ready=timer.elapsed();QTest::qWait(80);
        QVERIFY(frame.grab().save(output+"/top-picks.png"));auto *tree=frame.findChild<QTreeWidget *>("softwareCategories");auto *grid=frame.findChild<QListView *>("softwareAppGrid");
        timer.restart();tree->setCurrentItem(category(tree,"development"));const qint64 categoryTime=timer.elapsed();QTest::qWait(60);QVERIFY(frame.grab().save(output+"/development.png"));
        timer.restart();tree->setCurrentItem(category(tree,"packages"));const qint64 packagesTime=timer.elapsed();QTest::qWait(60);QVERIFY(frame.grab().save(output+"/packages.png"));
        QJsonObject report{{"initial_widget_ms",initial},{"catalog_ready_ms",ready},{"category_filter_ms",categoryTime},{"all_packages_filter_ms",packagesTime},{"packages",grid->model()->rowCount()},{"grid_children",grid->findChildren<QWidget *>().size()}};
        QVERIFY(write(output+"/timings.json",QJsonDocument(report).toJson()));
        tree->setCurrentItem(category(tree,"top"));frame.resize(900,700);QTest::qWait(80);QVERIFY(frame.grab().save(output+"/narrow.png"));
    }
};
QTEST_MAIN(SoftwareCatalogTests)
#include "software_catalog_tests.moc"
