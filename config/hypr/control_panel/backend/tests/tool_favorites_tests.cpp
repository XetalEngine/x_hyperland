#include "tool_tile.h"
#include "tool_favorites.h"
#include <QtTest>

class ToolFavoritesTests final : public QObject {
  Q_OBJECT
private slots:
  void shutdownStopsReadCallbacksAndFinishesAnAtomicEdit() {
    QTemporaryDir fixture; QDir().mkpath(fixture.filePath("control_panel"));
    QFile helper(fixture.filePath("control_panel/bridge.py")); QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json,sys,time
from pathlib import Path
root=Path(__file__).parent.parent;data=json.load(sys.stdin)
if sys.argv[1]=='tool-favorite':
 (root/'editing').touch();time.sleep(.15);(root/'saved').write_text(data['id'])
elif (root/'slow-read').exists():
 (root/'reading').touch();time.sleep(2)
print(json.dumps(dict(favorites=[])))
)PY"); helper.close();
    auto *editor = new ToolFavorites(fixture.path()); QTRY_VERIFY(editor->available());
    editor->setFavorite("rdp", true); QTRY_VERIFY(QFile::exists(fixture.filePath("editing")));
    delete editor;
    QFile saved(fixture.filePath("saved")); QVERIFY(saved.open(QIODevice::ReadOnly)); QCOMPARE(saved.readAll(),QByteArray("rdp"));
    QFile slow(fixture.filePath("slow-read")); QVERIFY(slow.open(QIODevice::WriteOnly)); slow.close();
    auto *reader = new ToolFavorites(fixture.path()); QSignalSpy changes(reader, &ToolFavorites::changed);
    QTRY_VERIFY(QFile::exists(fixture.filePath("reading"))); delete reader;
    QCOMPARE(changes.count(),0);
  }
  void starClickKeyboardAndExternalUnpin() {
    QTemporaryDir fixture;
    QVERIFY(fixture.isValid());
    QDir().mkpath(fixture.filePath("control_panel"));
    QDir().mkpath(fixture.filePath("launcher"));
    QFile helper(fixture.filePath("control_panel/bridge.py"));
    QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json,sys,time
from pathlib import Path
root=Path(__file__).parent.parent
path=root/'launcher/favorites.json'
data=json.load(sys.stdin)
saved=json.loads(path.read_text()) if path.exists() else []
if sys.argv[1]=='tool-favorite':
    with (root/'calls').open('a') as stream: stream.write(data['id']+'\n')
    time.sleep(.15)
    if data['enabled'] and data['id'] not in saved:saved.append(data['id'])
    elif not data['enabled']:saved=[value for value in saved if value!=data['id']]
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(saved));temp.replace(path)
print(json.dumps({'favorites':saved}))
)PY");
    helper.close();
    ToolFavorites favorites(fixture.path());
    ToolButton tile({{"id", "network"}, {"title", "Network"},
                     {"description", "Wi-Fi, interfaces, bridges and ports"},
                     {"icon", "network-workgroup"}}, nullptr);
    connect(&favorites, &ToolFavorites::changed, &tile, [&] {
      tile.setFavoriteState(favorites.contains("network"), favorites.available(),
                            favorites.pending("network"), favorites.error());
    });
    connect(tile.favoriteButton(), &QAbstractButton::clicked, &favorites,
            [&](bool checked) { favorites.setFavorite("network", checked); });
    QSignalSpy opened(&tile, &QPushButton::clicked);
    QSignalSpy errors(&favorites, &ToolFavorites::failed);
    tile.resize(350, 72);
    tile.show();
    auto *star = tile.favoriteButton();
    QTRY_VERIFY(star->isEnabled());
    QVERIFY(tile.rect().contains(star->geometry()));
    QTest::mouseClick(star, Qt::LeftButton);
    QVERIFY(!star->isEnabled());
    QTest::mouseClick(star, Qt::LeftButton); // An in-flight save cannot toggle twice.
    QTest::mouseClick(&tile, Qt::LeftButton, Qt::NoModifier, star->geometry().center());
    QTRY_VERIFY(star->isEnabled());
    QVERIFY(star->isChecked());
    QCOMPARE(opened.count(), 0);
    QFile calls(fixture.filePath("calls"));
    QVERIFY(calls.open(QIODevice::ReadOnly));
    QCOMPARE(calls.readAll(), QByteArray("network\n"));
    QVERIFY(star->toolTip().contains("Remove Network"));
    star->setFocus();
    QTest::keyClick(star, Qt::Key_Space);
    QTRY_VERIFY(star->isEnabled());
    QVERIFY(!star->isChecked());
    QCOMPARE(opened.count(), 0);
    QTest::mouseClick(&tile, Qt::LeftButton, Qt::NoModifier, QPoint(90, 25));
    QCOMPARE(opened.count(), 1);
    // A second app changes the shared file with atomic replacement.
    for (const auto &contents : {QByteArray("[\"network\"]"), QByteArray("[]")}) {
      QSaveFile external(fixture.filePath("launcher/favorites.json"));
      QVERIFY(external.open(QIODevice::WriteOnly));
      external.write(contents);
      QVERIFY(external.commit());
      QTRY_COMPARE(star->isChecked(), contents.contains("network"));
    }
    QCOMPARE(errors.count(), 0);
  }
};
QTEST_MAIN(ToolFavoritesTests)
#include "tool_favorites_tests.moc"
