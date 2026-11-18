#include "drive_shelf.h"
#include <QtTest>

class DriveShelfTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  static QList<Volume> inventory() {
    auto result = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/test-a","type":"disk","model":"System SSD","size":1000000000000,"children":[
        {"path":"/dev/test-a1","type":"part","fstype":"vfat","label":"EFI","size":512000000,"mountpoints":["/boot/efi"]},
        {"path":"/dev/test-a2","type":"part","fstype":"ext4","label":"HyperFusion","size":998000000000,"mountpoints":["/"]},
        {"path":"/dev/test-a3","type":"part","parttype":"21686148-6449-6e6f-744e-656564454649","size":1000000}]},
      {"path":"/dev/test-b","type":"disk","model":"Windows SSD","size":1000000000000,"fstype":"ntfs","label":"Windows"},
      {"path":"/dev/test-c","type":"disk","model":"Portable SSD","size":64000000000,"tran":"usb","children":[
        {"path":"/dev/test-c1","type":"part","fstype":"vfat","label":"Photos","size":63000000000},
        {"path":"/dev/test-c2","type":"part","fstype":"crypto_LUKS","label":"Encrypted","size":1000000000}]}
    ]})");
    for (auto &v : result) if (v.mounted()) { v.spaceKnown = true; v.total = v.size; v.available = v.size / 2; }
    return result;
  }
  static VolumeCard *card(DriveShelf &shelf, const QString &device) {
    for (auto *item : shelf.findChildren<VolumeCard *>()) if (item->volume().device == device) return item;
    return nullptr;
  }
  static QFrame *group(DriveShelf &shelf, const QString &key) {
    for (auto *item : shelf.findChildren<QFrame *>("physicalDriveGroup")) if (item->property("driveKey") == key) return item;
    return nullptr;
  }
  static QPoint position(DriveShelf &shelf, QWidget *widget) { return widget->mapTo(&shelf, QPoint()); }
private slots:
  void initTestCase() { QVERIFY(temporary.isValid()); qApp->setQuitOnLastWindowClosed(false); }
  void gridReflowsAndSystemPartitionsStayAccessible() {
    Fusion::Preferences prefs(temporary.path()+"/layout.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 800); shelf.show();
    QCOMPARE(shelf.findChildren<QFrame *>("physicalDriveGroup").size(), 3);
    auto *a = group(shelf, "/dev/test-a"), *c = group(shelf, "/dev/test-c");
    QTRY_VERIFY(position(shelf,a).x() < position(shelf,c).x()); QCOMPARE(position(shelf,a).y(), position(shelf,c).y());
    QVERIFY(card(shelf, "/dev/test-a2")->isVisible());
    auto *efi = card(shelf, "/dev/test-a1"), *reserved = card(shelf, "/dev/test-a3");
    QVERIFY(efi->isVisible()); QVERIFY(reserved->isVisible());
    QVERIFY(efi->property("partitionIcon").toBool()); QVERIFY(reserved->property("partitionIcon").toBool());
    QVERIFY(a->isAncestorOf(efi)); QVERIFY(a->isAncestorOf(reserved));
    QVERIFY(efi->width() <= 30); QVERIFY(efi->toolTip().contains("EFI"));
    // Ordinary FAT data keeps a full row; system icons still select and open.
    QVERIFY(card(shelf, "/dev/test-c1")->isVisible()); QVERIFY(!card(shelf, "/dev/test-c1")->property("partitionIcon").toBool());
    QSignalSpy operations(&shelf, &DriveShelf::operationRequested), context(&shelf, &DriveShelf::volumeContextRequested);
    shelf.selectDevice("/dev/test-a1", true); QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-a1"));
    QTest::keyClick(efi, Qt::Key_Return); QCOMPARE(operations.size(), 1);
    QCOMPARE(operations.first()[0].value<Volume>().device, QString("/dev/test-a1"));
    emit efi->customContextMenuRequested(efi->rect().center()); QCOMPARE(context.size(), 1);
    QCOMPARE(context.first()[0].value<Volume>().device, QString("/dev/test-a1"));
    const auto place = shelf.place(); shelf.selectDevice("/dev/test-a2"); shelf.restorePlace(place);
    QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-a1"));
    shelf.resize(500, 300); QTRY_VERIFY(position(shelf,a).y() < position(shelf,c).y());
    for (auto *item : shelf.findChildren<VolumeCard *>()) if (item->isVisible())
      QVERIFY(item->width() <= shelf.width());
    auto *scroll = shelf.findChild<QScrollArea *>("computerDrivesScroll");
    QCOMPARE(scroll->horizontalScrollBar()->maximum(), 0);
    QVERIFY(scroll->verticalScrollBar()->maximum() > 0);
  }
  void keyboardMountAndOpenUseTheCurrentVolume() {
    Fusion::Preferences prefs(temporary.path()+"/actions.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 800); shelf.show(); shelf.activateWindow();
    QSignalSpy operations(&shelf, &DriveShelf::operationRequested);
    auto *windows = card(shelf, "/dev/test-b");
    shelf.selectDevice("/dev/test-b", true);
    auto *mount = windows->findChild<QPushButton *>("mountVolume");
    QTRY_VERIFY(mount->isVisible()); QVERIFY(mount->isEnabled());
    QCOMPARE(operations.size(), 0); // Showing or selecting never mounts.
    mount->click(); QCOMPARE(operations.size(), 1);
    QCOMPARE(operations.last()[0].value<Volume>().device, QString("/dev/test-b"));
    QCOMPARE(operations.last()[1].toString(), QString("mount"));
    QTest::keyClick(windows, Qt::Key_Return); QCOMPARE(operations.size(), 2);
    QCOMPARE(operations.last()[1].toString(), QString("open"));
    auto *locked = card(shelf, "/dev/test-c2"); shelf.selectDevice(locked->volume().device, true);
    QVERIFY(!locked->findChild<QPushButton *>("mountVolume")->isEnabled());
    QTest::keyClick(locked, Qt::Key_Up);
    QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-c1"));
    QSignalSpy context(&shelf, &DriveShelf::volumeContextRequested);
    emit locked->customContextMenuRequested(locked->rect().center());
    QCOMPARE(context.size(), 1); QCOMPARE(context.first()[0].value<Volume>().device, QString("/dev/test-c2"));
  }
  void categoriesStayTogetherAtEveryWidthAndFollowMountChanges() {
    Fusion::Preferences prefs(temporary.path()+"/categories.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    auto extras = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/first","type":"disk","model":"Backup disk","fstype":"ext4","mountpoints":["/media/backup"]},
      {"path":"/dev/sr0","type":"rom","model":"DVD drive","tran":"usb","rm":1,"fstype":"iso9660"},
      {"path":"/dev/zip","type":"disk","model":"IOMEGA ZIP 100","tran":"usb","rm":1,"fstype":"vfat"}
    ]})");
    drives.volumes.append(extras);
    for (const auto &type : {"wine-prefix", "steam-prefix"}) {
      Volume v; v.device="/prefixes/"+QString(type)+"/drive_c"; v.mount=v.device; v.type=type;
      v.name=QString(type)+" (C:)"; v.driveModel=v.name; drives.volumes << v;
    }
    DriveShelf shelf(&prefs, &drives); shelf.resize(1350, 1400); shelf.show();
    auto *main=group(shelf,"/dev/test-a"), *mounted=group(shelf,"/dev/first"), *cd=group(shelf,"/dev/sr0"),
        *zip=group(shelf,"/dev/zip"), *usb=group(shelf,"/dev/test-c"), *last=group(shelf,"/dev/test-b"),
        *wine=group(shelf,"/prefixes/wine-prefix/drive_c"), *steam=group(shelf,"/prefixes/steam-prefix/drive_c");
    QTRY_VERIFY(position(shelf,main).y() < position(shelf,mounted).y());
    QCOMPARE(position(shelf,main).x(), position(shelf,mounted).x());
    QCOMPARE(position(shelf,main).y(), position(shelf,cd).y()); QVERIFY(position(shelf,cd).x() > position(shelf,main).x());
    QCOMPARE(position(shelf,cd).y(), position(shelf,zip).y()); QVERIFY(position(shelf,cd).x() < position(shelf,zip).x());
    QVERIFY(position(shelf,usb).y() > position(shelf,cd).y());
    QVERIFY(position(shelf,wine).y() > position(shelf,usb).y()); QCOMPARE(position(shelf,wine).y(), position(shelf,steam).y());
    QVERIFY(position(shelf,wine).x() < position(shelf,steam).x()); QVERIFY(position(shelf,last).y() > position(shelf,steam).y());
    QCOMPARE(card(shelf,"/dev/sr0")->volume().driveModel,QString("DVD drive"));
    QVERIFY(card(shelf,"/dev/sr0")->volume().optical()); QVERIFY(card(shelf,"/dev/zip")->volume().legacyMedia());
    QVERIFY(!wine->findChild<QWidget *>("physicalDriveHeading")->isVisible());
    shelf.resize(500, 800); QTRY_VERIFY(position(shelf,cd).y() < position(shelf,zip).y()); QVERIFY(position(shelf,zip).y() < position(shelf,usb).y());
    shelf.selectDevice("/dev/test-b",true);
    for (auto &v : drives.volumes) if(v.device=="/dev/test-b") v.mount="/media/windows";
    shelf.refresh(); QTRY_COMPARE(last->property("driveCategory").toInt(),1);
    QCOMPARE(shelf.selectedVolume().device,QString("/dev/test-b")); QVERIFY(position(shelf,last).y() < position(shelf,cd).y());
    auto *scroll=shelf.findChild<QScrollArea *>("computerDrivesScroll"); QCOMPARE(scroll->horizontalScrollBar()->maximum(),0);
    shelf.findChild<QToolButton *>("computerListView")->click();
    QTRY_COMPARE(position(shelf,cd).x(),position(shelf,zip).x()); QVERIFY(position(shelf,cd).y() < position(shelf,zip).y());
  }
  void refreshPreservesWidgetsFocusSelectionAndPartitionIcons() {
    Fusion::Preferences prefs(temporary.path()+"/refresh.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(650, 250); shelf.show(); shelf.activateWindow();
    auto *windows = card(shelf, "/dev/test-b"); shelf.selectDevice("/dev/test-b", true);
    auto *efi = card(shelf, "/dev/test-a1");
    auto *scroll = shelf.findChild<QScrollArea *>("computerDrivesScroll");
    QTRY_VERIFY(scroll->verticalScrollBar()->maximum() > 0);
    scroll->verticalScrollBar()->setValue(100);
    std::reverse(drives.volumes.begin(), drives.volumes.end()); shelf.refresh(); QTest::qWait(20);
    QCOMPARE(card(shelf, "/dev/test-b"), windows); QCOMPARE(scroll->verticalScrollBar()->value(), 100);
    QCOMPARE(card(shelf, "/dev/test-a1"), efi); QVERIFY(efi->isVisible()); QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-b"));
    QVERIFY(windows->hasFocus());
    for (auto &v : drives.volumes) if (v.device == "/dev/test-b") v.mount = "/media/Windows";
    shelf.refresh(); QTest::qWait(20);
    QCOMPARE(card(shelf, "/dev/test-b"), windows); QCOMPARE(shelf.selectedVolume().mount, QString("/media/Windows"));
    QVERIFY(windows->hasFocus()); QVERIFY(!windows->findChild<QPushButton *>("mountVolume")->isEnabled());
    drives.volumes.clear(); shelf.refresh();
    QVERIFY(shelf.selectedVolume().device.isEmpty()); QVERIFY(shelf.findChild<QLabel *>("emptyDrives")->isVisible());
  }
  void listPreferencePersistsAndIconsRemainVisible() {
    Fusion::Preferences prefs(temporary.path()+"/prefs.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    {
      DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 900); shelf.show();
      shelf.findChild<QToolButton *>("computerListView")->click();
      QTRY_COMPARE(position(shelf, group(shelf, "/dev/test-a")).x(), position(shelf, group(shelf, "/dev/test-b")).x());
      QTRY_VERIFY(card(shelf, "/dev/test-b")->height() < 104);
      prefs.settings.sync();
    }
    Fusion::Preferences saved(temporary.path()+"/prefs.ini"); DriveShelf again(&saved, &drives); again.show();
    QVERIFY(again.findChild<QToolButton *>("computerListView")->isChecked());
    QVERIFY(card(again, "/dev/test-a1")->isVisible());
  }
  void fixedTilesKeepTheirSizeIncludingSwapPrefixesAndMultipleVolumes() {
    Fusion::Preferences prefs(temporary.path()+"/fixed.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    Volume swap; swap.device = "/dev/zram0"; swap.name = "zram0"; swap.type = "disk"; swap.filesystem = "swap"; swap.size = 4ULL << 30;
    Volume wine; wine.device = "/prefix/drive_c"; wine.mount = wine.device; wine.type = "wine-prefix"; wine.name = "Wine (C:)";
    drives.volumes << swap << wine;
    DriveShelf shelf(&prefs, &drives); shelf.resize(1300, 1100); shelf.show();
    QTRY_VERIFY(card(shelf, "/dev/zram0")->isVisible());
    QVERIFY(!card(shelf, "/dev/zram0")->property("partitionIcon").toBool());
    auto assertTiles = [&] {
      int count = 0;
      for (auto *tile : shelf.findChildren<QFrame *>("driveTile")) if (tile->isVisible()) {
        QCOMPARE(tile->size(), QSize(380, 120)); ++count;
        auto *volume = tile->findChild<VolumeCard *>(); QVERIFY(volume);
        QVERIFY(tile->rect().contains(QRect(volume->mapTo(tile, QPoint()), volume->size())));
      }
      QCOMPARE(count, 6); // System, Windows, both USB volumes, swap and Wine.
    };
    QTest::qWait(20); assertTiles();
    const auto mountedSize = group(shelf, "/dev/test-a")->size();
    for (const int width : {2100, 850, 500, 1300}) {
      shelf.resize(width, 1100); QTest::qWait(20); assertTiles();
      QCOMPARE(group(shelf, "/dev/test-a")->size(), mountedSize);
      QCOMPARE(shelf.findChild<QScrollArea *>("computerDrivesScroll")->horizontalScrollBar()->maximum(), 0);
    }
    // Adding a mount and its usage bar does not change the tile's geometry.
    for (auto &volume : drives.volumes) if (volume.device == "/dev/test-b") {
      volume.mount = "/media/Windows"; volume.spaceKnown = true; volume.total = volume.size; volume.available = volume.size / 3;
    }
    shelf.refresh(); QTest::qWait(20); assertTiles();
    QVERIFY(card(shelf, "/dev/test-b")->findChild<QProgressBar *>("volumeUsage")->isVisible());
  }
  void originalViewPersistsAndSwitchesWithoutLosingVolumesOrActions() {
    Fusion::Preferences prefs(temporary.path()+"/original.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    {
      DriveShelf shelf(&prefs, &drives); shelf.resize(1300, 1000); shelf.show();
      auto *original = shelf.findChild<QToolButton *>("computerOriginalView");
      auto *tiles = shelf.findChild<QToolButton *>("computerShelfView");
      QVERIFY(original); QTRY_VERIFY(original->x() < tiles->x());
      auto *windows = card(shelf, "/dev/test-b"), *efi = card(shelf, "/dev/test-a1");
      shelf.selectDevice("/dev/test-b"); QSignalSpy operations(&shelf, &DriveShelf::operationRequested);
      original->click(); QTest::qWait(20);
      QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-b")); QCOMPARE(card(shelf, "/dev/test-b"), windows);
      QVERIFY(!efi->isVisible()); QVERIFY(windows->property("original").toBool());
      auto *disclosure = group(shelf, "/dev/test-a")->findChild<QToolButton *>("systemPartitions");
      QVERIFY(disclosure->isVisible()); disclosure->click(); QTRY_VERIFY(efi->isVisible()); QVERIFY(efi->width() > 28);
      shelf.selectDevice(efi->volume().device, true); QTest::keyClick(efi, Qt::Key_Return); QCOMPARE(operations.size(), 1);
      QCOMPARE(operations.last()[0].value<Volume>().device, efi->volume().device);
      for (int i = 0; i < 3; ++i) {
        tiles->click(); QTest::qWait(10); QCOMPARE(card(shelf, "/dev/test-a1"), efi); QCOMPARE(efi->size(), QSize(28, 28));
        QCOMPARE(shelf.selectedVolume().device, efi->volume().device);
        original->click(); QTest::qWait(10); QVERIFY(efi->isVisible()); QVERIFY(efi->width() > 28);
      }
      prefs.settings.sync();
    }
    Fusion::Preferences saved(temporary.path()+"/original.ini"); DriveShelf again(&saved, &drives); again.show();
    QVERIFY(again.findChild<QToolButton *>("computerOriginalView")->isChecked());
    QVERIFY(group(again, "/dev/test-a")->findChild<QToolButton *>("systemPartitions")->isChecked());
    again.findChild<QToolButton *>("computerShelfView")->click(); saved.settings.sync();
    DriveShelf tilesAgain(&saved, &drives); QVERIFY(tilesAgain.findChild<QToolButton *>("computerShelfView")->isChecked());
  }
  void ventoyBootPartitionUsesAnIconAndDataStaysFullSize() {
    Volume boot; boot.name = "VTOYEFI"; boot.filesystem = "vfat"; boot.size = 32 * 1024 * 1024;
    QVERIFY(boot.compactCard());
    boot.name = "Photos"; QVERIFY(!boot.compactCard());
    boot.name = "VTOYEFI"; boot.filesystem = "ext4"; QVERIFY(!boot.compactCard());
  }
  void changedPhysicalParentAndHotplugDoNotLeaveStaleCards() {
    Fusion::Preferences prefs(temporary.path()+"/hotplug.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(1000, 700); shelf.show();
    QPointer<VolumeCard> windows = card(shelf, "/dev/test-b"); shelf.selectDevice("/dev/test-b");
    for (auto &v : drives.volumes) if (v.device == "/dev/test-b") v.driveDevice = "/dev/new-backing";
    shelf.refresh(); QTest::qWait(20);
    QCOMPARE(card(shelf, "/dev/test-b"), windows.data()); QVERIFY(windows->isVisible());
    QCOMPARE(shelf.selectedVolume().driveKey(), QString("/dev/new-backing"));
    drives.volumes.removeIf([](const Volume &v) { return v.device == "/dev/test-b"; }); shelf.refresh();
    QVERIFY(windows.isNull()); QVERIFY(shelf.selectedVolume().device.isEmpty());
  }
};
QTEST_MAIN(DriveShelfTests)
#include "drive_shelf_tests.moc"
