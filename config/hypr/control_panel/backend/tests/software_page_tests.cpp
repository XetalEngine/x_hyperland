#include "software_page.h"
#include "software_packages.h"
#include "backend/package_install.h"
#include <QtTest>
#include <QtWidgets>

namespace {
bool write(const QString &path, const QByteArray &data, bool executable = false) {
    QFile f(path); if (!f.open(QIODevice::WriteOnly)) return false; f.write(data); f.close();
    return !executable || f.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
}
QByteArray read(const QString &path) { QFile f(path); return f.open(QIODevice::ReadOnly) ? f.readAll() : QByteArray(); }
template<class T> T *make(QWidget *parent, const char *name) { auto *w = new T(parent); w->setObjectName(name); return w; }
struct Fixture : QWidget {
    SoftwarePage *page;
    Fixture(const QString &root) {
        for (const auto *name : {"uninstallTab", "pacmanDoctorTab"}) new QVBoxLayout(make<QWidget>(this, name));
        for (const auto *name : {"uninstallCountLabel", "uninstallSelectedSizeLabel", "uninstallHelperLabel", "pacDocStatus", "pacDocDiagnosis"}) make<QLabel>(this, name);
        for (const auto *name : {"uninstallButton", "orphanCleanButton", "cacheCleanButton", "pacDocDiagnose", "pacDocMirrors", "pacDocKeys", "pacDocUnlock", "pacDocDowngrade", "pacDocTrim", "pacDocSync", "pacDocMerge", "pacDocOpenNew", "pacDocOpenCurrent", "pacDocApply", "pacDocBackup", "pacDocEdit"}) make<QPushButton>(this, name);
        for (const auto *name : {"uninstallDepsCheckBox", "pacDocColor", "pacDocCandy", "pacDocVerbose", "pacDocCheckSpace", "pacDocTimeout"}) make<QCheckBox>(this, name);
        make<QSpinBox>(this, "pacDocParallel"); make<QListWidget>(this, "pacDocFiles");
        make<QComboBox>(this, "uninstallHelperCombo")->addItems({"pacman", "yay", "paru"});
        make<QComboBox>(this, "uninstallSourceFilter")->addItems({"All", "Repository", "AUR / local"});
        make<QLineEdit>(this, "uninstallSearch");
        auto *table = make<QTableWidget>(this, "uninstallTable"); table->setColumnCount(6);
        table->setSelectionBehavior(QAbstractItemView::SelectRows); table->setSelectionMode(QAbstractItemView::ExtendedSelection);
        page = new SoftwarePage(this, root, root + "/terminal", this);
        auto *layout = new QVBoxLayout(this); layout->addWidget(page); resize(1240, 850); show();
    }
};
const QByteArray packages = "Name : alpha\nVersion : 2\nDescription : A repository package\nInstalled Size : 2 MiB\nInstall Date : Mon Nov  9 15:30:07 2026\n\n"
    "Name : beta\nVersion : 3\nDescription : A local package\nInstalled Size : 40 KiB\nInstall Date : Tue Nov 10 15:30:07 2026\n\n";
}
class SoftwarePageTests : public QObject {
    Q_OBJECT
    QTemporaryDir files;
    QByteArray oldPath;
private slots:
    void initTestCase() { qApp->setQuitOnLastWindowClosed(false); qApp->setStyle("Fusion"); QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, files.path()); }
    void init() {
        QVERIFY(files.isValid()); oldPath = qgetenv("PATH"); qputenv("PATH", files.path().toUtf8());
        QFile::remove(files.filePath("queries")); QFile::remove(files.filePath("fail"));
        QVERIFY(write(files.filePath("output"), packages));
        QVERIFY(write(files.filePath("pacman"), "#!/usr/bin/python3\nimport pathlib,sys,time\np=pathlib.Path(__file__).parent\nwith (p/'queries').open('a') as f: f.write(' '.join(sys.argv[1:])+'\\n')\ntime.sleep(.08)\nif (p/'fail').exists(): print('fixture failure',file=sys.stderr); sys.exit(1)\nprint('beta' if sys.argv[1]=='-Qmq' else (p/'output').read_text())\n", true));
    }
    void cleanup() { qputenv("PATH", oldPath); }
    void installedLoadingFilteringAndFailure() {
        Fixture f(files.path()); QTest::qWait(40); QVERIFY(!QFile::exists(files.filePath("queries")));
        f.page->openSection(1); auto *table = f.findChild<QTableWidget *>("uninstallTable");
        QVERIFY(!table->isEnabled()); bool tick = false; QTimer::singleShot(1, &f, [&] { tick = true; }); QTRY_VERIFY(tick);
        QTRY_COMPARE(table->rowCount(), 2); QTRY_VERIFY(table->isEnabled());
        QCOMPARE(read(files.filePath("queries")), QByteArray("-Qmq\n-Qi\n"));
        table->sortItems(2, Qt::AscendingOrder); QCOMPARE(table->item(0,0)->text(), QString("beta"));
        table->selectRow(0); QVERIFY(!f.findChild<QPushButton *>("softwareReinstall")->isEnabled());
        f.findChild<QLineEdit *>("uninstallSearch")->setText("alpha");
        QVERIFY(table->selectionModel()->selectedRows().isEmpty()); QVERIFY(!f.findChild<QPushButton *>("uninstallButton")->isEnabled());
        table->selectRow(1); QVERIFY(f.findChild<QPushButton *>("softwareReinstall")->isEnabled());
        f.page->refreshInstalled(); QTRY_VERIFY(table->isEnabled()); QCOMPARE(table->selectionModel()->selectedRows().size(), 1);
        QVERIFY(write(files.filePath("fail"), "1")); f.page->refreshInstalled(); QTRY_VERIFY(table->isEnabled());
        QCOMPARE(table->rowCount(), 2); QVERIFY(f.findChild<QLabel *>("uninstallCountLabel")->text().contains("fixture failure"));
    }
    void repairKeepsCallbacksAndConfigurationSelection() {
        Fixture f(files.path()); auto *check = f.findChild<QPushButton *>("pacDocDiagnose"); QSignalSpy checked(check, &QPushButton::clicked);
        f.page->openSection(2); QCOMPARE(checked.count(), 1); check->click(); QCOMPARE(checked.count(), 2);
        auto *original = f.findChild<QPushButton *>("pacDocKeys"); QSignalSpy repair(original, &QPushButton::clicked); original->click(); QCOMPARE(repair.count(), 1);
        QVariantMap result{{"check", "Database lock"}, {"result", "Clear"}, {"severity", 0}, {"advice", "Ready"}};
        f.findChild<QLabel *>("pacDocDiagnosis")->setProperty("softwareDiagnostics", QVariantList{result});
        auto *tree = f.findChild<QTreeWidget *>("softwareDiagnosis"); QCOMPARE(tree->topLevelItem(0)->text(1), QString("Clear"));
        auto *list = f.findChild<QListWidget *>("pacDocFiles"); list->addItem("No configuration files"); list->setCurrentRow(0);
        QVERIFY(!f.findChild<QPushButton *>("pacDocOpenNew")->isEnabled());
        list->clear(); list->addItem("/etc/example.pacnew"); list->setCurrentRow(0);
        QVERIFY(f.findChild<QPushButton *>("pacDocOpenNew")->isEnabled());
        f.resize(780, 700); QTest::qWait(30); QCOMPARE(f.findChild<QScrollArea *>("softwareRepairScroll")->horizontalScrollBar()->maximum(), 0);
    }
    void parsesMetadataAndUsesOneCompleteTransaction() {
        auto values = SoftwarePackages::parse(packages); QCOMPARE(values.size(), 2); QCOMPARE(values[0].bytes, qint64(2097152));
        QCOMPARE(SoftwarePackages::sizeBytes("bad"), qint64(0)); QCOMPARE(SoftwarePackages::sizeBytes("-1 MiB"), qint64(0));
        const auto command = PackageInstall::script("pacman", "Pacman", "alpha", false);
        QVERIFY(command.contains("pacman -Syu --")); QVERIFY(!command.contains("pacman -Sy &&"));
    }
};
QTEST_MAIN(SoftwarePageTests)
#include "software_page_tests.moc"
