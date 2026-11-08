#include "page.h"
#include "src/util.h"
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
        write(runner+"/proton","#!/bin/sh\nprintf '%s\\n' \"$WINEPREFIX\" > \"$WINEPREFIX/launched.txt\"\n[ \"$HOLD_FIXTURE\" != 1 ] || sleep 3\n",true);
        write(runner+"/version","0 fixture\n");
        write(runner+"/.xetalproton-tool.json",QJsonDocument(QJsonObject{{"provider","ge"},{"name",name},{"version","fixture"},{"entrypoint","proton"}}).toJson());
        write(runner+"/protonfixes/winetricks","w_metadata corefonts fonts\nw_metadata vcrun2022 dlls\n");
    }
    void show(Page &page) {page.resize(1150,720);page.show();QTRY_VERIFY(page.controller()->loaded);}
private slots:
    void init() {
        fixture=std::make_unique<QTemporaryDir>("/tmp/fusion-proton-page-XXXXXX");QVERIFY(fixture->isValid());
        qputenv("XETALPROTON_HOME",fixture->path().toUtf8());qputenv("XETALPROTON_OFFLINE","1");
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
        QTimer::singleShot(30,[]{auto *dialog=qobject_cast<QInputDialog *>(QApplication::activeModalWidget());if(dialog){dialog->setTextValue("Editor fixture");dialog->accept();}});
        QTest::mouseClick(page.findChild<QPushButton *>("protonNewPrefix"),Qt::LeftButton);
        QCOMPARE(page.controller()->prefixes.size(),size_t(1));
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
        QTest::mouseClick(page.findChild<QPushButton *>("protonDuplicate"),Qt::LeftButton);QCOMPARE(page.controller()->config.shortcuts.size(),size_t(2));
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
};
QTEST_MAIN(ProtonPageTests)
#include "page_tests.moc"
