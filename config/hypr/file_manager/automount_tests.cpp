#include "automount.h"
#include "browser.h"
#include <QtTest>

class AutoMountTests : public QObject {
  Q_OBJECT
  QTemporaryDir temp;
  QString settings, session;
  static Volume disk(const QString &uuid = "data-1234", const QString &device = "/dev/fusion-b1") {
    Volume v;
    v.uuid = uuid; v.device = device; v.driveDevice = "/dev/fusion-b";
    v.filesystem = "ext4"; v.name = "Projects"; v.connection = "15";
    return v;
  }
  static void remember(AutoMountPolicy &policy, Volume v) {
    v.mount = "/media/Projects"; v.verifiedMount = true;
    QString error;
    QVERIFY2(policy.observe({v}, &error), qPrintable(error));
  }
  static void write(const QString &path, const QByteArray &data, bool executable = false) {
    QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); QCOMPARE(file.write(data), data.size());
    if (executable) QVERIFY(file.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner));
  }
private slots:
  void init() {
    settings = temp.filePath(QUuid::createUuid().toString(QUuid::WithoutBraces) + ".json");
    session = settings + ".session";
  }
  void successfulMountRequiredAndOptInPersists() {
    AutoMountPolicy policy(settings, session); auto v = disk(); QString error;
    QVERIFY(policy.observe({v}, &error)); QVERIFY(!policy.choice(v.driveKey(), {v}).available);
    QVERIFY(!QFileInfo::exists(settings));
    QVERIFY(!policy.setEnabled(v.driveKey(), {v}, true, &error));
    v.mount = "/media/Projects"; // A stale inventory alone is not proof.
    QVERIFY(policy.observe({v}, &error)); QVERIFY(!policy.choice(v.driveKey(), {v}).available);
    v.verifiedMount = true;
    QVERIFY(policy.observe({v}, &error));
    QCOMPARE(policy.choice(v.driveKey(), {v}).state, Qt::Unchecked);
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    AutoMountPolicy another(settings, session);
    v.mount.clear(); v.verifiedMount = false;
    QVERIFY(another.observe({v}, &error));
    QVERIFY(another.choice(v.driveKey(), {v}).available);
    QCOMPARE(another.choice(v.driveKey(), {v}).state, Qt::Checked);
    QCOMPARE(QFile::permissions(settings) & (QFile::ReadGroup | QFile::WriteGroup | QFile::ReadOther | QFile::WriteOther), QFile::Permissions{});
  }
  void systemDiskAndUntriedPartitionsExcluded() {
    auto volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/system","type":"disk","disk-seq":11,"children":[
        {"path":"/dev/system1","type":"part","fstype":"ext4","uuid":"root","mountpoints":["/"]},
        {"path":"/dev/system2","type":"part","fstype":"vfat","uuid":"efi","mountpoints":["/boot/efi"]},
        {"path":"/dev/system3","type":"part","fstype":"ext4","uuid":"spare"}]},
      {"path":"/dev/usb","type":"disk","tran":"usb","disk-seq":12,"children":[
        {"path":"/dev/usb1","type":"part","fstype":"exfat","uuid":"usb-data","mountpoints":["/media/USB"]},
        {"path":"/dev/usb2","type":"part","fstype":"vfat","uuid":"usb-unused"}]}]})");
    for (auto &v : volumes) v.verifiedMount = v.mounted();
    AutoMountPolicy policy(settings, session); QString error;
    QVERIFY(policy.observe(volumes, &error));
    QVERIFY(!policy.choice("/dev/system", volumes).available);
    QCOMPARE(policy.choice("/dev/usb", volumes).volumes, 1);
    QVERIFY(policy.setEnabled("/dev/usb", volumes, true, &error));
    for (auto &v : volumes) { v.mount.clear(); v.verifiedMount = false; }
    Volume selected;
    QVERIFY(policy.next(volumes, &selected, &error));
    QCOMPARE(selected.uuid, QString("usb-data")); QCOMPARE(selected.connection, QString("12"));
    QVERIFY(!policy.next(volumes, &selected, &error));
    for (const auto &v : volumes) if (v.device.startsWith("/dev/system")) QVERIFY(v.system);
  }
  void rememberedMountsRetryOnlyAfterReconnectionOrNewLogin() {
    auto v = disk(); AutoMountPolicy policy(settings, session); remember(policy, v); QString error;
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    Volume selected;
    QVERIFY(policy.next({v}, &selected, &error));
    QVERIFY(!policy.next({v}, &selected, &error));
    AutoMountPolicy restart(settings, session);
    QVERIFY(!restart.next({v}, &selected, &error));
    // DISK-SEQ catches a fast unplug/replug between inventory scans.
    v.connection = "16"; v.device = "/dev/fusion-c1";
    QVERIFY(restart.next({v}, &selected, &error));
    QCOMPARE(selected.device, v.device);
    QVERIFY(!restart.next({v}, &selected, &error));
    QVERIFY(!restart.next({}, &selected, &error));
    QVERIFY(restart.next({v}, &selected, &error));
    AutoMountPolicy nextLogin(settings, session + ".next-login");
    QVERIFY(nextLogin.next({v}, &selected, &error));
  }
  void manualUnmountAndDisableAreRespected() {
    auto v = disk(); AutoMountPolicy policy(settings, session); remember(policy, v); QString error; Volume selected;
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    // Works even if the resident service has not scanned the mounted device yet.
    QVERIFY(policy.suppress(v, &error));
    QVERIFY(!policy.next({v}, &selected, &error));
    v.connection = "17";
    QVERIFY(policy.next({v}, &selected, &error));
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, false, &error));
    v.connection = "18";
    QVERIFY(!policy.next({v}, &selected, &error));
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    v.mount = "/media/Projects";
    QVERIFY(!policy.next({v}, &selected, &error));
    v.mount.clear();
    QVERIFY(!policy.next({v}, &selected, &error)); // Also respects unmounts in other apps.
  }
  void duplicateUuidsAndChangedFilesystemsAreNotMounted() {
    auto v = disk(); AutoMountPolicy policy(settings, session); remember(policy, v); QString error; Volume selected;
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    auto clone = v; clone.device = "/dev/fusion-c1"; clone.driveDevice = "/dev/fusion-c";
    QVERIFY(!policy.next({v, clone}, &selected, &error));
    QVERIFY(!policy.choice(v.driveKey(), {v, clone}).available);
    v.filesystem = "xfs";
    QVERIFY(!policy.next({v}, &selected, &error));
    v.mount = "/media/Projects"; v.verifiedMount = true;
    QVERIFY(policy.observe({v}, &error));
    QCOMPARE(policy.choice(v.driveKey(), {v}).state, Qt::Unchecked);
  }
  void simultaneousWindowsMergeAndInvalidSettingsSurvive() {
    auto a = disk(); auto b = disk("second", "/dev/fusion-c1"); b.driveDevice = "/dev/fusion-c";
    AutoMountPolicy first(settings, session), second(settings, session); QString error;
    remember(first, a); remember(second, b);
    QVERIFY(first.setEnabled(a.driveKey(), {a, b}, true, &error));
    QVERIFY(second.setEnabled(b.driveKey(), {a, b}, true, &error));
    QVERIFY(first.observe({a, b}, &error));
    QCOMPARE(first.choice(a.driveKey(), {a, b}).state, Qt::Checked);
    QCOMPARE(first.choice(b.driveKey(), {a, b}).state, Qt::Checked);
    write(settings, "invalid json");
    QVERIFY(!first.setEnabled(a.driveKey(), {a, b}, false, &error));
    QFile file(settings); QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), QByteArray("invalid json"));
  }
  void checkboxFollowsThePhysicalDriveAndDoesNotEnableUntriedVolumes() {
    auto a = disk(); a.mount = "/media/Projects"; a.verifiedMount = true;
    auto b = disk("untried", "/dev/fusion-b2");
    auto system = disk("root", "/dev/system1"); system.driveDevice = "/dev/system"; system.mount = "/"; system.verifiedMount = true;
    Drives drives(nullptr, false, false, settings, session);
    drives.volumes = {a, b, system}; drives.updateAutoMounts();
    Fusion::Preferences preferences(temp.filePath("view.ini"));
    Browser browser(&preferences, &drives); browser.resize(1200, 1000); browser.show();
    QCheckBox *dataCheck = nullptr, *systemCheck = nullptr;
    for (auto *group : browser.findChildren<QGroupBox *>("physicalDriveGroup")) {
      auto *check = group->findChild<QCheckBox *>("autoMountDrive");
      if (group->property("driveKey").toString() == a.driveKey()) dataCheck = check;
      else systemCheck = check;
    }
    QVERIFY(dataCheck); QVERIFY(systemCheck);
    QVERIFY(dataCheck->isVisible()); QVERIFY(!systemCheck->isVisible());
    dataCheck->click(); QCOMPARE(dataCheck->checkState(), Qt::Checked);
    QCOMPARE(drives.autoMountChoice(a.driveKey()).volumes, 1);
    drives.volumes[0].mount.clear(); emit drives.changed();
    QVERIFY(dataCheck->isVisible()); QCOMPARE(dataCheck->checkState(), Qt::Checked);
    drives.volumes[1].mount = "/media/Second"; drives.volumes[1].verifiedMount = true;
    drives.updateAutoMounts(); emit drives.changed();
    QCOMPARE(dataCheck->checkState(), Qt::PartiallyChecked);
    dataCheck->click(); QCOMPARE(dataCheck->checkState(), Qt::Checked);
    dataCheck->click(); QCOMPARE(dataCheck->checkState(), Qt::Unchecked);
  }
  void backgroundScannerUsesUuidAndNormalAuthorizationWithoutRetryLoop() {
    const auto commandDir = temp.filePath("commands"); QDir().mkpath(commandDir);
    const auto inventory = temp.filePath("inventory.json"), log = temp.filePath("mounts.jsonl");
    write(commandDir + "/lsblk", "#!/usr/bin/python3\nimport os\nprint(open(os.environ['FUSION_TEST_INVENTORY']).read())\n", true);
    write(commandDir + "/udisksctl", "#!/usr/bin/python3\nimport os,sys,json\nwith open(os.environ['FUSION_TEST_MOUNTS'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\nsys.exit(1)\n", true);
    const auto path = qgetenv("PATH");
    qputenv("PATH", commandDir.toUtf8() + ':' + path);
    qputenv("FUSION_TEST_INVENTORY", inventory.toUtf8()); qputenv("FUSION_TEST_MOUNTS", log.toUtf8());
    auto cleanup = qScopeGuard([&] { qputenv("PATH", path); qunsetenv("FUSION_TEST_INVENTORY"); qunsetenv("FUSION_TEST_MOUNTS"); });
    auto v = disk(); AutoMountPolicy policy(settings, session); remember(policy, v); QString error;
    QVERIFY(policy.setEnabled(v.driveKey(), {v}, true, &error));
    write(inventory, R"({"blockdevices":[{"path":"/dev/fusion-b","type":"disk","tran":"usb","disk-seq":15,"children":[{"path":"/dev/fusion-b1","type":"part","fstype":"ext4","uuid":"data-1234"}]}]})");
    auto commands = [&] { QFile file(log); if (!file.open(QIODevice::ReadOnly)) return QList<QByteArray>{}; auto lines = file.readAll().split('\n'); lines.removeAll({}); return lines; };
    {
      Drives scanner(nullptr, true, true, settings, session);
      QTRY_COMPARE(commands().size(), 1);
      QCOMPARE(QJsonDocument::fromJson(commands().first()).array(), QJsonArray({"mount", "-b", "/dev/disk/by-uuid/data-1234"}));
      for (int i = 0; i < 3; ++i) { scanner.refresh(); QTest::qWait(80); }
      QCOMPARE(commands().size(), 1);
      write(inventory, R"({"blockdevices":[]})"); scanner.refresh();
      QTRY_VERIFY(scanner.volumes.isEmpty());
      write(inventory, R"({"blockdevices":[{"path":"/dev/fusion-c","type":"disk","tran":"usb","disk-seq":16,"children":[{"path":"/dev/fusion-c1","type":"part","fstype":"ext4","uuid":"data-1234"}]}]})");
      scanner.refresh(); QTRY_COMPARE(commands().size(), 2);
    }
    const auto count = commands().size(); QTest::qWait(100); QCOMPARE(commands().size(), count);
  }
};
QTEST_MAIN(AutoMountTests)
#include "automount_tests.moc"
