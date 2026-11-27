#include "appearance.h"
#include "properties.h"
#include "window.h"
#include <KPropertiesDialog>
#include <QTabBar>
#include <QtTest>

class PropertiesTests : public QObject {
  Q_OBJECT
  QString base;
  QStringList fileUris;
  static void write(const QString &path, const QByteArray &bytes) {
    QSaveFile file(path);
    QVERIFY(file.open(QIODevice::WriteOnly));
    QCOMPARE(file.write(bytes), bytes.size());
    QVERIFY(file.commit());
  }
private slots:
  void initTestCase() {
    base = Fusion::root();
    QDir().mkpath(base + "/theme");
    QDir().mkpath(base + "/file_manager/state");
    QFile::copy(QFileInfo(QString::fromUtf8(__FILE__)).absolutePath() + "/computer.svg",
                base + "/file_manager/computer.svg");
    QDir().mkpath(base + "/Projects");
    write(base + "/notes # 100% café.txt", "keep this file\n");
    write(base + "/studio.desktop", "[Desktop Entry]\nType=Application\nName=Studio\nExec=true\nIcon=folder\n");
    for (const auto &name : {"Projects", "notes # 100% café.txt", "studio.desktop"})
      fileUris << QUrl::fromLocalFile(base + '/' + name).toString(QUrl::FullyEncoded);
    write(base + "/theme/color", "#825c76");
    write(base + "/file_manager/appearance.py", R"(
import json,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
time.sleep(.15)
theme=sys.argv[-1]
color='#397fad' if theme=='pinned' else (root/'theme/color').read_text()
print(json.dumps(dict(theme=theme,design=theme,iconSearchPaths=['/usr/share/icons'],
 iconTheme='Papirus-Dark',iconFallbackTheme='hicolor',colors=dict(Window=color,Text='#eeeeee',
 WindowText='#eeeeee',ButtonText='#eeeeee',Disabled='#888888',Accent=color),font='Noto Sans',
 stylesheet='QPushButton { padding: 8px; border-radius: 7px; background: '+color+'; }')))
)");
  }
  void desktopProperties_data() {
    QTest::addColumn<int>("selection");
    QTest::newRow("folder") << 0;
    QTest::newRow("file-with-literal-characters") << 1;
    QTest::newRow("desktop-shortcut") << 2;
    QTest::newRow("multiple-items") << 3;
  }
  void desktopProperties() {
    QFETCH(int, selection);
    // Each production Properties window has its own QApplication. Here, wait
    // for its explicit destroyed/quit path before reusing the application.
    QEventLoopLocker keepApplication;
    qApp->setStyleSheet({});
    bool sawDialog = false, styledOnFirstShow = false, correctItems = false, timedOut = false;
    QStringList tabs;
    QSize size;
    bool allTabsFit = false;
    const QStringList uris = selection < 3 ? QStringList{fileUris[selection]} : fileUris.mid(1);
    QTimer observer, deadline;
    connect(&observer, &QTimer::timeout, this, [&] {
      for (auto *widget : QApplication::topLevelWidgets()) {
        auto *dialog = qobject_cast<KPropertiesDialog *>(widget);
        if (!dialog || !dialog->isVisible()) continue;
        sawDialog = true;
        styledOnFirstShow = qApp->styleSheet().contains("#825c76");
        correctItems = dialog->items().size() == uris.size();
        if (auto *bar = dialog->findChild<QTabBar *>()) {
          allTabsFit = bar->width() >= bar->sizeHint().width();
          for (int i = 0; i < bar->count(); ++i) tabs << bar->tabText(i).remove('&');
        }
        size = dialog->size();
        dialog->reject();
        observer.stop();
      }
    });
    connect(&deadline, &QTimer::timeout, this, [&] { timedOut = true; qApp->quit(); });
    observer.start(20); deadline.setSingleShot(true); deadline.start(8000);
    QCOMPARE(Fusion::runProperties(*qApp, uris), 0);
    QVERIFY(!timedOut);
    QVERIFY(sawDialog);
    QVERIFY(styledOnFirstShow);
    QVERIFY(correctItems);
    QVERIFY(allTabsFit);
    QCOMPARE(qApp->desktopFileName(), QString("xetal-file-properties"));
    QVERIFY(tabs.contains("General"));
    QVERIFY(tabs.contains("Permissions"));
    if (selection == 2) { QVERIFY(tabs.contains("Application")); QVERIFY(tabs.contains("Checksums")); }
    QVERIFY2(size.width() < 1000 && size.height() < 850, qPrintable(QString::number(size.width())+'x'+QString::number(size.height())));
    QFile file(base + "/notes # 100% café.txt"); QVERIFY(file.open(QIODevice::ReadOnly));
    QCOMPARE(file.readAll(), QByteArray("keep this file\n"));
    QVERIFY(QFileInfo::exists(base + "/studio.desktop"));
  }
  void filesAndDesktopSharePinnedThemeAndLiveUpdates() {
    const auto settingsPath = base + "/file_manager/state/settings.ini";
    Fusion::Preferences settings(settingsPath);
    settings.settings.setValue("appearance/theme", "pinned"); settings.settings.sync();
    FilesWindow window(QUrl::fromLocalFile(base + "/Projects"), false, settingsPath);
    QTRY_COMPARE(window.property("fusionTheme").toString(), QString("pinned"));
    const auto filesStyle = qApp->styleSheet();
    Fusion::Appearance desktopAppearance(settingsPath);
    QSignalSpy loaded(&desktopAppearance, &Fusion::Appearance::initialized);
    QSignalSpy changed(&desktopAppearance, &Fusion::Appearance::changed);
    QTRY_COMPARE(loaded.count(), 1);
    QCOMPARE(qApp->styleSheet(), filesStyle);
    QCOMPARE(qApp->property("xetalThemeDesign").toString(), QString("pinned"));
    QPointer<KPropertiesDialog> dialog = Fusion::propertiesDialog({KFileItem(QUrl(fileUris[0]))});
    dialog->show();
    // Atomic settings/theme writes must update an already-open dialog.
    settings.settings.setValue("appearance/theme", "follow"); settings.settings.sync();
    QTRY_VERIFY(qApp->styleSheet().contains("#825c76"));
    QTRY_COMPARE(window.property("fusionTheme").toString(), QString("follow"));
    QVERIFY(!qApp->property("xetalThemeDesign").isValid());
    write(base + "/theme/color", "#bd8656");
    QTRY_VERIFY(qApp->styleSheet().contains("#bd8656"));
    QTRY_VERIFY(changed.count() >= 3);
    QVERIFY(dialog->isVisible());
    dialog->reject();
    QTRY_VERIFY(dialog.isNull());
  }
  void invalidUrlsDoNotOpenAWindow() {
    for (const auto &values : QList<QStringList>{{}, {"relative"}, {"file:relative"}, {fileUris[0], "bad"}}) {
      QVERIFY(!Fusion::openProperties(values));
      QCOMPARE(Fusion::runProperties(*qApp, values), 1);
    }
  }
  void failedAppearanceStillCompletes() {
    write(base + "/file_manager/appearance.py", "raise RuntimeError('fixture failure')\n");
    Fusion::Appearance appearance;
    QSignalSpy loaded(&appearance, &Fusion::Appearance::initialized);
    QSignalSpy changed(&appearance, &Fusion::Appearance::changed);
    QTRY_COMPARE(loaded.count(), 1);
    QCOMPARE(changed.count(), 0);
  }
};

int main(int argc, char **argv) {
  QTemporaryDir temporary;
  if (!temporary.isValid()) return 1;
  qputenv("HOME", temporary.path().toUtf8());
  qputenv("XETAL_FILES_ROOT", temporary.path().toUtf8());
  for (const auto &key : {"XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"}) {
    const auto path = temporary.path() + '/' + key;
    QDir().mkpath(path);
    QFile::setPermissions(path, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    qputenv(key, path.toUtf8());
  }
  qputenv("DBUS_SYSTEM_BUS_ADDRESS", ("unix:path=" + temporary.path() + "/no-system-bus").toUtf8());
  qputenv("XDG_DATA_DIRS", "/usr/local/share:/usr/share");
  qunsetenv("HYPRLAND_INSTANCE_SIGNATURE");
  QApplication app(argc, argv);
  app.setApplicationName("Fusion Properties Test");
  app.setStyle("Fusion");
  PropertiesTests tests;
  return QTest::qExec(&tests, argc, argv);
}
#include "properties_tests.moc"
