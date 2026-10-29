#include "log_reader.h"
#include <QtTest>
#include <QProcess>
#include <QTemporaryFile>

class LogReaderTests : public QObject {
    Q_OBJECT
private slots:
    void reportsUseDecodersAndCannotTailBinaryRecords() {
        for (const auto &path : {"/var/log/wtmp", "/var/log/btmp", "/var/log/lastlog"}) {
            const auto plan = LogReader::command(path, 100, true);
            QVERIFY(plan.program != "tail");
            QVERIFY(!plan.follow);
        }
        QCOMPARE(LogReader::command("/var/log/wtmp", 42, true).arguments,
                 QStringList({"-w", "-n", "42", "-f", "/var/log/wtmp"}));
        QCOMPARE(LogReader::command("/var/log/btmp", 10, false).program, QString("lastb"));
        const auto inxi = LogReader::command("inxi -M", 100, true);
        QCOMPARE(inxi.arguments, QStringList({"-M", "-c", "0"}));
        QVERIFY(!inxi.follow);
    }
    void stripsTerminalAndIrcFormattingWithoutLosingLayout() {
        const QString data = QString::fromUtf8("\x03" "12Machine:\x0f\n  \x1b[31mModel\x1b[0m\tCPU\r\n"
                                              "\x1b]8;;https://example.test\x1b\\link\x1b]8;;\x1b\\\x07");
        QCOMPARE(LogReader::plain(data), QString("Machine:\n  Model\tCPU\nlink"));
    }
    void fragmentedUtf8AndEscapeCodesArePreserved() {
        const QByteArray bytes = QString::fromUtf8("\x1b[31mTempérature ⚙\x1b[0m\nlast line").toUtf8();
        LogReader::Stream stream;
        QString result;
        for (const char byte : bytes) result += stream.take(QByteArray(1, byte));
        result += stream.take({}, true);
        QCOMPARE(result, QString::fromUtf8("Température ⚙\nlast line"));
    }
    void filterIsLiteralAndCaseInsensitive() {
        LogReader::Stream stream("[ERROR]");
        QCOMPARE(stream.take("[error] one\nERROR two\n[ER"), QString("[error] one\n"));
        QCOMPARE(stream.take("ROR] three"), QString());
        QCOMPARE(stream.take({}, true), QString("[ERROR] three"));
    }
    void tailUsesTheActualFileAndKeepsWhitespace() {
        QTemporaryFile file;
        QVERIFY(file.open());
        file.write("first\n  error: one\nlast\n"); file.flush();
        const auto plan = LogReader::command(file.fileName(), 2, false);
        QProcess process;
        process.start(plan.program, plan.arguments);
        QVERIFY(process.waitForFinished(3000));
        QCOMPARE(process.exitCode(), 0);
        LogReader::Stream stream;
        QCOMPARE(stream.take(process.readAllStandardOutput(), true), QString("  error: one\nlast\n"));
        QCOMPARE(LogReader::command("/var/log/a file;literal", 10, true).arguments.last(), QString("/var/log/a file;literal"));
    }
    void journalBootAndFollowingShareTheReader() {
        const auto plan = LogReader::command("/var/log/journal/", 50, true, -2);
        QCOMPARE(plan.program, QString("journalctl"));
        QVERIFY(plan.follow);
        QVERIFY(plan.arguments.contains("--no-pager"));
        QVERIFY(plan.arguments.contains("-f"));
        QCOMPARE(plan.arguments[plan.arguments.indexOf("-b") + 1], QString("-2"));
    }
};
QTEST_GUILESS_MAIN(LogReaderTests)
#include "log_reader_tests.moc"
