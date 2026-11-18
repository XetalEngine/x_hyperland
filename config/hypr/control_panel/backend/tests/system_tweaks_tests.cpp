#include "system_tweaks_page.h"
#include "window_sizing.h"
#include <QtTest>
#include <QtWidgets>

namespace {
QJsonObject snapshot() {
    QJsonArray rows;
    for (const auto &category : {"Performance", "Security", "Network"}) {
        for (int i = 0; i < 3; ++i) {
            const auto id = QString(category).toLower() + QString::number(i);
            rows.append(QJsonObject{{"id", id}, {"category", category}, {"title", id + " choice"},
                {"description", "A setting with a useful explanation that can wrap on a narrow window."},
                {"details", "Some further information."}, {"current", "off"}, {"saved", ""}, {"supported", true},
                {"choices", QJsonArray{QJsonObject{{"value", "on"}, {"label", "Enabled"}},
                                        QJsonObject{{"value", "off"}, {"label", "Disabled"}}}}});
        }
    }
    return {{"revision", "test-revision"}, {"settings", rows}};
}
void write(const QString &path, const QByteArray &data) {
    QDir().mkpath(QFileInfo(path).path()); QFile file(path);
    if (!file.open(QIODevice::WriteOnly)) qFatal("Could not write test fixture");
    file.write(data);
}
void helper(const QString &root, const QJsonObject &data, bool fail = false) {
    write(root + "/control_panel/snapshot.json", QJsonDocument(data).toJson());
    write(root + "/control_panel/system_tweaks.py", QByteArray(
        "import json,sys,time\nfrom pathlib import Path\n"
        "if sys.argv[1]=='status':\n print(Path(__file__).with_name('snapshot.json').read_text())\n"
        "else:\n time.sleep(.25)\n print(json.dumps(") +
        (fail ? "{'error':'Authentication cancelled'}" : "{'ok':True,'message':'Saved permanently and applied.'}") +
        "))\n sys.exit(" + (fail ? "1" : "0") + ")\n");
}
}

class SystemTweaksTests : public QObject {
    Q_OBJECT
private slots:
    void plainDialogKeepsItsContentSize() {
        HyperPanel::WindowSizing sizing(qApp); qApp->installEventFilter(&sizing);
        QDialog prompt; auto *layout = new QVBoxLayout(&prompt);
        layout->addWidget(new QLabel("Select CPU governor:"));
        auto *choice = new QComboBox; choice->addItems({"performance", "powersave"}); layout->addWidget(choice);
        layout->addWidget(new QDialogButtonBox(QDialogButtonBox::Apply | QDialogButtonBox::Cancel));
        prompt.show(); QTest::qWait(30);
        QVERIFY2(prompt.width() < 600 && prompt.height() < 250, "Ordinary prompt was expanded to full Control Panel size");
        qApp->removeEventFilter(&sizing);
    }

    void oneClickMakesOneRequestAndNoDialog() {
        QTemporaryDir temp; helper(temp.path(), snapshot());
        SystemTweaksPage page(temp.path()); page.resize(1300, 850);
        QSignalSpy requests(&page, &SystemTweaksPage::operationRequested);
        page.show(); auto *refresh = page.findChild<QPushButton *>("tweaksRefresh");
        QTRY_VERIFY_WITH_TIMEOUT(refresh->isEnabled() && page.findChild<QComboBox *>("performance0Choice"), 2000);
        auto *choice = page.findChild<QComboBox *>("performance0Choice"); choice->setCurrentIndex(0);
        QPushButton *apply = nullptr;
        for (auto *button : page.findChildren<QPushButton *>("tweakApply"))
            if (button->property("tweakId") == "performance0") apply = button;
        QVERIFY(apply); requests.clear();
        apply->click(); apply->click();
        QCOMPARE(requests.count(), 1);
        QCOMPARE(requests.first().at(0).toString(), QString("apply"));
        QCOMPARE(requests.first().at(2).toString(), QString("on"));
        QVERIFY(!apply->isEnabled());
        for (auto *widget : QApplication::topLevelWidgets()) QVERIFY(!qobject_cast<QDialog *>(widget));
        QTRY_VERIFY_WITH_TIMEOUT(refresh->isEnabled(), 3000);
        QCOMPARE(requests.count(), 2); // One apply followed by one status refresh.
        QVERIFY(page.findChild<QLabel *>("tweaksMessage")->text().contains("Saved permanently"));
    }

    void cancellationKeepsDraftAndAllowsRetry() {
        QTemporaryDir temp; helper(temp.path(), snapshot(), true);
        SystemTweaksPage page(temp.path()); page.show();
        QTRY_VERIFY_WITH_TIMEOUT(page.findChild<QComboBox *>("performance0Choice"), 2000);
        auto *choice = page.findChild<QComboBox *>("performance0Choice"); choice->setCurrentIndex(0);
        auto *button = choice->parentWidget()->findChild<QPushButton *>("tweakApply");
        button->click();
        QTRY_VERIFY_WITH_TIMEOUT(button->isEnabled(), 2000);
        QCOMPARE(choice->currentData().toString(), QString("on"));
        QVERIFY(page.findChild<QLabel *>("tweaksMessage")->text().contains("Authentication cancelled"));
    }

    void refreshPreservesUnappliedDraft() {
        QTemporaryDir temp; helper(temp.path(), snapshot());
        SystemTweaksPage page(temp.path()); page.display(snapshot());
        auto *choice = page.findChild<QComboBox *>("performance0Choice"); choice->setCurrentIndex(0);
        page.display(snapshot());
        QCOMPARE(choice->currentData().toString(), QString("on"));
    }

    void ptraceMode3MakesRebootTimingVisibleBeforeApplying() {
        QTemporaryDir temp; auto data = snapshot(); auto rows = data["settings"].toArray();
        auto row = rows[0].toObject(); row["id"] = "ptrace"; row["category"] = "Security";
        row["current"] = "1";
        row["choices"] = QJsonArray{QJsonObject{{"value", "1"}, {"label", "Child processes"}},
                                    QJsonObject{{"value", "3"}, {"label", "No tracing"}}};
        rows[0] = row; data["settings"] = rows;
        helper(temp.path(), data); SystemTweaksPage page(temp.path()); page.display(data);
        auto *choice = page.findChild<QComboBox *>("ptraceChoice");
        choice->setCurrentIndex(1);
        QCOMPARE(choice->parentWidget()->findChild<QPushButton *>("tweakApply")->text(), QString("Save for reboot"));
        QVERIFY(choice->parentWidget()->findChild<QLabel *>("tweakNote")->text().contains("after reboot"));
    }

    void searchAndResponsiveLayout() {
        QTemporaryDir temp; helper(temp.path(), snapshot());
        SystemTweaksPage page(temp.path()); page.resize(1400, 850); page.show();
        QTRY_VERIFY_WITH_TIMEOUT(page.findChild<QComboBox *>("performance0Choice"), 2000);
        auto *search = page.findChild<QLineEdit *>("tweaksSearch");
        auto *tabs = page.findChild<QTabWidget *>("systemTweaksCategories");
        search->setText("security1");
        QCOMPARE(tabs->tabText(tabs->currentIndex()), QString("Security"));
        int visible = 0;
        for (auto *box : page.findChildren<QWidget *>("tweakCard")) if (box->isVisible()) ++visible;
        QCOMPARE(visible, 1);
        search->clear(); page.selectCategory("Performance"); page.resize(780, 800); QTest::qWait(30);
        auto *a = page.findChild<QComboBox *>("performance0Choice")->parentWidget();
        auto *b = page.findChild<QComboBox *>("performance1Choice")->parentWidget();
        QCOMPARE(a->x(), b->x()); QVERIFY(b->y() > a->y());
        for (auto *scroll : page.findChildren<QScrollArea *>("tweaksScroll"))
            if (scroll->isVisible()) QCOMPARE(scroll->horizontalScrollBar()->maximum(), 0);
        for (int i = 0; i < 20; ++i) { search->setText("no matches"); search->clear(); }
        QVERIFY(a->parentWidget()->height() < 3000); // No hidden rows accumulating at row 1000.
    }

    void preview() {
        const auto source = qEnvironmentVariable("HYPERFUSION_TEST_PREVIEW_SNAPSHOT");
        if (source.isEmpty()) QSKIP("Optional full-catalog visual preview");
        QFile input(source); QVERIFY(input.open(QIODevice::ReadOnly));
        auto data = QJsonDocument::fromJson(input.readAll()).object();
        QFile theme(qEnvironmentVariable("HYPERFUSION_TEST_PREVIEW_THEME"));
        if (theme.open(QIODevice::ReadOnly)) {
            const auto settings = QJsonDocument::fromJson(theme.readAll()).object(); QPalette palette;
            const auto colors = settings["colors"].toObject(); const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
            for (auto it = colors.begin(); it != colors.end(); ++it) {
                const int role = roles.keyToValue(it.key().toUtf8());
                if (role >= 0) palette.setColor(QPalette::All, QPalette::ColorRole(role), QColor(it.value().toString()));
            }
            qApp->setPalette(palette); qApp->setStyleSheet(settings["stylesheet"].toString());
            qApp->setFont(QFont(settings["font"].toString(), 10));
        }
        QTemporaryDir temp; helper(temp.path(), data);
        SystemTweaksPage page(temp.path()); page.resize(1380, 850); page.show();
        QTRY_VERIFY_WITH_TIMEOUT(page.findChild<QComboBox *>("cpu_governorChoice"), 3000);
        QTest::qWait(100);
        const auto out = qEnvironmentVariable("HYPERFUSION_TEST_PREVIEW_DIR"); QDir().mkpath(out);
        QVERIFY(page.grab().save(out+"/performance.png"));
        page.selectCategory("Security"); QTest::qWait(30); QVERIFY(page.grab().save(out+"/security.png"));
        page.resize(780, 800); QTest::qWait(30); QVERIFY(page.grab().save(out+"/narrow.png"));
    }
};
QTEST_MAIN(SystemTweaksTests)
#include "system_tweaks_tests.moc"
