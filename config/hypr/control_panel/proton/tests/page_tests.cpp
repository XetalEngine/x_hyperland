#include "page.h"
#include "src/util.h"
#include "desktop.h"
#include <QtTest>
#include <QTemporaryDir>
#include <QJsonObject>
#include <QJsonArray>
#include <filesystem>

using namespace XetalProton;
namespace fs=std::filesystem;
class ProtonPageTests : public QObject {
    Q_OBJECT
    std::unique_ptr<QTemporaryDir> fixture;
    QString runner;
    void write(const QString &path,const QByteArray &bytes,bool executable=false) {
        QDir().mkpath(QFileInfo(path).absolutePath());QFile file(path);QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(bytes),bytes.size());file.close();
        if(executable)QVERIFY(file.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner|QFileDevice::ExeOwner));
    }
    void tool(const QString &name) {
        runner=Ui::text(util::tools_dir())+"/"+name;
        write(runner+"/proton","#!/bin/sh\nprintf '%s\\n' \"$WINEPREFIX\" > \"$WINEPREFIX/launched.txt\"\nprintf '%s\\n' \"$@\" > \"$WINEPREFIX/arguments.txt\"\n[ \"$HOLD_FIXTURE\" != 1 ] || sleep 3\n",true);
        write(runner+"/version","0 fixture\n");
        write(runner+"/.xetalproton-tool.json",QJsonDocument(QJsonObject{{"provider","ge"},{"name",name},{"version","fixture"},{"entrypoint","proton"}}).toJson());
        write(runner+"/protonfixes/winetricks","w_metadata corefonts fonts\nw_metadata vcrun2022 dlls\n");
    }
    void show(Page &page) {page.resize(1150,720);page.show();QTRY_VERIFY(page.controller()->loaded);}
private slots:
    void initTestCase() {
        const auto path=qEnvironmentVariable("XETALPROTON_TEST_THEME");if(path.isEmpty())return;
        QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto theme=QJsonDocument::fromJson(file.readAll()).object();
        QPalette palette;const auto colors=theme["colors"].toObject();const auto roles=QMetaEnum::fromType<QPalette::ColorRole>();
        for(auto it=colors.begin();it!=colors.end();++it){const int role=roles.keyToValue(it.key().toUtf8());if(role>=0)palette.setColor(QPalette::All,QPalette::ColorRole(role),QColor(it.value().toString()));}
        QApplication::setPalette(palette);QApplication::setFont(QFont(theme["font"].toString("Noto Sans"),10));
        QStringList paths;for(const auto &value:theme["iconSearchPaths"].toArray())paths<<value.toString();QIcon::setThemeSearchPaths(paths);QIcon::setThemeName(theme["iconTheme"].toString());
        qApp->setStyleSheet(theme["stylesheet"].toString());
    }
    void init() {
        fixture=std::make_unique<QTemporaryDir>("/tmp/fusion-proton-page-XXXXXX");QVERIFY(fixture->isValid());
        qputenv("XETALPROTON_HOME",fixture->path().toUtf8());qputenv("XETALPROTON_OFFLINE","1");
        qputenv("XETAL_HYPR_ROOT",(fixture->path()+"/hypr").toUtf8());
        qputenv("XDG_CONFIG_HOME",(fixture->path()+"/config").toUtf8());
    }
    void cleanup() {fixture.reset();}
    void pageIsLazyAndHasEverySectionAndProvider() {
        Page page;QVERIFY(!QFileInfo::exists(Ui::text(config_path())));QVERIFY(!page.controller()->loaded);
        show(page);QVERIFY(!QFileInfo::exists(Ui::text(config_path())));
        QCOMPARE(page.findChild<QTabWidget *>("protonSections")->count(),5);
        QCOMPARE(page.findChild<QTabWidget *>("protonToolTabs")->count(),3);
        QCOMPARE(page.findChild<QComboBox *>("protonProviders")->count(),int(toolstore::providers().size()));
        QCOMPARE(page.findChild<QTableWidget *>("protonDependencies")->rowCount(),int(dependencies::catalog().size()));
        QVERIFY(!page.controller()->config.discover_steam);
    }
    void isolatedPrefixesAndRealChildLaunches() {
        tool("Fixture");Controller model;QVERIFY(model.reload());
        QVERIFY(model.createPrefix("First"));const auto first=model.current;QVERIFY(model.createPrefix("Second"));const auto second=model.current;
        QVERIFY(first!=second);QVERIFY(model.selectPrefix(first));
        Shortcut app;app.id=new_id();app.name="Fixture";app.exe="cmd.exe";app.prefix=first;app.use_runtime=false;app.env["HOLD_FIXTURE"]="1";
        auto next=model.config;next.shortcuts.push_back(app);QVERIFY(model.save(next));
        const auto pid=model.launchShortcut(app.id);QVERIFY(pid>0);QTRY_VERIFY(QFileInfo::exists(Ui::text(first)+"/pfx/launched.txt"));
        QVERIFY(dependencies::busy(first));QVERIFY(!dependencies::busy(second));QVERIFY(!model.removePrefix(false));
        app.prefix=second;app.env.clear();QVERIFY(model.updateShortcut(app));QVERIFY(model.launchShortcut(app.id)>0);
        QTRY_VERIFY(QFileInfo::exists(Ui::text(second)+"/pfx/launched.txt"));
        QFile firstFile(Ui::text(first)+"/pfx/launched.txt"),secondFile(Ui::text(second)+"/pfx/launched.txt");QVERIFY(firstFile.open(QIODevice::ReadOnly));QVERIFY(secondFile.open(QIODevice::ReadOnly));
        QCOMPARE(firstFile.readAll().trimmed(),QByteArray::fromStdString(first+"/pfx"));QCOMPARE(secondFile.readAll().trimmed(),QByteArray::fromStdString(second+"/pfx"));
        model.stopProcess(pid,true);QTRY_VERIFY(!dependencies::busy(first));
    }
    void configurationPreservesUnknownFieldsAndRejectsConcurrentEdits() {
        tool("Fixture");Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("Existing"));
        const auto path=Ui::text(config_path());QFile input(path);QVERIFY(input.open(QIODevice::ReadOnly));auto document=QJsonDocument::fromJson(input.readAll()).object();input.close();
        document["future_option"]="keep";auto prefixes=document["prefixes"].toArray();auto prefix=prefixes[0].toObject();prefix["future_prefix_option"]=true;prefixes[0]=prefix;document["prefixes"]=prefixes;write(path,QJsonDocument(document).toJson());
        QVERIFY(model.reload());QVERIFY(model.renamePrefix("Renamed"));QVERIFY(input.open(QIODevice::ReadOnly));document=QJsonDocument::fromJson(input.readAll()).object();input.close();
        QCOMPARE(document["future_option"].toString(),QString("keep"));QVERIFY(document["prefixes"].toArray()[0].toObject()["future_prefix_option"].toBool());
        const auto changed=QJsonDocument(document).toJson();write(path,changed);QVERIFY(!model.renamePrefix("Must not overwrite"));QVERIFY(model.notice.contains("another window"));
        QVERIFY(input.open(QIODevice::ReadOnly));QCOMPARE(input.readAll(),changed);
    }
    void corruptConfigurationCannotBeOverwritten() {
        for(const auto &content:{QByteArray("{broken"),QByteArray(),QByteArray("[]")}) {
            write(Ui::text(config_path()),content);Controller model;QVERIFY(!model.reload());QVERIFY(!model.save(Config{}));
            QFile file(Ui::text(config_path()));QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),content);
        }
    }
    void unavailableSelectedToolNeverFallsBackAndRemovalIsProtected() {
        tool("Fixture");Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("Game"));
        const auto installed=model.installed.front();QVERIFY(model.removeTool(installed));QTRY_VERIFY(!model.busy());QVERIFY(model.notice.contains("assigned"));QVERIFY(QFileInfo::exists(runner+"/proton"));
        auto next=model.config;next.prefix_proton[model.current]="/unavailable/proton";QVERIFY(model.save(next));
        Shortcut app;app.prefix=model.current;app.exe="cmd.exe";QVERIFY(!model.command(app).error.empty());
        QCOMPARE(model.config.prefix_proton.at(model.current),std::string("/unavailable/proton"));
    }
    void removePrefixKeepsFilesByDefaultAndRestrictsDeletion() {
        Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("Keep"));const auto kept=model.current;
        write(Ui::text(kept)+"/pfx/game.txt","saved game");QVERIFY(model.removePrefix(false));QVERIFY(QFileInfo::exists(Ui::text(kept)+"/pfx/game.txt"));
        const auto external=fixture->path()+"/imported";QDir().mkpath(external+"/pfx");QVERIFY(model.importPrefix(external));QVERIFY(!model.removePrefix(true));QVERIFY(QFileInfo(external+"/pfx").isDir());
        QVERIFY(model.createPrefix("Delete"));const auto removed=model.current;QVERIFY(model.removePrefix(true));QTRY_VERIFY(!model.busy());QVERIFY(!QFileInfo::exists(Ui::text(removed)));
    }
    void newPrefixAndShortcutEditorUseNativeControls() {
        tool("Fixture");Page page;show(page);
        page.findChild<QTabWidget *>("protonSections")->setCurrentIndex(4);
        QTimer::singleShot(30,[]{auto *dialog=qobject_cast<QInputDialog *>(QApplication::activeModalWidget());if(dialog){dialog->setTextValue("Editor fixture");dialog->accept();}});
        QTest::mouseClick(page.findChild<QPushButton *>("protonNewPrefix"),Qt::LeftButton);
        QCOMPARE(page.controller()->prefixes.size(),size_t(1));
        page.findChild<QTabWidget *>("protonSections")->setCurrentIndex(0);
        const auto app=fixture->path()+"/Example.exe";write(app,"fixture executable");QVERIFY(page.controller()->addShortcut(app,false));
        bool edited=false;
        QTimer::singleShot(30,[&]{auto *dialog=qobject_cast<QDialog *>(QApplication::activeModalWidget());if(!dialog)return;
            auto *name=dialog->findChild<QLineEdit *>("protonShortcutName");auto *option=dialog->findChild<QCheckBox *>("protonOption_PROTON_NO_ESYNC");
            if(name && option){name->selectAll();QTest::keyClicks(name,"Edited app");option->setChecked(true);dialog->findChild<QPlainTextEdit *>("protonCustomEnv")->setPlainText("CUSTOM_VALUE=with spaces");edited=true;}
            auto *buttons=dialog->findChild<QDialogButtonBox *>();QTest::mouseClick(buttons->button(QDialogButtonBox::Save),Qt::LeftButton);
        });
        QTest::mouseClick(page.findChild<QPushButton *>("protonEditShortcut"),Qt::LeftButton);
        QVERIFY(edited);const auto &shortcut=page.controller()->config.shortcuts.front();QCOMPARE(shortcut.name,std::string("Edited app"));QCOMPARE(shortcut.env.at("PROTON_NO_ESYNC"),std::string("1"));
        QCOMPARE(shortcut.custom_env,std::string("CUSTOM_VALUE=with spaces"));
        page.findChild<QAction *>("protonDuplicate")->trigger();QCOMPARE(page.controller()->config.shortcuts.size(),size_t(2));
    }
    void dependencyStatusAndDownloadFilteringArePrefixSpecific() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("One"));const auto one=model.current;
        write(Ui::text(one)+"/pfx/winetricks.log","corefonts\n");model.changed();
        auto *search=page.findChild<QLineEdit *>("protonDependencySearch");search->setText("corefonts");auto *table=page.findChild<QTableWidget *>("protonDependencies");QCOMPARE(table->rowCount(),1);QCOMPARE(table->item(0,2)->text(),QString("Installed"));
        QVERIFY(model.createPrefix("Two"));QCOMPARE(table->item(0,2)->text(),QString("Missing"));
        toolstore::Release stable;stable.provider="ge";stable.name=stable.version="Stable";stable.asset="Stable.tar.gz";stable.url="https://example.com/stable";
        auto beta=stable;beta.version="Beta";beta.prerelease=true;auto wrong=stable;wrong.version="ARM";wrong.incompatibility="Requires ARM64";
        model.releases={stable,beta,wrong};model.changed();QCOMPARE(page.findChild<QTableWidget *>("protonReleases")->rowCount(),1);
        page.findChild<QLineEdit *>("protonReleaseSearch")->setText("does not exist");QCOMPARE(page.findChild<QTableWidget *>("protonReleases")->rowCount(),0);
    }
    void shortcutExportsTheSelectedPrefixAndPreservesCustomOptions() {
        tool("Fixture");Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("App"));
        const auto app=fixture->path()+"/space name.exe";write(app,"fixture");QVERIFY(model.addShortcut(app,false));
        auto shortcut=model.config.shortcuts.front();shortcut.use_runtime=false;shortcut.env["FUTURE_OPTION"]="value";shortcut.custom_env="MY_OPTION=space value";QVERIFY(model.updateShortcut(shortcut));
        const auto output=fixture->path()+"/launch.sh";QVERIFY(model.exportScript(shortcut.id,output));
        QFile file(output);QVERIFY(file.open(QIODevice::ReadOnly));const auto script=file.readAll();QVERIFY(script.contains("FUTURE_OPTION=value"));QVERIFY(script.contains(QByteArray::fromStdString(model.current+"/pfx")));QVERIFY(script.contains("'space value'"));QVERIFY(file.permissions()&QFileDevice::ExeOwner);
    }
    void browserSignInEditorPersistsAndExportsTheMatchingHandler() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("Sign in"));
        const auto app=fixture->path()+"/Example.exe";write(app,"fixture");QVERIFY(model.addShortcut(app,false));
        bool edited=false;
        QTimer::singleShot(30,[&]{
            auto *dialog=qobject_cast<QDialog *>(QApplication::activeModalWidget());if(!dialog)return;
            auto *enabled=dialog->findChild<QCheckBox *>("protonHandleUrls");
            if(enabled){
                enabled->setChecked(true);dialog->findChild<QLineEdit *>("protonUrlSchemes")->setText("example-login, example-app");
                dialog->findChild<QLineEdit *>("protonUrlArgument")->setText("--url={url}");
                dialog->findChild<QCheckBox *>("protonUrlIncludeArgs")->setChecked(false);
                dialog->findChild<QCheckBox *>("protonUseRuntime")->setChecked(false);edited=true;
            }
            const auto screenshots=qEnvironmentVariable("XETALPROTON_TEST_SCREENSHOTS");
            if(!screenshots.isEmpty()){QDir().mkpath(screenshots);dialog->grab().save(screenshots+"/browser-sign-in.png");}
            QTest::mouseClick(dialog->findChild<QDialogButtonBox *>()->button(QDialogButtonBox::Save),Qt::LeftButton);
        });
        page.findChild<QAction *>("protonBrowserSignIn")->trigger();QVERIFY(edited);
        const auto selected=model.config.shortcuts.front();QVERIFY(selected.desktop.enabled);QVERIFY(selected.desktop.private_output);
        const auto screenshots=qEnvironmentVariable("XETALPROTON_TEST_SCREENSHOTS");
        if(!screenshots.isEmpty()){QTest::qWait(30);page.grab().save(screenshots+"/proton-library.png");}
        QCOMPARE(selected.desktop.argument,std::string("--url={url}"));QVERIFY(!selected.desktop.include_args);
        QVERIFY(QFileInfo::exists(Desktop::manifest(selected.id)));QVERIFY(page.findChild<QAction *>("protonRepairHandlers")->isEnabled());
        QVERIFY(model.reload());QVERIFY(model.shortcut(selected.id)->desktop.enabled);
        const auto exported=fixture->path()+"/with-login.sh";QVERIFY(model.exportScript(selected.id,exported));
        QFile script(exported);QVERIFY(script.open(QIODevice::ReadOnly));const auto data=script.readAll();QVERIFY(data.contains("desktop_bridge.py"));QVERIFY(data.contains("--launch"));
        QVERIFY(model.duplicateShortcut(selected.id));QVERIFY(!model.config.shortcuts.back().desktop.enabled);
        auto disabled=selected;disabled.desktop.enabled=false;QVERIFY(model.updateShortcut(disabled));QVERIFY(!QFileInfo::exists(Desktop::manifest(selected.id)));
    }
    void invalidBrowserSettingsNeverOverwriteTheConfig() {
        tool("Fixture");Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("App"));
        const auto app=fixture->path()+"/Example.exe";write(app,"fixture");QVERIFY(model.addShortcut(app,false));
        QFile file(Ui::text(config_path()));QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();
        auto shortcut=model.config.shortcuts.front();shortcut.use_runtime=false;shortcut.desktop.enabled=true;shortcut.desktop.schemes="https";
        QVERIFY(!model.updateShortcut(shortcut));QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();
        shortcut.desktop.schemes="example";shortcut.verb="waitforexitandrun";QVERIFY(!model.updateShortcut(shortcut));
        QVERIFY(model.notice.contains("run verb"));
    }
    void taskManagerUsesTheSelectedAppsPrefixAndRunner() {
        tool("Default");const auto defaultRunner=runner;tool("Override");const auto overrideRunner=runner;
        Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("App prefix"));const auto first=model.current;
        Shortcut app;app.id=new_id();app.name="App";app.exe="cmd.exe";app.prefix=first;app.proton=overrideRunner.toStdString();app.use_runtime=false;
        auto next=model.config;next.shortcuts.push_back(app);next.prefix_proton[first]=defaultRunner.toStdString();QVERIFY(model.save(next));
        QVERIFY(model.createPrefix("Other prefix"));const auto other=model.current;
        QVERIFY(model.runTaskManager(app.id)>0);QTRY_VERIFY(QFileInfo::exists(Ui::text(first)+"/pfx/arguments.txt"));
        QFile args(Ui::text(first)+"/pfx/arguments.txt");QVERIFY(args.open(QIODevice::ReadOnly));QCOMPARE(args.readAll(),QByteArray("runinprefix\ntaskmgr.exe\n"));
        QVERIFY(!QFileInfo::exists(Ui::text(other)+"/pfx/launched.txt"));
        QFile log(Ui::text(model.processes.back().log_path));QVERIFY(log.open(QIODevice::ReadOnly));QVERIFY(log.readAll().contains(overrideRunner.toUtf8()));
    }
    void privateSignInLaunchDoesNotCaptureAppOutput() {
        tool("Fixture");write(runner+"/proton","#!/bin/sh\necho fixture-private-token\n",true);
        Controller model;QVERIFY(model.reload());QVERIFY(model.createPrefix("Private app"));
        Shortcut app;app.id=new_id();app.name="Private app";app.exe="cmd.exe";app.prefix=model.current;app.use_runtime=false;
        app.desktop.enabled=true;app.desktop.schemes="fixture-login";
        const auto spec=model.command(app);QVERIFY(spec.private_output);QCOMPARE(spec.env.at("PROTON_LOG"),std::string("0"));
        QVERIFY(model.launch(spec)>0);QTRY_VERIFY(!model.processes.back().running);
        QFile log(Ui::text(spec.log_path));QVERIFY(log.open(QIODevice::ReadOnly));const auto data=log.readAll();
        QVERIFY(data.contains("Application output hidden"));QVERIFY(!data.contains("fixture-private-token"));
        QVERIFY(!(log.permissions()&QFileDevice::ReadGroup));QVERIFY(!(log.permissions()&QFileDevice::ReadOther));
    }
    void libraryKeepsSetupOutOfTheWayAndGuidesAnEmptyLibrary() {
        Page page;show(page);
        QVERIFY(page.findChild<QPushButton *>("protonTaskManager")->isVisible());
        QVERIFY(!page.findChild<QPushButton *>("protonTaskManager")->accessibleName().isEmpty());
        QVERIFY(!page.findChild<QPushButton *>("protonTaskManager")->icon().isNull());
        QVERIFY(!page.findChild<QPushButton *>("protonAddShortcut")->isEnabled());
        QVERIFY(!page.findChild<QComboBox *>("protonVersion")->isVisible());
        QVERIFY(!page.findChild<QPushButton *>("protonInit")->isVisible());
        QVERIFY(!page.findChild<QPlainTextEdit *>("protonCommand"));
        auto *empty=page.findChild<QPushButton *>("protonEmptyAction");QVERIFY(empty->isVisible());
        QTest::mouseClick(empty,Qt::LeftButton);
        QCOMPARE(page.findChild<QTabWidget *>("protonSections")->currentIndex(),4);
        QVERIFY(page.findChild<QComboBox *>("protonVersion")->isVisible());
        QVERIFY(page.findChild<QPushButton *>("protonNewPrefix")->isVisible());
    }
    void searchSelectsTheCorrectAppAndEnterLaunchesOnlyThatApp() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("Personal"));const auto personal=model.current;
        QVERIFY(model.createPrefix("Work"));const auto work=model.current;QVERIFY(model.selectPrefix(personal));
        auto next=model.config;
        for(const auto &name:{"Alpha","Beta","Gamma"}){Shortcut app;app.id=new_id();app.name=name;app.exe=fixture->path().toStdString()+"/"+name+".exe";app.prefix=name==std::string("Gamma")?work:personal;app.use_runtime=false;next.shortcuts.push_back(app);}
        QVERIFY(model.save(next));auto *list=page.findChild<QListWidget *>("protonShortcuts");QCOMPARE(list->count(),2);
        auto *search=page.findChild<QLineEdit *>("protonLibrarySearch");search->setText("bEt");
        QCOMPARE(page.findChild<QLabel *>("protonAppName")->text(),QString("Beta"));QVERIFY(model.processes.empty());
        QVERIFY(list->item(0)->isHidden());QVERIFY(!list->item(1)->isHidden());
        list->setFocus();QTest::keyClick(list,Qt::Key_Return);
        QTRY_VERIFY(QFileInfo::exists(Ui::text(personal)+"/pfx/arguments.txt"));
        QFile args(Ui::text(personal)+"/pfx/arguments.txt");QVERIFY(args.open(QIODevice::ReadOnly));QVERIFY(args.readAll().contains("Beta.exe"));
        search->setText("No matches");QVERIFY(!page.findChild<QPushButton *>("protonLaunch")->isEnabled());
        QTest::mouseClick(page.findChild<QPushButton *>("protonEmptyAction"),Qt::LeftButton);QVERIFY(search->text().isEmpty());
        auto *prefix=page.findChild<QComboBox *>("protonPrefix");prefix->setCurrentIndex(prefix->findData(Ui::text(work)));
        QCOMPARE(list->count(),1);QCOMPARE(page.findChild<QLabel *>("protonAppName")->text(),QString("Gamma"));
    }
    void advancedCommandIsAvailableFromTheAppMenu() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("Personal"));
        const auto exe=fixture->path()+"/Example.exe";write(exe,"fixture");QVERIFY(model.addShortcut(exe,false));
        auto app=model.config.shortcuts.front();app.use_runtime=false;QVERIFY(model.updateShortcut(app));
        bool inspected=false;
        QTimer::singleShot(30,[&]{auto *dialog=qobject_cast<QDialog *>(QApplication::activeModalWidget());if(!dialog)return;
            auto *command=dialog->findChild<QPlainTextEdit *>("protonCommand");
            inspected=command && command->toPlainText().contains(exe) && command->toPlainText().contains(Ui::text(model.current));
            if(command){QTest::mouseClick(dialog->findChild<QPushButton *>("protonCopyCommand"),Qt::LeftButton);QCOMPARE(QApplication::clipboard()->text(),command->toPlainText());}
            dialog->accept();
        });
        page.findChild<QAction *>("protonShowCommand")->trigger();QVERIFY(inspected);
        QVERIFY(!page.findChild<QPlainTextEdit *>("protonCommand"));
    }
    void launchFeedbackAcknowledgesTheSelectedAppAndRejectsRepeatClicks() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("Personal"));
        auto next=model.config;
        for(const auto *name:{"First app","Second app"}){Shortcut app;app.id=new_id();app.name=name;app.exe="cmd.exe";app.prefix=model.current;app.use_runtime=false;next.shortcuts.push_back(app);}
        QVERIFY(model.save(next));auto *list=page.findChild<QListWidget *>("protonShortcuts");list->setCurrentRow(0);
        auto *launch=page.findChild<QPushButton *>("protonLaunch");
        const auto screenshots=qEnvironmentVariable("XETALPROTON_TEST_SCREENSHOTS");
        auto capture=[&](const QString &name){if(!screenshots.isEmpty()){QDir().mkpath(screenshots);launch->grab().save(screenshots+"/"+name+".png");}};
        capture("launch-ready");QTest::mousePress(launch,Qt::LeftButton);capture("launch-pressed");
        QTest::mouseRelease(launch,Qt::LeftButton);
        QCOMPARE(launch->text(),QString("Launching…"));QVERIFY(!launch->isEnabled());capture("launch-pending");
        list->setFocus();QTest::keyClick(list,Qt::Key_Return);
        page.findChild<QAction *>("protonMenuLaunch")->trigger();
        QTRY_COMPARE(model.processes.size(),size_t(1));QTRY_COMPARE(launch->text(),QString("Launch sent"));
        QTest::qWait(300);capture("launch-sent");QCOMPARE(model.processes.size(),size_t(1));
        // A different app can launch immediately, and returning to the first
        // app keeps its acknowledgement until the brief repeat-click guard ends.
        list->setCurrentRow(1);QVERIFY(launch->isEnabled());QCOMPARE(launch->text(),QString("Launch"));
        launch->setFocus();QTest::keyClick(launch,Qt::Key_Space);QCOMPARE(launch->text(),QString("Launching…"));
        QTRY_COMPARE(model.processes.size(),size_t(2));list->setCurrentRow(0);
        QCOMPARE(launch->text(),QString("Launch sent"));QVERIFY(!launch->isEnabled());
        QTRY_VERIFY_WITH_TIMEOUT(launch->isEnabled(),2200);QCOMPARE(launch->text(),QString("Launch"));
        QCOMPARE(model.processes.size(),size_t(2));
        auto broken=model.config.shortcuts.front();broken.proton="/missing/proton";QVERIFY(model.updateShortcut(broken));
        QTest::mouseClick(launch,Qt::LeftButton);QCOMPARE(launch->text(),QString("Launching…"));
        QTRY_VERIFY(launch->isEnabled());QCOMPARE(launch->text(),QString("Launch"));QCOMPARE(model.processes.size(),size_t(2));
        QVERIFY(!model.notice.isEmpty());
    }
    void libraryLayoutWorksAtCommonWindowSizes() {
        tool("Fixture");Page page;show(page);auto &model=*page.controller();QVERIFY(model.createPrefix("Everyday"));auto next=model.config;
        const QStringList names={"Photo Studio","Work Notes","Music Player","Strategy Arena","Team Chat","Workshop"};
        const QList<QColor> colors={QColor("#6366db"),QColor("#d4a23b"),QColor("#bf507c"),QColor("#497dc4"),QColor("#32a273"),QColor("#a163d8")};
        for(int i=0;i<names.size();++i){
            QImage image(128,128,QImage::Format_ARGB32);image.fill(Qt::transparent);QPainter painter(&image);painter.setRenderHint(QPainter::Antialiasing);
            painter.setPen(Qt::NoPen);painter.setBrush(colors[i]);painter.drawRoundedRect(QRectF(3,3,122,122),26,26);painter.setPen(Qt::white);painter.setFont(QFont("Noto Sans",40,QFont::Bold));painter.drawText(image.rect(),Qt::AlignCenter,names[i].left(1));painter.end();
            const auto icon=fixture->path()+"/app-"+QString::number(i)+".png";QVERIFY(image.save(icon));
            Shortcut app;app.id=new_id();app.name=names[i].toStdString();app.exe=fixture->path().toStdString()+"/app.exe";app.icon_override=icon.toStdString();app.prefix=model.current;app.use_runtime=false;next.shortcuts.push_back(app);
        }
        QVERIFY(model.save(next));auto *sections=page.findChild<QTabWidget *>("protonSections");auto *list=page.findChild<QListWidget *>("protonShortcuts");list->setCurrentRow(3);
        QTest::qWait(80);
        for(const auto size:{QSize(1150,720),QSize(900,650),QSize(1600,900)}){
            page.resize(size);QTest::qWait(30);QCOMPARE(page.size(),size);
            auto *card=page.findChild<QFrame *>("protonAppCard");const auto corner=card->mapTo(&page,card->rect().bottomRight());
            QVERIFY(corner.x()<page.width());QVERIFY(corner.y()<page.height());QVERIFY(page.findChild<QPushButton *>("protonLaunch")->isVisible());
            const auto screenshots=qEnvironmentVariable("XETALPROTON_TEST_SCREENSHOTS");
            if(!screenshots.isEmpty()){QDir().mkpath(screenshots);page.grab().save(screenshots+"/library-"+QString::number(size.width())+".png");}
        }
        page.resize(1150,720);sections->setCurrentIndex(4);QTest::qWait(30);
        const auto screenshots=qEnvironmentVariable("XETALPROTON_TEST_SCREENSHOTS");if(!screenshots.isEmpty())page.grab().save(screenshots+"/settings.png");
        page.focusSearch();QCOMPARE(sections->currentIndex(),0);QVERIFY(page.findChild<QLineEdit *>("protonLibrarySearch")->hasFocus());
    }
};
QTEST_MAIN(ProtonPageTests)
#include "page_tests.moc"
