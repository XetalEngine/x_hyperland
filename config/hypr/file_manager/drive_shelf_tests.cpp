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
private slots:
  void initTestCase() { QVERIFY(temporary.isValid()); qApp->setQuitOnLastWindowClosed(false); }
  void gridReflowsAndSystemPartitionsStayAccessible() {
    Fusion::Preferences prefs(temporary.path()+"/layout.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 800); shelf.show();
    QCOMPARE(shelf.findChildren<QFrame *>("physicalDriveGroup").size(), 3);
    auto *a = group(shelf, "/dev/test-a"), *c = group(shelf, "/dev/test-c");
    QTRY_VERIFY(a->x() != c->x()); QCOMPARE(a->y(), c->y());
    QVERIFY(card(shelf, "/dev/test-a2")->isVisible());
    QVERIFY(!card(shelf, "/dev/test-a1")->isVisible());
    QVERIFY(!card(shelf, "/dev/test-a3")->isVisible());
    // An ordinary FAT data partition must remain visible.
    QVERIFY(card(shelf, "/dev/test-c1")->isVisible());
    auto *toggle = a->findChild<QToolButton *>("systemPartitions");
    QCOMPARE(toggle->text(), QString("System partitions · 2"));
    toggle->click(); QVERIFY(card(shelf, "/dev/test-a1")->isVisible());
    shelf.selectDevice("/dev/test-a1"); toggle->click();
    QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-a2"));
    shelf.resize(500, 500); QTRY_COMPARE(a->x(), c->x()); QVERIFY(a->y() != c->y());
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
  void refreshPreservesWidgetsFocusSelectionAndDisclosure() {
    Fusion::Preferences prefs(temporary.path()+"/refresh.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(650, 500); shelf.show(); shelf.activateWindow();
    auto *windows = card(shelf, "/dev/test-b"); shelf.selectDevice("/dev/test-b", true);
    auto *toggle = group(shelf, "/dev/test-a")->findChild<QToolButton *>("systemPartitions"); toggle->setChecked(true);
    auto *scroll = shelf.findChild<QScrollArea *>("computerDrivesScroll");
    QTRY_VERIFY(scroll->verticalScrollBar()->maximum() > 0);
    scroll->verticalScrollBar()->setValue(100);
    std::reverse(drives.volumes.begin(), drives.volumes.end()); shelf.refresh(); QTest::qWait(20);
    QCOMPARE(card(shelf, "/dev/test-b"), windows); QCOMPARE(scroll->verticalScrollBar()->value(), 100);
    QVERIFY(toggle->isChecked()); QCOMPARE(shelf.selectedVolume().device, QString("/dev/test-b"));
    QVERIFY(windows->hasFocus());
    for (auto &v : drives.volumes) if (v.device == "/dev/test-b") v.mount = "/media/Windows";
    shelf.refresh(); QTest::qWait(20);
    QCOMPARE(card(shelf, "/dev/test-b"), windows); QCOMPARE(shelf.selectedVolume().mount, QString("/media/Windows"));
    QVERIFY(windows->hasFocus()); QVERIFY(!windows->findChild<QPushButton *>("mountVolume")->isEnabled());
    drives.volumes.clear(); shelf.refresh();
    QVERIFY(shelf.selectedVolume().device.isEmpty()); QVERIFY(shelf.findChild<QLabel *>("emptyDrives")->isVisible());
  }
  void listAndDisclosurePreferencesPersist() {
    Fusion::Preferences prefs(temporary.path()+"/prefs.ini"); Drives drives(nullptr, false); drives.volumes = inventory();
    {
      DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 900); shelf.show();
      shelf.findChild<QToolButton *>("computerListView")->click();
      QTRY_COMPARE(group(shelf, "/dev/test-a")->x(), group(shelf, "/dev/test-b")->x());
      QTRY_VERIFY(card(shelf, "/dev/test-b")->height() < 104);
      group(shelf, "/dev/test-a")->findChild<QToolButton *>("systemPartitions")->click();
      prefs.settings.sync();
    }
    Fusion::Preferences saved(temporary.path()+"/prefs.ini"); DriveShelf again(&saved, &drives); again.show();
    QVERIFY(again.findChild<QToolButton *>("computerListView")->isChecked());
    QVERIFY(card(again, "/dev/test-a1")->isVisible());
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
