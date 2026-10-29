#include "disk_visualizer.h"
#include "disk_layout.h"
#include "native.h"
#include <QtTest>
#include <QtWidgets>
#include <QJsonDocument>
#include <QProcess>

class DiskVisualizerTests final : public QObject {
  Q_OBJECT
private slots:
  void squarifiedAreaPreservesEveryByte() {
    const QVector<double> weights{110, 9000, 500, 0, 13, 88, 100, 1};
    const QRectF bounds(9, 13, 813, 415);
    const auto tiles = DiskLayout::rectangles(weights,bounds);
    const auto total = std::accumulate(weights.begin(),weights.end(),0.);
    for (int i = 0; i < tiles.size(); ++i) {
      const auto area = tiles[i].width() * tiles[i].height();
      QVERIFY(qAbs(area - weights[i] / total * bounds.width() * bounds.height()) < .0001);
      if (!weights[i]) continue;
      QVERIFY(bounds.adjusted(-.0001,-.0001,.0001,.0001).contains(tiles[i]));
      for (int j = i + 1; j < tiles.size(); ++j) {
        auto overlap = tiles[i].intersected(tiles[j]);
        QVERIFY(overlap.width() * overlap.height() < .0001);
      }
    }
    QVERIFY(DiskLayout::rectangles({0,0},bounds)[0].isEmpty());
  }
  void scansLazilyNavigatesAndFits() {
    const auto profile = QDir(QFileInfo(QStringLiteral(__FILE__)).absolutePath()).absoluteFilePath("../../..");
    qputenv("XETAL_HYPR_ROOT",profile.toUtf8());
    QProcess theme;
    theme.start("python3",{profile + "/control_panel/bridge.py","theme"});
    QVERIFY(theme.waitForFinished(5000));
    const auto appearance = QJsonDocument::fromJson(theme.readAllStandardOutput()).object();
    qApp->setStyleSheet(appearance["stylesheet"].toString());
    auto palette = qApp->palette();
    const auto colors = appearance["colors"].toObject();
    for (auto role : {QPalette::Window,QPalette::WindowText,QPalette::Base,QPalette::AlternateBase,QPalette::Text,QPalette::Button,QPalette::ButtonText,QPalette::Highlight,QPalette::HighlightedText,QPalette::Link,QPalette::Midlight,QPalette::PlaceholderText}) {
      const auto key = QMetaEnum::fromType<QPalette::ColorRole>().valueToKey(role);
      const auto color = colors[role == QPalette::Link ? "Accent" : key].toString();
      if (!color.isEmpty()) palette.setColor(role,QColor(color));
    }
    qApp->setPalette(palette);
    QTemporaryDir fixture;
    QVERIFY(fixture.isValid());
    auto put = [&](QString name,int size){
      const auto path = fixture.path() + "/" + name; QDir().mkpath(QFileInfo(path).absolutePath());
      QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); QCOMPARE(file.write(QByteArray(size,'x')),qint64(size));
    };
    put("Projects/Binary Knife/symbols.db",900000);
    put("Projects/Echo/samples.wav",600000);
    put("Projects/Hyper Fusion/desktop.qml",340000);
    put("Videos/desktop-tour.mp4",1200000);
    put("Pictures/wallpaper.png",400000);
    put("Archives/system-backup.tar",700000);
    put("notes.txt",60000); put("readme.md",20000);
    bool authenticated = false;
    DiskVisualizer panel([&]{ authenticated = true; return false; });
    panel.resize(1220,650); panel.show();
    QSignalSpy ready(&panel,&DiskVisualizer::viewReady);
    panel.scanFixture(fixture.path());
    QTRY_VERIFY_WITH_TIMEOUT(ready.count() > 0,10000);
    QVERIFY(!authenticated);
    auto *tree = panel.findChild<QTreeWidget *>("diskTree"); QVERIFY(tree);
    QCOMPARE(tree->topLevelItemCount(),1);
    auto *root = tree->topLevelItem(0);
    QTRY_COMPARE(root->childCount(),5);
    QCOMPARE(root->child(0)->text(0),QString("Projects"));
    QCOMPARE(root->child(4)->text(0),QString("Files"));
    QVERIFY(root->child(0)->data(0,Qt::UserRole+1).toString() == "unloaded");
    root->child(0)->setExpanded(true);
    QTRY_COMPARE(root->child(0)->childCount(),3);
    const auto screenshot = qEnvironmentVariable("DISK_TEST_CAPTURE");
    if (!screenshot.isEmpty()) { QTest::qWait(220); QVERIFY(panel.grab().save(screenshot)); }
    auto *map = panel.findChild<QWidget *>("diskTreemap"); QVERIFY(map); QVERIFY(map->width() > 400); QVERIFY(map->height() > 240);
    const int before = ready.count();
    QTest::mouseClick(tree->viewport(),Qt::LeftButton,Qt::NoModifier,tree->visualItemRect(root->child(4)).center());
    QTest::mouseDClick(tree->viewport(),Qt::LeftButton,Qt::NoModifier,tree->visualItemRect(root->child(4)).center());
    QTRY_VERIFY(ready.count() > before);
    QVERIFY(panel.findChildren<QPushButton *>().size() > 6);
    for (QSize size : {QSize(1220,650),QSize(1050,650)}) {
      panel.resize(size); QTest::qWait(20);
      for (auto *button : panel.findChildren<QPushButton *>()) {
        if (!button->isVisible()) continue;
        const auto position = button->mapTo(&panel,QPoint());
        QVERIFY2(position.x() + button->width() <= panel.width() + 1,qPrintable(button->text()));
      }
    }
  }
};
QTEST_MAIN(DiskVisualizerTests)
#include "disk_visualizer_tests.moc"
