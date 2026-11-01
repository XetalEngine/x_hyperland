#include "../control_panel/backend/volume_commands.h"
#include "window.h"
#include <KIO/RenameDialog>
#include <KIO/RenameFileDialog>
#include <KUrlComboBox>
#include <QtTest>

class FileTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  QString folder;
  static void write(const QString &path,
                    const QByteArray &bytes = "fixture data\n") {
    QFile file(path);
    QVERIFY(file.open(QIODevice::WriteOnly));
    QCOMPARE(file.write(bytes), bytes.size());
  }
  static void focus(Browser *tab) {
    tab->window()->activateWindow();
    tab->view()->setFocus();
    QTest::qWait(40);
  }
private slots:
  void initTestCase() {
    QVERIFY(temporary.isValid());
    folder = temporary.path() + "/files";
    QVERIFY(QDir().mkpath(folder));
    qApp->setQuitOnLastWindowClosed(false);
  }
  void pathsPreserveLiteralCharacters() {
    const QString path = folder + "/deep path/# 100% café %u.txt";
    QCOMPARE(Fusion::displayPath(Fusion::userUrl(path)), path);
    QCOMPARE(Fusion::userUrl("../next", QUrl::fromLocalFile(folder + "/child"))
                 .adjusted(QUrl::NormalizePathSegments),
             QUrl::fromLocalFile(folder + "/next"));
    QCOMPARE(Fusion::userUrl("~/Documents").toLocalFile(),
             QDir::homePath() + "/Documents");
    QVERIFY(Fusion::isComputer(Fusion::userUrl("This PC")));
    QCOMPARE(Fusion::userUrl("smb://server/share/deep%20folder").path(),
             QString("/share/deep folder"));
    QVERIFY(!Fusion::validName("../outside"));
    QVERIFY(!Fusion::validName(".."));
    QVERIFY(Fusion::validName("100% # résumé.txt"));
  }
  void customCommandsKeepFilenamesAsArguments() {
    const QString name = folder + "/a;$(touch sentinel) 'quote' %u.txt";
    const auto urls = QList<QUrl>{QUrl::fromLocalFile(name),
                                  QUrl::fromLocalFile(folder + "/second file")};
    QCOMPARE(Fusion::expandCommand("viewer -- %F", urls),
             QStringList({"viewer", "--", name, folder + "/second file"}));
    QCOMPARE(Fusion::expandCommand("viewer %f", urls),
             QStringList({"viewer", name}));
    QVERIFY(Fusion::expandCommand("viewer --files=%F", urls).isEmpty());
    QVERIFY(
        Fusion::expandCommand("viewer %F", {QUrl("smb://server/share/file")})
            .isEmpty());
  }
  void drivesIncludeUnmountedAndPreserveMountPaths() {
    const QByteArray json =
        R"({"blockdevices":[{"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","size":10000,"children":[{"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","fstype":"ext4","label":"System","uuid":"aaa","size":4000,"mountpoints":["/"]},{"name":"nvme0n1p2","path":"/dev/nvme0n1p2","type":"part","fstype":"ntfs","label":"Windows","size":6000,"mountpoints":[null]}]},{"name":"sdb1","path":"/dev/sdb1","type":"part","fstype":"exfat","label":"USB","size":500,"rm":true,"mountpoints":["/run/media/fixture/My USB"]},{"name":"loop0","type":"loop","fstype":"squashfs","size":2}]})";
    const auto volumes = Drives::parse(json);
    QCOMPARE(volumes.size(), 3);
    QCOMPARE(volumes[0].mount, QString("/"));
    auto windows =
        std::find_if(volumes.begin(), volumes.end(),
                     [](const Volume &v) { return v.name == "Windows"; });
    QVERIFY(windows != volumes.end());
    QVERIFY(!windows->mounted());
    QVERIFY(windows->mountable());
    auto usb = std::find_if(volumes.begin(), volumes.end(),
                            [](const Volume &v) { return v.name == "USB"; });
    QVERIFY(usb != volumes.end());
    QVERIFY(usb->removable);
    QCOMPARE(usb->mount, QString("/run/media/fixture/My USB"));
    QCOMPARE(FusionVolumes::mount("/dev/sdb1", true),
             QStringList({"mount", "-b", "/dev/sdb1", "-o", "force"}));
    const auto encrypted = Drives::parse(
        R"({"blockdevices":[{"name":"sdc1","type":"part","fstype":"BitLocker","mountpoints":[null]},{"name":"sdd1","type":"part","fstype":"crypto_LUKS","mountpoints":[null]}]})");
    QCOMPARE(encrypted.size(), 2);
    for (const auto &volume : encrypted) {
      QVERIFY(volume.locked());
      QVERIFY(!volume.mountable());
    }
  }
  void privatePreferencesRoundTrip() {
    const QString path = temporary.path() + "/prefs/settings.ini";
    Fusion::Preferences settings(path);
    auto bookmarks = settings.places();
    QVERIFY(!bookmarks.isEmpty());
    bookmarks.append({{"name", "Private shortcut"},
                      {"url", QUrl::fromLocalFile(folder).toString()},
                      {"icon", "folder"}});
    settings.setPlaces(bookmarks);
    auto menu = settings.menu();
    menu[0]["enabled"] = false;
    settings.setMenu(menu);
    Fusion::Preferences restored(path);
    QCOMPARE(restored.places(), bookmarks);
    QCOMPARE(restored.menu(), menu);
  }
  void keyboardAndOperations() {
    const QString source = folder + "/source", dest = folder + "/destination",
                  deep = folder + "/a folder/#percent%/leaf";
    QDir().mkpath(source);
    QDir().mkpath(dest);
    QDir().mkpath(deep);
    const QString original = source + "/original.txt",
                  renamed = source + "/renamed # 100%.txt";
    write(original);
    FilesWindow window(QUrl::fromLocalFile(source), false,
                       temporary.path() + "/ui.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 1, 10000);
    tab->selectUrl(QUrl::fromLocalFile(original));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_F2);
    QTRY_VERIFY(window.findChild<KIO::RenameFileDialog *>());
    auto *rename = window.findChild<KIO::RenameFileDialog *>();
    auto *edit = rename->findChild<QLineEdit *>();
    QVERIFY(edit);
    edit->setText(QFileInfo(renamed).fileName());
    QTest::keyClick(edit, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(renamed), 10000);
    QVERIFY(!QFileInfo::exists(original));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(renamed)).isValid(), 10000);
    tab->selectUrl(QUrl::fromLocalFile(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(),
             QList<QUrl>{QUrl::fromLocalFile(renamed)});
    window.openLocation(QUrl::fromLocalFile(dest));
    QTRY_COMPARE(tab->location(), QUrl::fromLocalFile(dest));
    focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    const QString copy = dest + "/renamed # 100%.txt";
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(copy), 10000);
    QVERIFY(QFileInfo::exists(renamed));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(copy)).isValid(), 10000);
    tab->selectUrl(QUrl::fromLocalFile(copy));
    focus(tab);
    QCOMPARE(tab->selectedUrls(), QList<QUrl>{QUrl::fromLocalFile(copy)});
    QSignalSpy trashKey(window.findChild<QAction *>("trash"),
                        &QAction::triggered);
    QTest::keyClick(tab->view(), Qt::Key_Delete);
    QCOMPARE(trashKey.count(), 1);
    QTRY_VERIFY_WITH_TIMEOUT(!QFileInfo::exists(copy), 10000);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Z, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(copy), 10000);
    window.openLocation(QUrl::fromLocalFile(source));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(renamed)).isValid(), 10000);
    tab->selectUrl(QUrl::fromLocalFile(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    window.openLocation(QUrl::fromLocalFile(deep));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(deep + "/renamed # 100%.txt"),
                             10000);
    QVERIFY(!QFileInfo::exists(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_L, Qt::ControlModifier);
    QVERIFY(tab->navigator->isUrlEditable());
    auto *address = tab->navigator->editor()->lineEdit();
    QVERIFY(address->hasFocus());
    QCOMPARE(address->selectedText(), deep);
    QTest::keyClick(address, Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->text(), deep);
    address->setText(source);
    QTest::keyClick(address, Qt::Key_Return);
    QTRY_COMPARE(tab->location().adjusted(QUrl::StripTrailingSlash),
                 QUrl::fromLocalFile(source));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Left, Qt::AltModifier);
    QTRY_COMPARE(tab->location().adjusted(QUrl::StripTrailingSlash),
                 QUrl::fromLocalFile(deep));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_T, Qt::ControlModifier);
    QCOMPARE(window.findChild<QTabWidget *>()->count(), 2);
    QTest::keyClick(window.browser()->cards, Qt::Key_W, Qt::ControlModifier);
    QCOMPARE(window.findChild<QTabWidget *>()->count(), 1);
    QVERIFY(finished.count() >= 3);
    window.close();
  }
  void cancelledConflictKeepsBothFiles() {
    const QString a = folder + "/conflict-a", b = folder + "/conflict-b";
    QDir().mkpath(a);
    QDir().mkpath(b);
    write(a + "/same.txt", "original source");
    write(b + "/same.txt", "original destination");
    FilesWindow window(QUrl::fromLocalFile(a), false,
                       temporary.path() + "/conflict.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 1, 10000);
    tab->selectUrl(QUrl::fromLocalFile(a + "/same.txt"));
    focus(tab);
    window.runAction("cut");
    window.openLocation(QUrl::fromLocalFile(b));
    focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    window.runAction("paste");
    KIO::RenameDialog *conflict = nullptr;
    QTRY_VERIFY_WITH_TIMEOUT(
        ([&] {
          for (auto *widget : QApplication::topLevelWidgets())
            if ((conflict = qobject_cast<KIO::RenameDialog *>(widget)))
              return true;
          return false;
        })(),
        10000);
    conflict->reject();
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 10000);
    QFile source(a + "/same.txt"), dest(b + "/same.txt");
    QVERIFY(source.open(QIODevice::ReadOnly));
    QVERIFY(dest.open(QIODevice::ReadOnly));
    QCOMPARE(source.readAll(), QByteArray("original source"));
    QCOMPARE(dest.readAll(), QByteArray("original destination"));
    window.close();
  }
  void newFolderAndPermanentDeleteCancellation() {
    const QString base = folder + "/new-folder-test";
    QDir().mkpath(base);
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/new-folder.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    focus(tab);
    QTimer::singleShot(30, [] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QInputDialog *>(widget)) {
          dialog->setTextValue("New # folder");
          dialog->accept();
        }
    });
    QTest::keyClick(tab->view(), Qt::Key_N,
                    Qt::ControlModifier | Qt::ShiftModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo(base + "/New # folder").isDir(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(base + "/New # folder"))
            .isValid(),
        10000);
    tab->selectUrl(QUrl::fromLocalFile(base + "/New # folder"));
    focus(tab);
    QTimer::singleShot(30, [] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QMessageBox *>(widget))
          dialog->reject();
    });
    QTest::keyClick(tab->view(), Qt::Key_Delete, Qt::ShiftModifier);
    QVERIFY(QFileInfo(base + "/New # folder").isDir());
    window.close();
  }
  void mountArgumentsUseMockToolsOnly() {
    const QString tools = temporary.path() + "/mock-tools",
                  log = temporary.path() + "/mount-args.json";
    QDir().mkpath(tools);
    write(tools + "/udisksctl", "#!/usr/bin/python3\nimport os,sys,json\nwith "
                                "open(os.environ['FUSION_TEST_DRIVE_LOG'],'w') "
                                "as f: json.dump(sys.argv[1:],f)\n");
    write(tools + "/lsblk", "#!/usr/bin/python3\nimport "
                            "os\nprint(os.environ['FUSION_TEST_LSBLK'])\n");
    QFile::setPermissions(tools + "/udisksctl", QFileDevice::ReadOwner |
                                                    QFileDevice::WriteOwner |
                                                    QFileDevice::ExeOwner);
    QFile::setPermissions(tools + "/lsblk", QFileDevice::ReadOwner |
                                                QFileDevice::WriteOwner |
                                                QFileDevice::ExeOwner);
    const auto oldPath = qgetenv("PATH");
    const auto cleanup = qScopeGuard([&] {
      qputenv("PATH", oldPath);
      qunsetenv("FUSION_TEST_DRIVE_LOG");
      qunsetenv("FUSION_TEST_LSBLK");
    });
    qputenv("PATH", tools.toUtf8());
    qputenv("FUSION_TEST_DRIVE_LOG", log.toUtf8());
    qputenv(
        "FUSION_TEST_LSBLK",
        R"({"blockdevices":[{"name":"fixture","path":"/dev/fusion-test-only","type":"part","fstype":"ext4","uuid":"fixture","size":100,"mountpoints":[null]}]})");
    Drives drives;
    QTRY_COMPARE_WITH_TIMEOUT(drives.volumes.size(), 1, 5000);
    QVERIFY(!QFileInfo::exists(log));
    drives.operate(drives.volumes.first(), "mount", nullptr);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 5000);
    QTRY_VERIFY(!drives.busy());
    QFile args(log);
    QVERIFY(args.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(args.readAll()).array(),
             QJsonArray({"mount", "-b", "/dev/fusion-test-only"}));
  }
  void viewsAndScreenshots() {
    const QString sample = folder + "/preview";
    QDir().mkpath(sample + "/Projects");
    QDir().mkpath(sample + "/Documents");
    QDir().mkpath(sample + "/Wallpapers");
    write(sample + "/Welcome.txt",
          "Welcome to Fusion Files.\nYour files, your desktop.\n");
    write(sample + "/Notes.md", "# Ideas\nKeep the desktop simple.\n");
    QImage art(800, 500, QImage::Format_RGB32);
    QPainter painter(&art);
    QLinearGradient gradient(0, 0, 800, 500);
    gradient.setColorAt(0, QColor("#212344"));
    gradient.setColorAt(1, QColor("#ed5f79"));
    painter.fillRect(art.rect(), gradient);
    painter.end();
    art.save(sample + "/Sunset.png");
    const QString settings = temporary.path() + "/views.ini";
    FilesWindow window(QUrl::fromLocalFile(sample), false, settings);
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 6, 10000);
    for (int mode = 0; mode < 5; ++mode) {
      tab->setView(mode);
      QCOMPARE(tab->selectedUrls().size(), 0);
      QVERIFY(tab->view()->isVisible());
    }
    tab->details->setColumnHidden(KDirModel::Owner, false);
    tab->details->setColumnHidden(KDirModel::ModifiedTime, true);
    tab->saveView();
    window.preferences.settings.sync();
    Fusion::Preferences restored(settings);
    Browser another(&restored, window.drives);
    QVERIFY(!another.details->isColumnHidden(KDirModel::Owner));
    QVERIFY(another.details->isColumnHidden(KDirModel::ModifiedTime));
    const QString capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) {
      tab->setView(2);
      tab->selectUrl(QUrl::fromLocalFile(sample + "/Sunset.png"));
      window.runAction("preview");
      QTest::qWait(700);
      QVERIFY(window.grab().save(capture + "-folder.png"));
      window.openLocation(Fusion::computerUrl());
      window.drives->volumes = {
          {"/dev/fixture1", "Linux system", "ext4", "/", "part", "one",
           512000000000ULL, 186000000000ULL, 512000000000ULL, false, false},
          {"/dev/fixture2", "Projects", "ext4", "/media/Projects", "part",
           "two", 1000000000000ULL, 740000000000ULL, 1000000000000ULL, false,
           false},
          {"/dev/fixture3", "Windows", "ntfs", "", "part", "three",
           512000000000ULL, 0, 0, false, false},
          {"/dev/fixture4", "USB drive", "exfat", "", "part", "four",
           64000000000ULL, 0, 0, true, false}};
      emit window.drives->changed();
      window.runAction("preview");
      QTest::qWait(150);
      QVERIFY(window.grab().save(capture + "-computer.png"));
    }
    window.close();
  }
};
QTEST_MAIN(FileTests)
#include "tests.moc"
