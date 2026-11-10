#include "core.h"
#include <QtTest>

class ExecutionTests : public QObject {
  Q_OBJECT
private slots:
  void localFileActions() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    for (const auto &suffix : {"AppImage", "APPIMAGE", "sh", "run", "deb", "txt"}) {
      const auto path = temp.path()+"/quotes ' $(literal); file."+suffix;
      QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("fixture\n"); file.close();
      QVERIFY(QFile::setPermissions(path, QFile::ReadOwner|QFile::WriteOwner));
      const auto url = QUrl::fromLocalFile(path);
      const auto kind = Fusion::executionKind(url);
      if (QString(suffix) == "txt") { QVERIFY(kind.isEmpty()); QVERIFY(Fusion::executionCommand(url).isEmpty()); continue; }
      QVERIFY(!kind.isEmpty());
      QCOMPARE(Fusion::executionCommand(url), QStringList({"/usr/bin/python3", Fusion::root()+"/file_manager/execute.py", "--", path}));
      QCOMPARE(Fusion::executeOnOpen(url), kind == "appimage" || kind == "deb");
      auto entries = Fusion::menuDefaults();
      auto first = entries.takeFirst(); first["enabled"] = false; entries.append(first);
      const auto menu = Fusion::executionMenu(entries, {url});
      QCOMPARE(menu.first()["id"].toString(), QString("execute"));
      QCOMPARE(menu.first()["name"].toString(), kind == "deb" ? QString("Install .deb…") : QString("Execute"));
      QVERIFY(menu.first()["enabled"].toBool());
      QVERIFY(QFile::setPermissions(path, QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
      QVERIFY(Fusion::executeOnOpen(url));
    }
  }
  void remoteAndDirectoryNeverExecute() {
    QTemporaryDir temp;
    const auto directory = temp.path()+"/folder.AppImage"; QVERIFY(QDir().mkdir(directory));
    for (const auto &url : {QUrl::fromLocalFile(directory), QUrl("sftp://host/app.AppImage"), QUrl("trash:/app.sh"), QUrl("admin:/opt/app.run")}) {
      QVERIFY(Fusion::executionKind(url).isEmpty());
      QVERIFY(Fusion::executionCommand(url).isEmpty());
      QVERIFY(!Fusion::executeOnOpen(url));
    }
  }
  void extensionlessAppImageRecognizedByHeader() {
    QTemporaryDir temp; const auto path = temp.path()+"/download";
    QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QByteArray::fromHex("7f454c4602010100414902")); file.close();
    QCOMPARE(Fusion::executionKind(QUrl::fromLocalFile(path)), QString("appimage"));
    QVERIFY(Fusion::executeOnOpen(QUrl::fromLocalFile(path)));
  }
};
QTEST_MAIN(ExecutionTests)
#include "execution_tests.moc"
