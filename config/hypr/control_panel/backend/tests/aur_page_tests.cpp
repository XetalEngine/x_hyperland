#include "aur_page.h"
#include <QtTest>
#include <QtWidgets>

namespace {
const QByteArray fixture = "extra/obs-studio 32.0.2-1 (8 MiB 26 MiB) [installed]\n"
    "    Free and open source software for video recording and live streaming\n"
    "aur/obs-studio-git 32.0.2.r1-1 (+53 0.42)\n"
    "    OBS Studio development build\n"
    "custom/obs-plugin 1.0-1\n"
    "    Extra plugin for OBS Studio\n";
bool write(const QString &path, const QByteArray &data, bool executable = false) {
    QFile file(path); if (!file.open(QIODevice::WriteOnly)) return false;
    file.write(data); file.close();
    return !executable || file.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
}
QByteArray read(const QString &path) { QFile file(path); return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray(); }
void answer(QWidget &page, QMessageBox::StandardButton choice) {
    QTimer::singleShot(0, &page, [&page, choice] {
        auto *dialog = page.findChild<QMessageBox *>(); QVERIFY(dialog); dialog->button(choice)->click();
    });
}
}

class AurPageTests final : public QObject {
    Q_OBJECT
    QTemporaryDir files;
    QByteArray oldPath;
    QString path(const QString &name) const { return files.filePath(name); }
    static QPushButton *button(QWidget &page, const char *name) { return page.findChild<QPushButton *>(name); }
    bool helper(const QString &name, double delay = .05, int code = 0) {
        return write(path(name), "#!/usr/bin/python3\nimport json,pathlib,sys,time\n"
            "p=pathlib.Path(__file__).parent\n"
            "with (p/'queries').open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "time.sleep(" + QByteArray::number(delay) + ")\n"
            "print((p/'output').read_text(),end='')\n"
            "sys.exit(" + QByteArray::number(code) + ")\n", true);
    }
private slots:
    void initTestCase() {
        QVERIFY(files.isValid()); qApp->setQuitOnLastWindowClosed(false); qApp->setStyle("Fusion");
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, files.path());
        const auto themePath = qEnvironmentVariable("AUR_PAGE_THEME");
        if (!themePath.isEmpty()) {
            const auto data = QJsonDocument::fromJson(read(themePath)).object(); QPalette palette;
            const auto roles = QMetaEnum::fromType<QPalette::ColorRole>(); const auto colors = data["colors"].toObject();
            for (auto i = colors.begin(); i != colors.end(); ++i) {
                const int role = roles.keyToValue(i.key().toUtf8());
                if (role >= 0) palette.setColor(QPalette::All, QPalette::ColorRole(role), QColor(i.value().toString()));
            }
            qApp->setPalette(palette); qApp->setFont(QFont(data["font"].toString(), 10)); qApp->setStyleSheet(data["stylesheet"].toString());
            QStringList paths; for (const auto &entry : data["iconSearchPaths"].toArray()) paths << entry.toString();
            QIcon::setThemeSearchPaths(paths); QIcon::setThemeName(data["iconTheme"].toString());
        }
    }
    void init() {
        oldPath = qgetenv("PATH"); qputenv("PATH", files.path().toUtf8());
        for (const auto &name : {"yay", "paru", "pacman", "queries", "terminal.json"}) QFile::remove(path(name));
        QVERIFY(write(path("output"), fixture));
        QVERIFY(write(path("terminal"), "#!/usr/bin/python3\nimport json,pathlib,sys\n"
            "(pathlib.Path(__file__).parent/'terminal.json').write_text(json.dumps(sys.argv[1:]))\n", true));
        QVERIFY(QDir().mkpath(path("control_panel")));
        QVERIFY(write(path("control_panel/aur_helper_install.py"), "# fixture only\n"));
    }
    void cleanup() { qputenv("PATH", oldPath); }
    void parserHandlesBothHelpersCustomReposAndInstalledMarkers() {
        const auto values = AurSearch::parse(fixture + "aur/example 1.2-3 (Votes: 123 Popularity: 4.2) [Installed: 1.1-1]\n"
            "    A multi-line\n      description\n"
            "\x1b[32maur/colored\x1b[0m 2.0-1 (Installed)\n    colored app\n"
            "aur/bad;touch 1\n");
        QCOMPARE(values.size(), 5); QCOMPARE(values[1].votes, QString("53"));
        QVERIFY(values[0].votes.isEmpty());
        QVERIFY(values[0].installed); QVERIFY(!values[1].installed);
        QCOMPARE(values[2].repository, QString("custom")); QCOMPARE(values[3].votes, QString("123"));
        QVERIFY(values[3].installed); QVERIFY(values[4].installed);
        QCOMPARE(values[3].description, QString("A multi-line description"));
        QVERIFY(AurSearch::matches(values[0], "OBS-STUDIO", 1, true));
        QVERIFY(!AurSearch::matches(values[1], "obs-studio", 1, true));
        QVERIFY(AurSearch::matches(values[1], "development", 2, false));
    }
    void pageStaysSilentAndSelectsAvailableHelper() {
        AurPage page(files.path(), path("terminal")); page.resize(1100, 700); page.show();
        QVERIFY(!button(page, "aurSearch")->isEnabled()); QVERIFY(page.findChildren<QMessageBox *>().isEmpty());
        for(const auto *name:{"aurInstallYay","aurInstallParu"}){QVERIFY(button(page,name)->isVisible());QVERIFY(button(page,name)->isEnabled());}
        QCOMPARE(button(page,"aurInstallYay")->text(),QString("Install Yay"));QVERIFY(button(page,"aurInstallYay")->property("aurPrimary").toBool());
        QVERIFY(page.findChild<QLabel *>("aurRecommended")->isVisible());
        const auto capture=qEnvironmentVariable("AUR_PAGE_CAPTURE");
        if(!capture.isEmpty()){QDir().mkpath(capture);page.grab().save(capture+"/install-helpers.png");}
        QVERIFY(!QFile::exists(path("queries"))); QVERIFY(helper("paru"));
        button(page, "aurRefresh")->click(); QVERIFY(button(page, "aurSearch")->isEnabled());
        QVERIFY(!button(page,"aurInstallParu")->isEnabled());QCOMPARE(button(page,"aurInstallParu")->text(),QString("Paru installed"));
        QVERIFY(button(page,"aurInstallYay")->isEnabled());
        page.findChild<QLineEdit *>("aurQuery")->setText("obs"); button(page, "aurSearch")->click();
        auto *table = page.findChild<QTableWidget *>("aurResults"); QTRY_COMPARE(table->rowCount(), 3);
        QCOMPARE(QJsonDocument::fromJson(read(path("queries")).trimmed()).array(), QJsonArray({"-Ss", "--color", "never", "--", "obs"}));
        page.findChild<QComboBox *>("aurHelper")->setCurrentIndex(1);
        QVERIFY(!button(page, "aurSearch")->isEnabled()); QVERIFY(!button(page, "aurInstall")->isEnabled());
    }
    void searchRemainsResponsiveRunsOnceAndFiltersWithoutNewRequests() {
        QVERIFY(helper("yay", .2)); AurPage page(files.path(), path("terminal")); page.resize(1100, 700); page.show();
        auto *query = page.findChild<QLineEdit *>("aurQuery"); query->setText("obs-studio");
        QTest::keyClick(query, Qt::Key_Return);
        QCOMPARE(button(page, "aurSearch")->text(), QString("Cancel"));
        QVERIFY(!button(page, "aurInstall")->isEnabled());
        bool responsive = false; QTimer::singleShot(5, &page, [&] { responsive = true; });
        QTRY_VERIFY(responsive);
        auto *table = page.findChild<QTableWidget *>("aurResults"); QTRY_COMPARE(table->rowCount(), 2);
        page.findChild<QComboBox *>("aurMatch")->setCurrentIndex(1); QCOMPARE(table->rowCount(), 1);
        QCOMPARE(read(path("queries")).count('\n'), 1);
        table->selectRow(0); QVERIFY(button(page, "aurRemove")->isEnabled());
        page.findChild<QComboBox *>("aurMatch")->setCurrentIndex(0); table->selectRow(1);
        QVERIFY(button(page, "aurInstall")->isEnabled()); QVERIFY(!button(page, "aurRemove")->isEnabled());
    }
    void cancellationAndFailureNeverLeaveStaleActions() {
        QVERIFY(helper("yay", 5)); AurPage page(files.path(), path("terminal"));
        page.findChild<QLineEdit *>("aurQuery")->setText("obs"); button(page, "aurSearch")->click();
        QTRY_VERIFY(QFile::exists(path("queries"))); button(page, "aurSearch")->click();
        QTRY_COMPARE(button(page, "aurSearch")->text(), QString("Search"));
        QVERIFY(!button(page, "aurInstall")->isEnabled());
        QVERIFY(helper("yay", .02, 2)); button(page, "aurSearch")->click();
        QTRY_COMPARE(button(page, "aurSearch")->text(), QString("Search"));
        QCOMPARE(page.findChild<QTableWidget *>("aurResults")->rowCount(), 0);
        QVERIFY(!button(page, "aurRemove")->isEnabled());
        QVERIFY(!QFile::exists(path("terminal.json")));
    }
    void installUsesSelectedRepositoryAndRequiresConfirmation() {
        QVERIFY(helper("yay")); AurPage page(files.path(), path("terminal"));
        page.findChild<QLineEdit *>("aurQuery")->setText("obs"); button(page, "aurSearch")->click();
        auto *table = page.findChild<QTableWidget *>("aurResults"); QTRY_COMPARE(table->rowCount(), 3); table->selectRow(1);
        answer(page, QMessageBox::No); button(page, "aurInstall")->click();
        QVERIFY(!QFile::exists(path("terminal.json")));
        answer(page, QMessageBox::Yes); button(page, "aurInstall")->click();
        QTRY_VERIFY(QFile::exists(path("terminal.json")));
        const auto args = QJsonDocument::fromJson(read(path("terminal.json"))).array();
        QCOMPARE(args[0].toString(), QString("-e")); QCOMPARE(args[1].toString(), QString("bash"));
        QVERIFY(args.last().toString().contains("'yay' -S -- 'aur/obs-studio-git'"));
        QVERIFY(!args.last().toString().contains("--noconfirm"));
    }
    void helperMenuKeepsBothInstallInOneTerminal() {
        AurPage page(files.path(), path("terminal"));
        answer(page,QMessageBox::No);button(page,"aurInstallYay")->click();QVERIFY(!QFile::exists(path("terminal.json")));
        for(const auto &name:{QString("yay"),QString("paru")}){
            answer(page,QMessageBox::Yes);button(page,name=="yay"?"aurInstallYay":"aurInstallParu")->click();
            QTRY_VERIFY(QFile::exists(path("terminal.json")));
            QCOMPARE(QJsonDocument::fromJson(read(path("terminal.json"))).array(),QJsonArray({"-e","python3",path("control_panel/aur_helper_install.py"),"--wait",name}));
            QVERIFY(QFile::remove(path("terminal.json")));
        }
        auto *menu = page.findChild<QMenu *>("aurHelperMenu");
        QMetaObject::invokeMethod(menu, "aboutToShow");
        QVERIFY(menu->actions().first()->text().contains("both"));
        answer(page, QMessageBox::Yes); menu->actions().first()->trigger();
        QTRY_VERIFY(QFile::exists(path("terminal.json")));
        const auto args = QJsonDocument::fromJson(read(path("terminal.json"))).array();
        QCOMPARE(args, QJsonArray({"-e", "python3", path("control_panel/aur_helper_install.py"), "--wait", "both"}));
    }
    void repositoryBrowserWorksWithoutAurHelpersAndReviewsFullUpgrade() {
        QVERIFY(helper("pacman"));
        QVERIFY(write(path("output"), "extra/obs-studio 32.0.2-1 [installed]\n    Recording software\n"));
        AurPage page(files.path(), path("terminal"), nullptr, AurPage::Mode::Repositories); page.show();
        QVERIFY(button(page,"aurSearch")->isEnabled()); QVERIFY(!page.findChild<QComboBox *>("aurHelper")->isVisible());
        QVERIFY(!page.findChild<QWidget *>("aurHelperChoices")->isVisible());
        QVERIFY(!button(page,"aurRemove")->isVisible());
        page.findChild<QLineEdit *>("aurQuery")->setText("obs"); button(page,"aurSearch")->click();
        auto *table=page.findChild<QTableWidget *>("aurResults"); QTRY_COMPARE(table->rowCount(),1); table->selectRow(0);
        QCOMPARE(QJsonDocument::fromJson(read(path("queries")).trimmed()).array(),QJsonArray({"-Ss","--color","never","--","obs"}));
        answer(page,QMessageBox::No); button(page,"aurInstall")->click(); QVERIFY(!QFile::exists(path("terminal.json")));
        answer(page,QMessageBox::Yes); button(page,"aurInstall")->click(); QTRY_VERIFY(QFile::exists(path("terminal.json")));
        const auto command=QJsonDocument::fromJson(read(path("terminal.json"))).array().last().toString();
        QVERIFY(command.contains("sudo pacman -Syu -- 'extra/obs-studio'")); QVERIFY(!command.contains("--noconfirm"));
    }
    void layoutAndPreview() {
        QVERIFY(helper("yay")); AurPage page(files.path(), path("terminal"));
        page.resize(1360, 780); page.show(); QTest::qWait(40);
        const auto capture = qEnvironmentVariable("AUR_PAGE_CAPTURE");
        if (!capture.isEmpty()) { QDir().mkpath(capture); page.grab().save(capture + "/empty.png"); }
        page.findChild<QLineEdit *>("aurQuery")->setText("obs"); button(page, "aurSearch")->click();
        auto *table = page.findChild<QTableWidget *>("aurResults"); QTRY_COMPARE(table->rowCount(), 3); table->selectRow(0);
        if (!capture.isEmpty()) page.grab().save(capture + "/results.png");
        page.resize(760, 680); QTest::qWait(40); QCOMPARE(page.width(), 760);
        if (!capture.isEmpty()) page.grab().save(capture + "/narrow.png");
    }
};
QTEST_MAIN(AurPageTests)
#include "aur_page_tests.moc"
