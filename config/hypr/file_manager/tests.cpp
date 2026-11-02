#include "../control_panel/backend/volume_commands.h"
#include "drive_properties.h"
#include "window.h"
#include "applications.h"
#include "removal.h"
#include "transfers.h"
#include <KIO/FileUndoManager>
#include <KApplicationTrader>
#include <KIO/RenameDialog>
#include <KIO/Paste>
#include <KIO/RenameFileDialog>
#include <KIO/StatJob>
#include <KUrlComboBox>
#include <QDBusConnection>
#include <QScopeGuard>
#include <QStorageInfo>
#include <QtTest>
#include <sys/stat.h>
#include <unistd.h>

class TestFileManager : public QObject {
  Q_OBJECT
  Q_CLASSINFO("D-Bus Interface", "org.freedesktop.FileManager1")
public slots:
  void ShowItems(const QStringList &, const QString &) {}
  void ShowFolders(const QStringList &, const QString &) {}
};

class FileTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  QString folder;
  TestFileManager fileManager;
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
  static void clickFile(Browser *tab, const QUrl &url,
                        Qt::KeyboardModifiers modifiers = Qt::NoModifier) {
    const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(url));
    QVERIFY(index.isValid());
    tab->view()->scrollTo(index);
    QTRY_VERIFY(tab->view()->visualRect(index).isValid());
    QTest::mouseClick(tab->view()->viewport(), Qt::LeftButton, modifiers,
                      tab->view()->visualRect(index).center());
  }
  static QList<Volume> computerVolumes() {
    auto volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/fusion-a","name":"fusion-a","type":"disk","model":"Fusion NVMe","tran":"nvme","size":1000000000000,"children":[
        {"path":"/dev/fusion-a1","type":"part","fstype":"vfat","label":"EFI","size":512000000,"mountpoints":["/boot/efi"]},
        {"path":"/dev/fusion-a2","type":"part","fstype":"ext4","label":"Linux system","size":512000000000,"mountpoints":["/"]},
        {"path":"/dev/fusion-a3","type":"part","fstype":"ntfs","label":"Windows","size":480000000000,"mountpoints":[null]}]},
      {"path":"/dev/fusion-b","name":"fusion-b","type":"disk","model":"Project SSD","tran":"sata","size":2000000000000,"children":[
        {"path":"/dev/fusion-b1","type":"part","fstype":"ext4","label":"Projects","size":2000000000000,"mountpoints":["/media/Projects"]}]},
      {"path":"/dev/fusion-c","name":"fusion-c","type":"disk","model":"Portable SSD","tran":"usb","rm":false,"size":64000000000,"children":[
        {"path":"/dev/fusion-c1","type":"part","fstype":"exfat","label":"USB files","size":32000000000,"mountpoints":["/media/USB"]},
        {"path":"/dev/fusion-c2","type":"part","fstype":"exfat","label":"USB backup","size":32000000000,"mountpoints":[null]}]}
    ]})");
    for (auto &volume : volumes)
      if (volume.mounted()) {
        volume.total = volume.size;
        volume.available = volume.total * 63 / 100;
        volume.freeBytes = volume.available;
        volume.spaceKnown = true;
      }
    return volumes;
  }
private slots:
  void initTestCase() {
    QVERIFY(temporary.isValid());
    folder = temporary.path() + "/files";
    QVERIFY(QDir().mkpath(folder));
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setDesktopFileName("xetal-files");
    auto bus = QDBusConnection::sessionBus();
    QVERIFY(bus.registerService("org.freedesktop.FileManager1"));
    QVERIFY(bus.registerObject("/org/freedesktop/FileManager1", &fileManager,
                               QDBusConnection::ExportAllSlots));
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
  void transferAccessUsesOnlyNecessaryPrivileges() {
    if (geteuid() == 0) QSKIP("Permission routing is checked as the desktop user.");
    const auto base = folder + "/access";
    QDir().mkpath(base + "/source/nested");
    QDir().mkpath(base + "/destination");
    const auto file = base + "/source/nested/protected # 100%.txt";
    write(file);
    const auto source = QUrl::fromLocalFile(base + "/source");
    const auto destination = QUrl::fromLocalFile(base + "/destination");
    const auto cancelled = std::make_shared<std::atomic_bool>(false);
    auto plan = [&](QList<QUrl> items, Fusion::TransferOperation operation) {
      return Fusion::transferAccess(items, destination, operation, cancelled);
    };
    const auto restore = qScopeGuard([&] {
      ::chmod(QFile::encodeName(file), 0600);
      ::chmod(QFile::encodeName(base + "/source"), 0700);
      ::chmod(QFile::encodeName(base + "/destination"), 0700);
    });
    QVERIFY(!plan({source}, Fusion::TransferOperation::Copy).administrator);
    QCOMPARE(::chmod(QFile::encodeName(file), 0000), 0);
    auto copy = plan({source}, Fusion::TransferOperation::Copy);
    QVERIFY(copy.administrator);
    QCOMPARE(copy.sources.first().scheme(), "admin");
    QCOMPARE(copy.destination, destination); // Normal destination stays user-owned.
    QVERIFY(!plan({source}, Fusion::TransferOperation::Move).administrator); // Atomic rename.
    const auto link = base + "/link";
    QVERIFY(QFile::link(file, link));
    QVERIFY(!plan({QUrl::fromLocalFile(link)}, Fusion::TransferOperation::Copy).administrator);
    QCOMPARE(::chmod(QFile::encodeName(base + "/source"), 0500), 0);
    const auto moved = plan({QUrl::fromLocalFile(base + "/source/nested")}, Fusion::TransferOperation::Move);
    QVERIFY(moved.administrator);
    QCOMPARE(moved.destination.scheme(), "admin");
    QCOMPARE(::chmod(QFile::encodeName(base + "/destination"), 0500), 0);
    copy = plan({QUrl::fromLocalFile(link)}, Fusion::TransferOperation::Copy);
    QVERIFY(copy.administrator);
    QCOMPARE(copy.destination.scheme(), "admin");
    QCOMPARE(copy.sources.first().scheme(), "file");
  }
  void droppedFilesShareNumberedCopyAndMoveBehavior() {
    const auto base = folder + "/dropped";
    QDir().mkpath(base + "/source"); QDir().mkpath(base + "/target");
    write(base + "/source/item.txt", "source");
    write(base + "/target/item.txt", "existing");
    QMimeData mime;
    mime.setUrls({QUrl::fromLocalFile(base + "/source/item.txt")});
    QWidget window;
    for (auto modifier : {Qt::ControlModifier, Qt::ShiftModifier}) {
      QDropEvent event(QPointF(1, 1), Qt::CopyAction | Qt::MoveAction, &mime, Qt::LeftButton, modifier);
      auto *job = Fusion::dropFiles(&event, QUrl::fromLocalFile(base + "/target"), &window, QPoint());
      int error = -1;
      connect(job, &KJob::result, &window, [&](KJob *result) { error = result->error(); });
      QTRY_COMPARE_WITH_TIMEOUT(error, 0, 10000);
    }
    QVERIFY(!QFileInfo::exists(base + "/source/item.txt"));
    for (const auto &name : {"item_copy1.txt", "item_copy2.txt"}) {
      QFile file(base + "/target/" + name); QVERIFY(file.open(QIODevice::ReadOnly));
      QCOMPARE(file.readAll(), QByteArray("source"));
    }
  }
  void cancelTransferBeforeStartingChangesNothing() {
    const auto base = folder + "/cancel-before-start";
    QDir().mkpath(base + "/target"); write(base + "/file", "untouched");
    auto *job = Fusion::transferFiles({QUrl::fromLocalFile(base + "/file")},
        QUrl::fromLocalFile(base + "/target"), Fusion::TransferOperation::Move, nullptr);
    QVERIFY(job->kill());
    QTest::qWait(80);
    QVERIFY(QFileInfo::exists(base + "/file"));
    QVERIFY(!QFileInfo::exists(base + "/target/file"));
  }
  void administratorTransfers() {
    if (geteuid() != 0 || !qEnvironmentVariableIsSet("FUSION_FILES_ADMIN_CHECK"))
      QSKIP("Explicit root-fixture check, using the installed admin worker on a private session bus.");
    // Only the QTemporaryDir owned by this test is touched. No policy rules,
    // desktop preferences, or real protected user files are changed.
    const auto base = folder + "/administrator";
    QDir().mkpath(base + "/source/private"); QDir().mkpath(base + "/target");
    write(base + "/source/private/item # 100%.txt", "protected content");
    ::chmod(QFile::encodeName(base + "/source/private"), 0700);
    auto admin = [](const QString &path) { auto url = QUrl::fromLocalFile(path); url.setScheme("admin"); return url; };
    QWidget window;
    for (int n = 0; n < 2; ++n) {
      auto *job = Fusion::transferFiles({admin(base + "/source/private")}, QUrl::fromLocalFile(base + "/target"),
          Fusion::TransferOperation::Copy, &window);
      int error = -1; QString message;
      connect(job, &KJob::result, &window, [&](KJob *result) { error = result->error(); message = result->errorString(); });
      QTRY_VERIFY_WITH_TIMEOUT(error != -1, 15000);
      QVERIFY2(!error, qPrintable(message));
    }
    QFile copied(base + "/target/private_copy1/item # 100%.txt");
    QVERIFY(copied.open(QIODevice::ReadOnly)); QCOMPARE(copied.readAll(), QByteArray("protected content")); copied.close();
    write(base + "/source/move.txt", "move this"); write(base + "/target/move.txt", "keep this");
    auto *mime = new QMimeData; mime->setUrls({QUrl::fromLocalFile(base + "/source/move.txt")});
    KIO::setClipboardDataCut(mime, true); QApplication::clipboard()->setMimeData(mime);
    auto *move = Fusion::pasteFiles(admin(base + "/target"), &window);
    int error = -1; QString message;
    connect(move, &KJob::result, &window, [&](KJob *result) { error = result->error(); message = result->errorString(); });
    QTRY_VERIFY_WITH_TIMEOUT(error != -1, 15000);
    QVERIFY2(!error, qPrintable(message));
    QVERIFY(!QFileInfo::exists(base + "/source/move.txt"));
    QVERIFY(QFileInfo::exists(base + "/target/move_copy1.txt"));
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(base + "/target/move_copy1.txt")});
    QVERIFY(!KIO::isClipboardDataCut(QApplication::clipboard()->mimeData()));
    KIO::FileUndoManager::self()->undo();
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(base + "/source/move.txt"), 15000);
    QVERIFY(!QFileInfo::exists(base + "/target/move_copy1.txt"));
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
  void physicalDriveAncestry() {
    const auto volumes = computerVolumes();
    QCOMPARE(volumes.size(), 6);
    for (const auto &volume : volumes) {
      QVERIFY(!volume.driveKey().isEmpty());
      if (volume.device.startsWith("/dev/fusion-a")) {
        QCOMPARE(volume.driveKey(), QString("/dev/fusion-a"));
        QCOMPARE(volume.driveModel, QString("Fusion NVMe"));
        QCOMPARE(volume.driveSize, 1000000000000ULL);
      }
      if (volume.device == "/dev/fusion-c1") {
        QVERIFY(volume.usb());
        QVERIFY(!volume.removable);
        QCOMPARE(volume.transport, QString("usb"));
      }
    }
    const auto shared = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/a","type":"disk","children":[{"path":"/dev/md0","type":"raid1","fstype":"ext4","mountpoints":["/mnt/data"]}]},
      {"path":"/dev/b","type":"disk","children":[{"path":"/dev/md0","type":"raid1","fstype":"ext4","mountpoints":["/mnt/data"]}]}
    ]})");
    QCOMPARE(shared.size(), 1);
    QCOMPARE(shared.first().driveKey(), QString("/dev/md0"));
    QCOMPARE(shared.first().driveModel, QString("Multiple backing disks"));
  }
  void mountedRowsSidebarAndSplitter() {
    FilesWindow window(Fusion::computerUrl(), false,
                       temporary.path() + "/drive-layout.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.resize(1000, 900);
    window.show();
    window.drives->volumes = computerVolumes();
    emit window.drives->changed();
    auto *tab = window.browser();
    auto group = [tab](const QString &key) -> QWidget * {
      for (auto *widget : tab->findChildren<QWidget *>("mountedDiskGroup"))
        if (widget->property("driveKey").toString() == key)
          return widget;
      return nullptr;
    };
    QTRY_VERIFY(group("/dev/fusion-a"));
    QCOMPARE(tab->findChildren<QWidget *>("mountedDiskGroup").size(), 2);
    auto *row = group("/dev/fusion-a")->findChild<QListWidget *>();
    QCOMPARE(row->count(), 2);
    QVERIFY(!row->isWrapping());
    QCOMPARE(tab->cards->count(), 1);
    QCOMPARE(tab->usbCards->count(), 2);
    for (int i = 0; i < tab->cards->count(); ++i)
      QVERIFY(
          !tab->cards->item(i)->data(Qt::UserRole).value<Volume>().mounted());
    auto *places = window.findChild<QTreeWidget *>("places");
    auto sidebar = [places](const QString &name) -> QTreeWidgetItem * {
      for (int i = 0; i < places->topLevelItemCount(); ++i)
        if (places->topLevelItem(i)->text(0) == name)
          return places->topLevelItem(i);
      return nullptr;
    };
    QVERIFY(sidebar("This PC"));
    QCOMPARE(sidebar("This PC")->childCount(), 4);
    QVERIFY(sidebar("Unmounted drives"));
    QCOMPARE(sidebar("Unmounted drives")->childCount(), 2);
    QVERIFY(sidebar("Unmounted drives")->isExpanded());
    QVERIFY(places->indexOfTopLevelItem(sidebar("Unmounted drives")) >
            places->indexOfTopLevelItem(sidebar("Trash")));
    sidebar("Unmounted drives")->setExpanded(false);
    row->setCurrentRow(0);
    row->setFocus();
    const auto selected = tab->selectedVolume().device;
    emit window.drives->changed();
    QCOMPARE(group("/dev/fusion-a")->findChild<QListWidget *>(), row);
    QCOMPARE(tab->selectedVolume().device, selected);
    QVERIFY(!sidebar("Unmounted drives")->isExpanded());
    auto *splitter = tab->findChild<QSplitter *>("driveSections");
    QCOMPARE(splitter->orientation(), Qt::Vertical);
    QTest::qWait(100);
    auto *handle = splitter->handle(1);
    const auto middle = handle->rect().center();
    QTest::mousePress(handle, Qt::LeftButton, Qt::NoModifier, middle);
    QTest::mouseMove(handle, middle + QPoint(0, 35), 20);
    QTest::mouseRelease(handle, Qt::LeftButton, Qt::NoModifier,
                        middle + QPoint(0, 35));
    QVERIFY(!window.preferences.settings.value("computerSections")
                 .toByteArray()
                 .isEmpty());
    const auto sizes = splitter->sizes();
    emit window.drives->changed();
    QCOMPARE(splitter->sizes(), sizes);
    window.resize(800, 900);
    QTRY_VERIFY(row->horizontalScrollBar()->maximum() > 0);
    QCOMPARE(row->visualItemRect(row->item(0)).y(),
             row->visualItemRect(row->item(1)).y());
    row->horizontalScrollBar()->setValue(80);
    emit window.drives->changed();
    QTest::qWait(30);
    QCOMPARE(row->horizontalScrollBar()->value(), 80);
    window.activateWindow();
    row->setFocus();
    QTest::keyClick(row, Qt::Key_Return, Qt::AltModifier);
    QTRY_VERIFY(window.findChild<DriveProperties *>());
    auto *properties = window.findChild<DriveProperties *>();
    QCOMPARE(properties->findChild<QLabel *>("volumeDevice")->text(), selected);
    properties->close();
    QTRY_VERIFY(!window.findChild<DriveProperties *>());
    places->setCurrentItem(sidebar("This PC")->child(0));
    window.activateWindow();
    places->setFocus();
    QTRY_VERIFY(window.isActiveWindow());
    QTRY_VERIFY(places->hasFocus());
    QTest::keyClick(places, Qt::Key_Return, Qt::AltModifier);
    QTRY_VERIFY(window.findChild<DriveProperties *>());
    window.findChild<DriveProperties *>()->close();
    QTRY_VERIFY(!window.findChild<DriveProperties *>());
    for (auto &volume : window.drives->volumes)
      if (volume.device == "/dev/fusion-a3")
        volume.mount = "/media/Windows";
    emit window.drives->changed();
    QCOMPARE(row->count(), 3);
    QCOMPARE(tab->cards->count(), 0);
    QCOMPARE(sidebar("This PC")->childCount(), 5);
    for (auto &volume : window.drives->volumes)
      if (volume.driveKey() == "/dev/fusion-a")
        volume.mount.clear();
    emit window.drives->changed();
    QVERIFY(!group("/dev/fusion-a"));
    QCOMPARE(tab->cards->count(), 3);
    QCOMPARE(sidebar("This PC")->childCount(), 2);
    window.drives->volumes.clear();
    emit window.drives->changed();
    QCOMPARE(tab->findChildren<QWidget *>("mountedDiskGroup").size(), 0);
    QCOMPARE(tab->cards->count(), 0);
    QCOMPARE(tab->usbCards->count(), 0);
    QVERIFY(!sidebar("Unmounted drives"));
    window.close();
  }
  void sidebarExpansionSurvivesReopenAndReconnect() {
    const auto settings = temporary.path() + "/sidebar.ini";
    const QStringList names{"This PC", "Quick access", "Unmounted drives"};
    auto sections = [](FilesWindow &window) {
      QMap<QString, QTreeWidgetItem *> result;
      auto *tree = window.findChild<QTreeWidget *>("places");
      for (int i = 0; i < tree->topLevelItemCount(); ++i)
        result.insert(tree->topLevelItem(i)->text(0), tree->topLevelItem(i));
      return result;
    };
    {
      FilesWindow window(Fusion::computerUrl(), false, settings);
      window.setAttribute(Qt::WA_DeleteOnClose, false);
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      for (const auto &name : names) {
        QVERIFY(sections(window).value(name));
        QVERIFY(sections(window).value(name)->isExpanded());
        sections(window).value(name)->setExpanded(false);
      }
      window.drives->volumes.clear();
      emit window.drives->changed();
      QVERIFY(!sections(window).contains("Unmounted drives"));
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      for (const auto &name : names)
        QVERIFY(!sections(window).value(name)->isExpanded());
      window.close();
    }
    {
      FilesWindow reopened(Fusion::computerUrl(), false, settings);
      reopened.setAttribute(Qt::WA_DeleteOnClose, false);
      reopened.drives->volumes = computerVolumes();
      emit reopened.drives->changed();
      for (const auto &name : names)
        QVERIFY(!sections(reopened).value(name)->isExpanded());
      sections(reopened).value("Quick access")->setExpanded(true);
      reopened.close();
    }
    FilesWindow reopened(Fusion::computerUrl(), false, settings);
    reopened.drives->volumes = computerVolumes();
    emit reopened.drives->changed();
    QVERIFY(sections(reopened).value("Quick access")->isExpanded());
    QVERIFY(!sections(reopened).value("This PC")->isExpanded());
    QVERIFY(!sections(reopened).value("Unmounted drives")->isExpanded());
  }
  void propertiesOpenSystemCleaner() {
    const auto originalRoot = qgetenv("XETAL_FILES_ROOT");
    const auto result = temporary.path() + "/cleaner-arguments";
    const auto root = temporary.path() + "/cleaner-profile";
    QVERIFY(QDir().mkpath(root + "/scripts"));
    const auto script = root + "/scripts/control-panel.sh";
    write(
        script,
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FUSION_CLEANER_TEST_RESULT\"\n");
    QVERIFY(QFile::setPermissions(script, QFile::ReadOwner | QFile::WriteOwner |
                                              QFile::ExeOwner));
    const auto restore = qScopeGuard([&] {
      qputenv("XETAL_FILES_ROOT", originalRoot);
      qunsetenv("FUSION_CLEANER_TEST_RESULT");
    });
    qputenv("FUSION_CLEANER_TEST_RESULT", result.toUtf8());
    Drives drives(nullptr, false);
    DriveProperties dialog(computerVolumes().first(), &drives);
    dialog.show();
    qputenv("XETAL_FILES_ROOT", root.toUtf8());
    auto *button = dialog.findChild<QPushButton *>("systemCleaner");
    QVERIFY(button);
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(QFileInfo::exists(result));
    QFile arguments(result);
    QVERIFY(arguments.open(QIODevice::ReadOnly));
    QCOMPARE(arguments.readAll(), QByteArray("--section\ncleaner\n"));
  }
  void propertiesUsageAndUnavailableSpace() {
    Drives drives(nullptr, false);
    auto volume = computerVolumes().first();
    volume.name = "Projects <b> & 100% %10 backups";
    volume.size = volume.total = 1000;
    volume.available = 200;
    volume.freeBytes = 300;
    volume.spaceKnown = true;
    drives.volumes = {volume};
    DriveProperties dialog(volume, &drives);
    dialog.show();
    auto value = [&dialog](const QString &name) {
      return dialog.findChild<QLabel *>(name);
    };
    QCOMPARE(value("volumeHeading")->textFormat(), Qt::PlainText);
    QCOMPARE(value("volumeHeading")->text(), volume.name);
    QCOMPARE(value("usedBytes")->text(), QString("700 bytes"));
    QCOMPARE(value("freeBytes")->text(), QString("200 bytes"));
    QCOMPARE(value("reservedBytes")->text(), QString("100 bytes"));
    QCOMPARE(value("capacityBytes")->text(),
             QLocale().toString(1000) + " bytes");
    QVERIFY(dialog.findChild<QPushButton *>("openVolume")->isVisible());
    QVERIFY(dialog.findChild<QWidget *>("storageChart")
                ->accessibleDescription()
                .contains("700 bytes"));
    drives.volumes[0].available = 400;
    drives.volumes[0].freeBytes = 450;
    emit drives.changed();
    QCOMPARE(value("usedBytes")->text(), QString("550 bytes"));
    QCOMPARE(value("freeBytes")->text(), QString("400 bytes"));
    drives.volumes[0].mount.clear();
    drives.volumes[0].total = 0;
    emit drives.changed();
    QCOMPARE(value("usedValue")->text(), QString("—"));
    QCOMPARE(value("freeBytes")->text(), QString("Unavailable"));
    QCOMPARE(value("capacityBytes")->text(),
             QLocale().toString(1000) + " bytes");
    QVERIFY(value("usageHint")->text().contains("Mount this volume"));
    QVERIFY(!dialog.findChild<QPushButton *>("openVolume")->isVisible());
    drives.volumes.clear();
    emit drives.changed();
    QCOMPARE(value("volumeStatus")->text(), QString("Disconnected"));
    for (auto *button : dialog.findChildren<QPushButton *>())
      if (button->text() == "Copy details") {
        QTest::mouseClick(button, Qt::LeftButton);
        QVERIFY(
            QApplication::clipboard()->text().startsWith(volume.name + '\n'));
        QVERIFY(QApplication::clipboard()->text().contains("Device: " +
                                                           volume.device));
      }
    dialog.close();
  }
  void computerClipboardAndDriveMenu() {
    const QString source = folder + "/usb-source",
                  destination = folder + "/usb-target";
    QDir().mkpath(source);
    QDir().mkpath(destination);
    write(source + "/copy # 100%.txt", "copied safely\n");
    write(source + "/move.txt", "moved safely\n");
    write(source + "/menu.txt", "pasted from the menu\n");
    QStorageInfo storage(destination);
    Volume usb;
    usb.device = QString::fromLocal8Bit(storage.device());
    usb.name = "Test USB";
    usb.mount = destination;
    usb.filesystem = "ext4";
    usb.transport = "usb"; // USB SSDs often report RM=0.
    usb.uuid = "test-only";
    QVERIFY(QFileInfo::exists(usb.device));
    FilesWindow window(QUrl::fromLocalFile(source), false,
                       temporary.path() + "/usb-copy.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.drives->volumes = {usb};
    emit window.drives->changed();
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 3);
    tab->selectUrl(QUrl::fromLocalFile(source + "/copy # 100%.txt"));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls().size(), 1);
    window.openLocation(Fusion::computerUrl());
    QCOMPARE(tab->usbCards->count(), 1);
    auto selectDrive = [&] {
      tab->usbCards->setCurrentRow(0);
      window.activateWindow();
      tab->usbCards->setFocus();
      QTest::qWait(30);
    };
    selectDrive();
    QTest::keyClick(tab->usbCards, Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(
        QFileInfo::exists(destination + "/copy # 100%.txt"), 10000);
    QVERIFY(QFileInfo::exists(source + "/copy # 100%.txt"));
    window.openLocation(QUrl::fromLocalFile(source));
    QTRY_COMPARE(tab->proxy->rowCount(), 3);
    tab->selectUrl(QUrl::fromLocalFile(source + "/move.txt"));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    window.openLocation(Fusion::computerUrl());
    selectDrive();
    QTest::keyClick(tab->usbCards, Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(destination + "/move.txt"),
                             10000);
    QTRY_VERIFY(!QFileInfo::exists(source + "/move.txt"));
    QTest::keyClick(tab->usbCards, Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(),
             QList<QUrl>{QUrl::fromLocalFile(destination)});
    auto *data = new QMimeData;
    data->setUrls({QUrl::fromLocalFile(source + "/menu.txt")});
    QApplication::clipboard()->setMimeData(data);
    bool copyEnabled = false, cutDisabled = false, pasteEnabled = false,
         arkPresent = false;
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      auto *copy = menu->findChild<QAction *>("copy");
      auto *cut = menu->findChild<QAction *>("cut");
      auto *paste = menu->findChild<QAction *>("paste");
      copyEnabled = copy && copy->isEnabled();
      cutDisabled = cut && !cut->isEnabled();
      pasteEnabled = paste && paste->isEnabled();
      arkPresent = menu->findChild<QMenu *>("arkMenu");
      if (paste)
        paste->trigger();
      menu->close();
    });
    window.drives->menu(usb, window.mapToGlobal(QPoint(30, 30)), &window);
    QVERIFY(copyEnabled && cutDisabled && pasteEnabled && arkPresent);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(destination + "/menu.txt"),
                             10000);
    write(source + "/disconnected.txt");
    data = new QMimeData;
    data->setUrls({QUrl::fromLocalFile(source + "/disconnected.txt")});
    QApplication::clipboard()->setMimeData(data);
    window.drives->volumes[0].mount.clear();
    emit window.drives->changed();
    selectDrive();
    QTest::keyClick(tab->usbCards, Qt::Key_V, Qt::ControlModifier);
    QTest::qWait(100);
    QVERIFY(!QFileInfo::exists(destination + "/disconnected.txt"));
    QVERIFY(window.drives->mountedLocation(usb).isEmpty());
    QFile copied(destination + "/copy # 100%.txt");
    QVERIFY(copied.open(QIODevice::ReadOnly));
    QCOMPARE(copied.readAll(), QByteArray("copied safely\n"));
    window.close();
  }
  void defaultApplicationAndArkMenu() {
    const QString applications =
        qEnvironmentVariable("XDG_DATA_HOME") + "/applications";
    QDir().mkpath(applications);
    write(applications + "/fusion-test-editor.desktop",
          "[Desktop Entry]\nType=Application\nName=Fusion Test "
          "Editor\nExec=/bin/true %U\nMimeType=text/plain;\n");
    write(qEnvironmentVariable("XDG_CONFIG_HOME") + "/mimeapps.list",
          "[Default Applications]\ntext/plain=fusion-test-editor.desktop;\n");
    QCOMPARE(QProcess::execute("kbuildsycoca6", {"--noincremental"}), 0);
    const QString sample = folder + "/archive-menu";
    QDir().mkpath(sample);
    write(sample + "/archive me.txt", "archive fixture\n");
    FilesWindow window(QUrl::fromLocalFile(sample), false,
                       temporary.path() + "/menu.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 1);
    clickFile(tab, QUrl::fromLocalFile(sample + "/archive me.txt"));
    bool openNamed = false, chooser = false, copy = false, cut = false,
         paste = false;
    QStringList compression;
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      auto *open = menu->findChild<QAction *>("open");
      openNamed = open && open->text() == "Open with Fusion Test Editor";
      chooser = menu->findChild<QAction *>("openWith");
      copy = menu->findChild<QAction *>("copy");
      cut = menu->findChild<QAction *>("cut");
      paste = menu->findChild<QAction *>("paste");
      if (auto *ark = menu->findChild<QMenu *>("arkMenu"))
        for (auto *action : ark->actions())
          if (!action->isSeparator())
            compression << action->text();
      const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
      if (!capture.isEmpty())
        menu->grab().save(capture + "-menu.png");
      menu->close();
    });
    emit tab->contextRequested(window.mapToGlobal(QPoint(40, 80)));
    QVERIFY(openNamed && chooser && copy && cut && paste);
    QVERIFY2(compression.size() >= 2, qPrintable(compression.join(" | ")));
    QVERIFY2(std::any_of(compression.cbegin(), compression.cend(),
                         [](const QString &text) {
                           return text.contains("zip", Qt::CaseInsensitive);
                         }),
             qPrintable(compression.join(" | ")));
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      if (auto *ark = menu->findChild<QMenu *>("arkMenu"))
        for (auto *action : ark->actions())
          if (action->text().contains("zip", Qt::CaseInsensitive)) {
            action->trigger();
            break;
          }
      menu->close();
    });
    emit tab->contextRequested(window.mapToGlobal(QPoint(40, 80)));
    QTRY_COMPARE_WITH_TIMEOUT(
        QDir(sample).entryList({"*.zip"}, QDir::Files).size(), 1, 15000);
    const QString archive = QDir(sample).filePath(
        QDir(sample).entryList({"*.zip"}, QDir::Files).first());
    QProcess verify;
    verify.start("python3",
                 {"-c",
                  "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert "
                  "z.read('archive me.txt') == b'archive fixture\\n'",
                  archive});
    QVERIFY(verify.waitForFinished(5000));
    QCOMPARE(verify.exitCode(), 0);
    window.close();
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
    clickFile(tab, QUrl::fromLocalFile(original));
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
    clickFile(tab, QUrl::fromLocalFile(renamed));
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
    clickFile(tab, QUrl::fromLocalFile(copy));
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
    clickFile(tab, QUrl::fromLocalFile(renamed));
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
  void mouseSelectionInEveryView() {
    const QString base = folder + "/mouse-selection";
    QDir().mkpath(base);
    write(base + "/first.txt");
    write(base + "/second.unknown-format", QByteArray(32, '\0'));
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/mouse.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 2);
    for (int mode = 0; mode < 5; ++mode) {
      tab->setView(mode);
      focus(tab);
      tab->view()->clearSelection();
      clickFile(tab, QUrl::fromLocalFile(base + "/first.txt"));
      QCOMPARE(tab->selectedUrls(), QList<QUrl>{QUrl::fromLocalFile(base + "/first.txt")});
      clickFile(tab, QUrl::fromLocalFile(base + "/second.unknown-format"), Qt::ControlModifier);
      QCOMPARE(tab->selectedUrls().size(), 2);
      QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
      QCOMPARE(QApplication::clipboard()->mimeData()->urls().size(), 2);
      QTest::keyClick(tab->view(), Qt::Key_A, Qt::ControlModifier);
      QCOMPARE(tab->selectedItems().size(), 2);
    }
    window.close();
  }
  void dragAndDropAcrossViews() {
    const QString base = folder + "/drag-views";
    QDir().mkpath(base + "/Destination");
    const auto first = QUrl::fromLocalFile(base + "/photo # 100% café.png");
    const auto second = QUrl::fromLocalFile(base + "/notes.txt");
    write(first.toLocalFile());
    write(second.toLocalFile());
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/drag-views.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 3, 10000);
    // Exercise both initial construction and changing back from compact mode.
    int sequence = 0;
    for (int mode : {2, 3, 0, 1, 4, 2}) {
      tab->setView(mode);
      focus(tab);
      QVERIFY2(tab->view()->dragEnabled(), "View changes must not disable file dragging");
      QVERIFY(tab->view()->viewport()->acceptDrops());
      clickFile(tab, first);
      clickFile(tab, second, Qt::ControlModifier);
      const auto indexes = tab->view()->selectionModel()->selectedIndexes();
      std::unique_ptr<QMimeData> outgoing(tab->proxy->mimeData(indexes));
      QVERIFY(outgoing);
      QVERIFY(outgoing->hasFormat("text/uri-list"));
      QCOMPARE(outgoing->urls().size(), 2);
      QVERIFY(outgoing->urls().contains(first));
      QVERIFY(outgoing->urls().contains(second));
      const auto destination = tab->proxy->mapFromSource(
          tab->model->indexForUrl(QUrl::fromLocalFile(base + "/Destination")));
      QVERIFY(destination.flags().testFlag(Qt::ItemIsDropEnabled));
      const QString incoming = temporary.path() + "/incoming-" + QString::number(++sequence) + ".txt";
      write(incoming, "dropped file contents\n");
      QMimeData mime;
      mime.setUrls({QUrl::fromLocalFile(incoming)});
      const auto point = tab->view()->visualRect(destination).center();
      QDragEnterEvent enter(point, Qt::CopyAction, &mime, Qt::LeftButton, Qt::ControlModifier);
      QApplication::sendEvent(tab->view()->viewport(), &enter);
      QVERIFY(enter.isAccepted());
      QSignalSpy jobs(tab, &Browser::jobStarted);
      QDropEvent drop(point, Qt::CopyAction, &mime, Qt::LeftButton, Qt::ControlModifier);
      QApplication::sendEvent(tab->view()->viewport(), &drop);
      QVERIFY(drop.isAccepted());
      QCOMPARE(jobs.size(), 1);
      QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(base + "/Destination/" + QFileInfo(incoming).fileName()), 10000);
      QVERIFY(QFileInfo::exists(incoming));
    }
    window.close();
  }
  void unknownFilesAndScriptMenus() {
    const QString base = folder + "/script-menus";
    QDir().mkpath(base);
    const auto script = QUrl::fromLocalFile(base + "/a ; $(literal) # 100%.sh");
    const auto unknown = QUrl::fromLocalFile(base + "/data.unknown-format");
    write(script.toLocalFile(), "#!/usr/bin/env bash\nprintf 'fixture only'\n");
    write(unknown.toLocalFile(), QByteArray(32, '\0'));
    const auto command = Fusion::executionCommand(script);
    QCOMPARE(command, QStringList({"kitty", "--hold", "--directory", base, "-e",
                                  "/usr/bin/env", "bash", script.toLocalFile()}));
    QVERIFY(!QFileInfo(script.toLocalFile()).isExecutable());
    QVERIFY(Fusion::executionCommand(unknown).isEmpty());
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/scripts.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 2);
    for (const auto &url : {unknown, script}) {
      clickFile(tab, url);
      QStringList actions;
      QTimer::singleShot(0, &window, [&] {
        auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
        if (!menu) return;
        for (auto *action : menu->actions()) actions << action->objectName();
        menu->close();
      });
      const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(url));
      // Use the view's real right-click path, including hit testing.
      emit tab->view()->customContextMenuRequested(tab->view()->visualRect(index).center());
      for (const auto &id : {"open", "openWith", "copy", "cut", "paste", "rename", "trash"})
        QVERIFY2(actions.contains(id), id);
      if (url == script) QCOMPARE(actions.first(), QString("execute"));
      else QVERIFY(!actions.contains("execute"));
    }
    window.close();
  }
  void numberedPastesKeepBothAndSupportUndo() {
    const QString a = folder + "/numbered-a", b = folder + "/numbered-b";
    QDir().mkpath(a + "/project.v1/nested");
    QDir().mkpath(b);
    write(a + "/same.txt", "original source");
    write(a + "/.env", "dotfile");
    write(a + "/backup.tar.gz", "compound extension");
    write(a + "/project.v1/nested/data", "nested content");
    write(b + "/same.txt", "original destination");
    QVERIFY(QFile::link(a + "/missing", a + "/link"));
    FilesWindow window(QUrl::fromLocalFile(a), false,
                       temporary.path() + "/numbered.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    tab->setHidden(true);
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 5, 10000);
    bool popup = false;
    QTimer rejectConflicts;
    connect(&rejectConflicts, &QTimer::timeout, &window, [&] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QDialog *>(widget); dialog && dialog->isVisible()) {
          popup = true;
          dialog->reject();
        }
    });
    rejectConflicts.start(10);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_A, Qt::ControlModifier);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    for (int number = 1; number <= 2; ++number) {
      const auto suffix = "_copy" + QString::number(number);
      QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
      QTRY_COMPARE_WITH_TIMEOUT(finished.count(), number, 15000);
      QCOMPARE(finished.last().first().toInt(), 0);
      for (const auto &name : {"same" + suffix + ".txt", ".env" + suffix,
                               "backup" + suffix + ".tar.gz", "project.v1" + suffix + "/nested/data"})
        QVERIFY2(QFileInfo::exists(a + "/" + name), qPrintable(name));
      QVERIFY(QFileInfo(a + "/link" + suffix).isSymbolicLink());
      QVERIFY(!popup);
    }
    // Cut to an occupied name also keeps the destination; Undo restores source.
    focus(tab);
    clickFile(tab, QUrl::fromLocalFile(a + "/same.txt"));
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(a + "/same.txt")});
    QVERIFY(KIO::isClipboardDataCut(QApplication::clipboard()->mimeData()));
    window.openLocation(QUrl::fromLocalFile(b));
    QTRY_COMPARE(tab->proxy->rowCount(), 1);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 3, 15000);
    QCOMPARE(finished.last().first().toInt(), 0);
    QVERIFY(!QFileInfo::exists(a + "/same.txt"));
    QFile moved(b + "/same_copy1.txt"), existing(b + "/same.txt");
    QVERIFY(moved.open(QIODevice::ReadOnly));
    QVERIFY(existing.open(QIODevice::ReadOnly));
    QCOMPARE(moved.readAll(), QByteArray("original source"));
    QCOMPARE(existing.readAll(), QByteArray("original destination"));
    moved.close(); existing.close();
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Z, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(a + "/same.txt"), 10000);
    QVERIFY(!QFileInfo::exists(b + "/same_copy1.txt"));
    QVERIFY(!popup);
    window.close();
  }
  void transferProgress() {
    if (!qEnvironmentVariableIsSet("FUSION_FILES_PROGRESS_CHECK"))
      QSKIP("Run by test_progress.py with the real Fusion JobView service.");
    const auto source = folder + "/Transfer source";
    const auto target = folder + "/Transfer target";
    QDir().mkpath(source);
    QDir().mkpath(target);
    for (int n = 0; n < 1024; ++n)
      write(source + "/file-" + QString::number(n), QByteArray(65536, char(n % 127)));
    FilesWindow window(QUrl::fromLocalFile(folder), false,
                       temporary.path() + "/progress.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(QUrl::fromLocalFile(source)).isValid());
    clickFile(tab, QUrl::fromLocalFile(source));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    window.openLocation(QUrl::fromLocalFile(target));
    focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 30000);
    if (qEnvironmentVariableIsSet("FUSION_FILES_PROGRESS_CANCEL")) {
      QCOMPARE(finished.first().first().toInt(), int(KIO::ERR_USER_CANCELED));
      QCOMPARE(QDir(source).entryList(QDir::Files).size(), 1024);
      window.close();
      return;
    }
    QCOMPARE(finished.first().first().toInt(), 0);
    QCOMPARE(QDir(target + "/Transfer source").entryList(QDir::Files).size(), 1024);
    QFile last(target + "/Transfer source/file-1023");
    QVERIFY(last.open(QIODevice::ReadOnly));
    QCOMPARE(last.readAll(), QByteArray(65536, char(1023 % 127)));
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
  void applicationChooserAndExplicitOpen() {
    const QString sample = folder + "/app-chooser";
    QDir().mkpath(sample);
    const auto file = QUrl::fromLocalFile(sample + "/open # % literal.txt");
    write(file.toLocalFile());
    const QString log = sample + "/opened.json";
    const QString program = sample + "/editor.py";
    write(program, "import json,sys\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{log}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(json.dumps(sys.argv[1:]))\n");
    write(qEnvironmentVariable("XDG_DATA_HOME") + "/applications/fusion-test-editor.desktop",
          "[Desktop Entry]\nType=Application\nName=Fusion Test Editor\nExec=/usr/bin/python3 \"" + program.toUtf8() + "\" %F\nIcon=text-editor\nMimeType=text/plain;\n");
    QCOMPARE(QProcess::execute("kbuildsycoca6", {"--noincremental"}), 0);
    FilesWindow window(QUrl::fromLocalFile(sample), false, temporary.path() + "/chooser.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(file).isValid());
    clickFile(tab, file);
    // An explicit menu action must work while an address/search editor owns focus.
    tab->filter->setFocus();
    window.runAction("open");
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 10000);
    QFile opened(log); QVERIFY(opened.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(opened.readAll()).array(), QJsonArray{file.toLocalFile()});
    Fusion::ApplicationDialog chooser({KFileItem(file)}, &window);
    chooser.show();
    auto *list = chooser.findChild<QListWidget *>("applicationList");
    auto *search = chooser.findChild<QLineEdit *>("applicationSearch");
    QVERIFY(list && search);
    QTRY_VERIFY_WITH_TIMEOUT(list->count() > 0, 10000);
    search->setFocus(); QTest::keyClicks(search, "Fusion Test Editor");
    QCOMPARE(search->text(), QString("Fusion Test Editor"));
    QTRY_COMPARE(list->count(), 1);
    QCOMPARE(chooser.request().value("app").toString(), QString("fusion-test-editor.desktop"));
    QVERIFY(!chooser.request().value("remember").toBool());
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) chooser.grab().save(capture + "-open-with.png");
    chooser.reject(); window.close();
  }
  void executableDoubleClickRunsWithoutChangingPermissions() {
    const QString sample = folder + "/executable-click";
    QDir().mkpath(sample + "/bin");
    const QString log = sample + "/executed";
    const auto script = QUrl::fromLocalFile(sample + "/test installer.run");
    write(script.toLocalFile(), "#!/usr/bin/python3\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{log}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text('executed')\n");
    QFile::setPermissions(script.toLocalFile(), QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    // A test-only terminal launches the harmless fixture; no desktop terminal opens.
    const QString kitty = sample + "/bin/kitty";
    write(kitty, "#!/usr/bin/python3\nimport os,sys\na=sys.argv[sys.argv.index('-e')+1:];os.execvp(a[0],a)\n");
    QFile::setPermissions(kitty, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH");
    qputenv("PATH", QFile::encodeName(sample + "/bin:") + previousPath);
    auto resetPath = qScopeGuard([&] { qputenv("PATH", previousPath); });
    const auto permissions = QFileInfo(script.toLocalFile()).permissions();
    FilesWindow window(QUrl::fromLocalFile(sample), false, temporary.path() + "/execute.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(script).isValid());
    clickFile(tab, script);
    const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(script));
    QTest::mouseDClick(tab->view()->viewport(), Qt::LeftButton, Qt::NoModifier, tab->view()->visualRect(index).center());
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 10000);
    QCOMPARE(QFileInfo(script.toLocalFile()).permissions(), permissions);
    window.close();
  }
  void thumbnailsConfigurationAndTrashAnimation() {
    const QString sample = folder + "/thumbnails";
    QDir().mkpath(sample);
    const auto file = QUrl::fromLocalFile(sample + "/red picture.png");
    QImage image(160, 100, QImage::Format_RGB32); image.fill(QColor("#eb425a")); QVERIFY(image.save(file.toLocalFile()));
    const QString settings = temporary.path() + "/thumbnails.ini";
    FilesWindow window(QUrl::fromLocalFile(sample), false, settings);
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    auto *preview = window.findChild<QAction *>("previewPaneAction");
    QVERIFY(preview && preview->isChecked());
    QTRY_VERIFY(tab->model->indexForUrl(file).isValid());
    auto pixel = [&] {
      const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(file));
      const auto pixmap = qvariant_cast<QIcon>(index.data(Qt::DecorationRole)).pixmap(80, 80).toImage();
      return pixmap.isNull() ? QColor() : pixmap.pixelColor(pixmap.width()/2, pixmap.height()/2);
    };
    QTRY_VERIFY_WITH_TIMEOUT(pixel().red() > 210 && pixel().green() < 100, 15000);
    clickFile(tab, file); focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_Delete);
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 10000);
    QCOMPARE(finished.last().first().toInt(), 0);
    QVERIFY(!QFileInfo::exists(file.toLocalFile()));
    QVERIFY(window.findChild<QWidget *>("trashFlight"));
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) { QTest::qWait(260); window.grab().save(capture + "-trash-flight.png"); }
    QTRY_VERIFY_WITH_TIMEOUT(!window.findChild<QWidget *>("trashFlight"), 2000);
    bool configured = false;
    QTimer::singleShot(0, &window, [&] {
      auto *dialog = window.findChild<QDialog *>("filesConfiguration");
      if (!dialog) return;
      dialog->findChild<QCheckBox *>("configureThumbnails")->setChecked(false);
      dialog->findChild<QCheckBox *>("configurePreview")->setChecked(false);
      dialog->findChild<QCheckBox *>("configureTrashAnimation")->setChecked(false);
      if (!capture.isEmpty()) dialog->grab().save(capture + "-configuration.png");
      configured = true; dialog->accept();
    });
    auto *action = window.findChild<QAction *>("configureFiles"); QVERIFY(action); action->trigger();
    QVERIFY(configured);
    QVERIFY(!preview->isChecked());
    QCOMPARE(window.preferences.settings.value("thumbnails").toBool(), false);
    window.close();
    FilesWindow reopened(QUrl::fromLocalFile(sample), false, settings);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false);
    QVERIFY(!reopened.findChild<QAction *>("previewPaneAction")->isChecked());
    QCOMPARE(reopened.preferences.settings.value("trashAnimation").toBool(), false);
  }
  void permissionFailureRequestsAuthenticationAndCancellationKeepsFile() {
    const QString sample = folder + "/permission-retry", bin = sample + "/bin", protectedFolder = sample + "/protected";
    QDir().mkpath(bin); QDir().mkpath(protectedFolder);
    const auto file = QUrl::fromLocalFile(protectedFolder + "/keep.txt");
    write(file.toLocalFile());
    const QString request = sample + "/request.json";
    write(bin + "/pkexec", "#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{request}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(sys.stdin.read())\nsys.exit(126)\n");
    QFile::setPermissions(bin + "/pkexec", QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH"); qputenv("PATH", QFile::encodeName(bin + ':') + previousPath);
    auto restore = qScopeGuard([&] { qputenv("PATH", previousPath); QFile::setPermissions(protectedFolder, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner); });
    QFile::setPermissions(protectedFolder, QFile::ReadOwner | QFile::ExeOwner);
    auto *job = new Fusion::RemovalJob({file}, false, nullptr);
    QSignalSpy finished(job, &KJob::result);
    int error = -1; connect(job, &KJob::result, this, [&](KJob *job) { error = job->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 15000);
    QVERIFY(QFileInfo::exists(file.toLocalFile()));
    QFile record(request); QVERIFY(record.open(QIODevice::ReadOnly));
    const auto data = QJsonDocument::fromJson(record.readAll()).object();
    QCOMPARE(data.value("operation").toString(), QString("trash"));
    QCOMPARE(data.value("items").toArray().first().toObject().value("path").toString(), file.toLocalFile());
    QCOMPARE(error, int(KIO::ERR_USER_CANCELED));
  }
  void protectedRestoreUsesTrashMetadataAndKeepsCancelledItem() {
    const QString sample = folder + "/restore-retry", bin = sample + "/bin", destination = sample + "/protected";
    QDir().mkpath(bin); QDir().mkpath(destination);
    const QString trash = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/Trash";
    QDir().mkpath(trash + "/files"); QDir().mkpath(trash + "/info");
    const QString name = "fusion-restore-fixture.txt", original = destination + "/original # name.txt";
    write(trash + "/files/" + name);
    write(trash + "/info/" + name + ".trashinfo", "[Trash Info]\nPath=" + QUrl::toPercentEncoding(original, "/") + "\nDeletionDate=2026-01-01T12:00:00\n");
    const auto url = QUrl("trash:/0-" + name);
    auto *stat = KIO::stat(url); stat->setAutoDelete(false);
    QVERIFY2(stat->exec(), qPrintable(stat->errorString()));
    const KFileItem item(stat->statResult(), url); delete stat;
    QCOMPARE(item.localPath(), trash + "/files/" + name);
    const QString request = sample + "/request.json";
    write(bin + "/pkexec", "#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{request}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(sys.stdin.read())\nsys.exit(126)\n");
    QFile::setPermissions(bin + "/pkexec", QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH"); qputenv("PATH", QFile::encodeName(bin + ':') + previousPath);
    auto reset = qScopeGuard([&] { qputenv("PATH", previousPath); QFile::setPermissions(destination, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner); });
    QFile::setPermissions(destination, QFile::ReadOwner | QFile::ExeOwner);
    auto *job = new Fusion::RemovalJob(KFileItemList{item}, QString("restore"), nullptr);
    QSignalSpy finished(job, &KJob::result);
    int error = -1; connect(job, &KJob::result, this, [&](KJob *result) { error = result->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 15000);
    QCOMPARE(error, int(KIO::ERR_USER_CANCELED));
    QVERIFY(QFileInfo::exists(item.localPath())); QVERIFY(!QFileInfo::exists(original));
    QFile record(request); QVERIFY(record.open(QIODevice::ReadOnly));
    const auto data = QJsonDocument::fromJson(record.readAll()).object();
    QCOMPARE(data.value("operation").toString(), QString("restore"));
    const auto selection = data.value("items").toArray().first().toObject();
    QCOMPARE(selection.value("path").toString(), item.localPath());
    QCOMPARE(selection.value("restoreTo").toString(), original);
    QVERIFY(selection.value("fromTrash").toBool());
    QFile::setPermissions(destination, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    auto *retry = new Fusion::RemovalJob(KFileItemList{item}, QString("restore"), nullptr);
    QSignalSpy restored(retry, &KJob::result);
    connect(retry, &KJob::result, this, [&](KJob *result) { error = result->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!restored.isEmpty(), 15000);
    QCOMPARE(error, 0); QVERIFY(QFileInfo::exists(original));
    QVERIFY(!QFileInfo::exists(item.localPath()));
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
      if (!window.findChild<QAction *>("previewPaneAction")->isChecked()) window.runAction("preview");
      QTest::qWait(700);
      QVERIFY(window.grab().save(capture + "-folder.png"));
      window.openLocation(Fusion::computerUrl());
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      window.runAction("preview");
      window.resize(1280, 1120);
      QTest::qWait(150);
      QVERIFY(window.grab().save(capture + "-computer.png"));
      auto system = *std::find_if(
          window.drives->volumes.cbegin(), window.drives->volumes.cend(),
          [](const Volume &v) { return v.mount == "/"; });
      system.available = system.total * 31 / 100;
      system.freeBytes = system.total * 36 / 100;
      system.uuid = "01234567-89ab-cdef-0123-456789abcdef";
      DriveProperties properties(system, window.drives, &window);
      properties.show();
      QTest::qWait(100);
      QVERIFY(properties.grab().save(capture + "-properties.png"));
      QVERIFY(Fusion::icon("fusion-computer")
                  .pixmap(256, 256)
                  .save(capture + "-icon.png"));
      properties.close();
    }
    window.close();
  }
};
QTEST_MAIN(FileTests)
#include "tests.moc"
