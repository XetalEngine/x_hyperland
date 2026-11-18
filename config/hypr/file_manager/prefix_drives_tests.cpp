#include "prefix_drives.h"
#include "window.h"
#include <QtTest>

namespace {
void write(const QString &path, const QByteArray &contents) {
  QDir().mkpath(QFileInfo(path).absolutePath()); QFile f(path);
  QVERIFY(f.open(QIODevice::WriteOnly)); QCOMPARE(f.write(contents), contents.size());
}
void directory(const QString &path) { QVERIFY(QDir().mkpath(path)); }
}
class PrefixDriveTests : public QObject {
  Q_OBJECT
private slots:
  void registryDefaultWineSteamLibrariesAndDeduplication() {
    QTemporaryDir temp; QVERIFY(temp.isValid());
    PrefixDrives::Locations locations{temp.path()+"/home", temp.path()+"/config", temp.path()+"/data", {}, {}};
    const auto custom = temp.path()+"/Custom prefixes/Office";
    const auto raw = temp.path()+"/Raw wine";
    const auto automatic = locations.data+"/XetalProton/prefixes/My game";
    for (const auto &path : {custom+"/pfx/drive_c", raw+"/drive_c", automatic+"/pfx/drive_c", locations.home+"/.wine/drive_c"}) directory(path);
    const auto alias = temp.path()+"/Alias"; QVERIFY(QFile::link(custom, alias));
    QJsonObject config{{"prefixes", QJsonArray{QJsonObject{{"name","Work apps"},{"path",custom}}, QJsonObject{{"name","Duplicate"},{"path",alias}}, QJsonObject{{"name","Missing"},{"path",temp.path()+"/missing"}}}},
        {"shortcuts", QJsonArray{QJsonObject{{"prefix",raw}},QJsonObject{{"prefix",custom}}}},
        {"last_prefix",custom}};
    write(locations.config+"/XetalProton/config.json", QJsonDocument(config).toJson());
    const auto steam = locations.data+"/Steam", library = temp.path()+"/External Steam Library";
    directory(steam+"/steamapps/compatdata/42/pfx/drive_c");
    directory(library+"/steamapps/compatdata/99/pfx/drive_c");
    directory(library+"/steamapps/compatdata/100/pfx"); // not initialized yet
    write(steam+"/steamapps/libraryfolders.vdf", "\"libraryfolders\" { \"0\" { \"path\" \""+steam.toUtf8()+"\" } // comment\n \"1\" { \"path\" \""+library.toUtf8()+"\" \"apps\" { \"99\" \"0\" } } }");
    write(steam+"/steamapps/appmanifest_42.acf", "\"AppState\" { \"appid\" \"42\" \"name\" \"My Steam Game\" }");
    directory(locations.home+"/.steam"); QVERIFY(QFile::link(steam, locations.home+"/.steam/root"));
    auto result = PrefixDrives::discover(locations); QCOMPARE(result.size(), 6);
    QStringList names; QSet<QString> devices;
    for (const auto &volume : result) { names << volume.name; devices.insert(volume.device); QVERIFY(volume.prefix()); QVERIFY(!volume.mountable()); QVERIFY(!volume.compactCard()); QVERIFY(volume.mounted()); }
    QCOMPARE(devices.size(), result.size()); QVERIFY(names.contains("Work apps (C:)")); QVERIFY(names.contains("My game (C:)"));
    QVERIFY(names.contains("My Steam Game (C:)")); QVERIFY(names.contains("Steam app 99 (C:)"));
    QCOMPARE(result[4].type, QString("steam-prefix")); QCOMPARE(result[5].type, QString("steam-prefix"));
    QVERIFY(QDir(custom).removeRecursively()); result = PrefixDrives::discover(locations); QCOMPARE(result.size(), 5);
  }
  void portableRegistryAndLegacyLibraryFormat() {
    QTemporaryDir temp; PrefixDrives::Locations locations{temp.path()+"/home",temp.path()+"/config",temp.path()+"/data",temp.path()+"/portable",{}};
    const auto prefix=locations.portable+"/prefixes/Portable";
    directory(prefix+"/drive_c");
    write(locations.portable+"/config/config.json", QJsonDocument(QJsonObject{{"prefixes", QJsonArray{QJsonObject{{"path",prefix},{"name","Portable apps"}}}}}).toJson());
    write(locations.config+"/XetalProton/config.json", "{malformed");
    const auto steam=locations.home+"/.var/app/com.valvesoftware.Steam/.local/share/Steam", external=temp.path()+"/library";
    directory(steam+"/steamapps"); directory(external+"/steamapps/compatdata/12/pfx/drive_c");
    write(steam+"/config/libraryfolders.vdf", "\"libraryfolders\" { \"1\" \""+external.toUtf8()+"\" }");
    const auto result=PrefixDrives::discover(locations); QCOMPARE(result.size(), 2); QCOMPARE(result[0].name,QString("Portable apps (C:)"));
  }
  void prefixesOpenAsFoldersAndNeverRunDiskOperations() {
    QTemporaryDir temp; PrefixDrives::Locations locations{temp.path(),temp.path()+"/config",temp.path()+"/data",{},{}};
    directory(temp.path()+"/.wine/drive_c"); Drives drives(nullptr, false); drives.volumes=PrefixDrives::discover(locations);
    QCOMPARE(drives.volumes.size(),1); const auto volume=drives.volumes.first();
    QSignalSpy browse(&drives,&Drives::browse), message(&drives,&Drives::message);
    for (const auto &action : {"mount","unmount","eject","force"}) { drives.operate(volume,action,nullptr); QVERIFY(!drives.busy()); }
    QCOMPARE(message.size(),4); QVERIFY(browse.isEmpty());
    drives.operate(volume,"open",nullptr); QCOMPARE(browse.size(),1); QCOMPARE(browse.first()[0].toUrl(),QUrl::fromLocalFile(volume.mount));
    QStringList actions;
    QTimer::singleShot(0, [&] {
      auto *menu=qobject_cast<QMenu *>(QApplication::activePopupWidget()); QVERIFY(menu);
      for (const auto *action : menu->actions()) if (!action->isSeparator()) actions << action->text();
      menu->close();
    });
    drives.menu(volume,{},nullptr);
    QCOMPARE(actions,QStringList({"Open C: drive","Copy folder path","Properties…"}));
    QVERIFY(QDir(volume.mount).removeRecursively()); drives.operate(volume,"open",nullptr); QCOMPARE(browse.size(),1);
    QVERIFY(message.last()[0].toString().contains("moved or removed"));
  }
  void sidebarGroupsRememberExpansionAndOpenCDrive() {
    QTemporaryDir temp; PrefixDrives::Locations locations{temp.path(),temp.path()+"/config",temp.path()+"/data",{},{}};
    directory(temp.path()+"/.wine/drive_c"); directory(locations.data+"/Steam/steamapps/compatdata/42/pfx/drive_c");
    write(locations.data+"/Steam/steamapps/appmanifest_42.acf", "\"AppState\" { \"name\" \"Portal 2\" }");
    FilesWindow window(Fusion::computerUrl(),false,temp.path()+"/settings.ini"); window.setAttribute(Qt::WA_DeleteOnClose,false);
    window.drives->volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/main","type":"disk","model":"Samsung SSD 970 EVO Plus 2TB","size":2000000000000,"fstype":"ext4","label":"HyperFusion","mountpoints":["/"]},
      {"path":"/dev/main-efi","pkname":"/dev/main","type":"part","size":1024000000,"fstype":"vfat","label":"FUSION_EFI","mountpoints":["/boot/efi"]},
      {"path":"/dev/main-bios","pkname":"/dev/main","type":"part","size":1000000,"parttype":"21686148-6449-6e6f-744e-656564454649"},
      {"path":"/dev/backup","type":"disk","model":"Backup SSD","size":1000000000000,"fstype":"ext4","label":"Projects","mountpoints":["/media/Projects"]},
      {"path":"/dev/sr0","type":"rom","model":"DVD drive","fstype":"iso9660","label":"Archive disc","size":4700000000},
      {"path":"/dev/zip","type":"disk","model":"IOMEGA ZIP 100","rm":1,"fstype":"vfat","size":100000000,"label":"ZIP archive"},
      {"path":"/dev/usb","type":"disk","model":"USB DISK 3.0","tran":"usb","size":16000000000,"fstype":"exfat","label":"Ventoy"},
      {"path":"/dev/usb-efi","pkname":"/dev/usb","type":"part","size":33554432,"fstype":"vfat","label":"VTOYEFI"},
      {"path":"/dev/windows","type":"disk","model":"Samsung SSD 970 EVO Plus 1TB","size":1000000000000,"fstype":"ntfs","label":"Windows_10_Guest"},
      {"path":"/dev/zram0","type":"disk","size":4294967296,"fstype":"swap","label":"zram0"}
    ]})");
    for (auto &v : window.drives->volumes) if (v.mounted()) { v.total=v.size; v.available=v.size/2; v.spaceKnown=true; }
    window.drives->volumes.append(PrefixDrives::discover(locations)); emit window.drives->changed();
    if (window.browser()->previewVisible) window.runAction("preview");
    window.resize(1526,1000); window.show();
    auto *tree=window.findChild<QTreeWidget *>("places");
    auto group=[tree](const QString &name) -> QTreeWidgetItem * {
      for(int i=0;i<tree->topLevelItemCount();++i) if(tree->topLevelItem(i)->text(0)==name)return tree->topLevelItem(i);
      return nullptr;
    };
    QVERIFY(group("Wine & Proton")); QVERIFY(group("Steam prefixes"));
    QCOMPARE(group("This PC")->childCount(),3); QCOMPARE(group("Wine & Proton")->childCount(),1);
    QVERIFY(!group("Wine & Proton")->isExpanded()); group("Wine & Proton")->setExpanded(true);
    emit window.drives->changed(); QVERIFY(group("Wine & Proton")->isExpanded());
    QVERIFY(window.statusBar()->currentMessage().contains("2 prefixes"));
    const auto preview=qEnvironmentVariable("FUSION_DRIVE_PREVIEW");
    if (!preview.isEmpty()) {
      QVERIFY(QDir().mkpath(preview)); QTest::qWait(600);
      QVERIFY(window.grab().save(preview+"/normal.png"));
      auto *shelf = window.browser()->findChild<DriveShelf *>(); QVERIFY(shelf);
      shelf->findChild<QToolButton *>("computerOriginalView")->click(); QTest::qWait(100);
      QVERIFY(window.grab().save(preview+"/original.png"));
      shelf->findChild<QToolButton *>("computerShelfView")->click(); QTest::qWait(100);
      window.resize(2400,1500); QTest::qWait(100); QVERIFY(window.grab().save(preview+"/wide.png"));
      window.drives->volumes.removeIf([](const Volume &v) { return v.device == "/dev/backup" || v.device == "/dev/sr0" || v.device == "/dev/zip"; });
      emit window.drives->changed(); window.resize(1526,1000); QTest::qWait(100);
      QVERIFY(window.grab().save(preview+"/system-and-usb.png"));
      window.resize(720,900); QTest::qWait(100); QVERIFY(window.grab().save(preview+"/narrow.png"));
    }
    const auto volume=PrefixDrives::discover(locations).first();
    window.drives->operate(volume,"open",&window); QTRY_COMPARE(window.browser()->location(),QUrl::fromLocalFile(volume.mount));
    window.close();
  }
};
QTEST_MAIN(PrefixDriveTests)
#include "prefix_drives_tests.moc"
