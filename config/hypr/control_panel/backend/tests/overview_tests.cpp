#include "../../overview_page.h"
#include "../../../theme/about.hpp"
#include <QtTest>

class OverviewTests : public QObject {
  Q_OBJECT
  QString label(QWidget &page, const char *name) { return page.findChild<QLabel *>(name)->text(); }
private slots:
  void unavailableIsNeverHealthy() {
    FusionOverview::Page page;
    page.servicesResult({}, false);
    QCOMPARE(label(page,"overviewServiceValue"), QString("—"));
    QVERIFY(label(page,"overviewServiceState").contains("unavailable"));
    page.servicesResult("unrecognised", true);
    QVERIFY(label(page,"overviewServiceState").contains("unavailable"));
    page.updatesResult({}, 1);
    QVERIFY(label(page,"overviewUpdateState").contains("unavailable"));
    page.updatesResult({}, 0, false);
    QVERIFY(label(page,"overviewUpdateState").contains("unavailable"));
    page.updatesResult("unexpected output", 2);
    QVERIFY(label(page,"overviewUpdateState").contains("unavailable"));
    page.systemResult({}, false);
    QCOMPARE(label(page,"overviewRamPercent"), QString("—"));
    QVERIFY(page.findChild<QProgressBar *>("overviewRamBar")->isHidden());
  }
  void updateAndServiceResultsRemainReadable() {
    FusionOverview::Page page;
    page.servicesResult("RUNNING: 12\n", true);
    QCOMPARE(label(page,"overviewServiceValue"), QString("12"));
    QVERIFY(label(page,"overviewServiceDetail").contains("No failed"));
    page.servicesResult("RUNNING: 12\nFAILED: example.service\nFAILED: another.service\n", true);
    QCOMPARE(label(page,"overviewServiceValue"), QString("2"));
    QVERIFY(label(page,"overviewServiceDetail").contains("example.service"));
    page.updatesResult("linux 1 -> 2\nmesa 1 -> 2\n", 0);
    QCOMPARE(label(page,"overviewUpdateValue"), QString("2"));
    QVERIFY(label(page,"overviewUpdateDetail").contains("mesa"));
    page.updatesResult({}, 2);
    QCOMPARE(label(page,"overviewUpdateValue"), QString("0"));
    QVERIFY(label(page,"overviewUpdateState").contains("up to date"));
  }
  void storageAndMemoryHandleMissingAndRepeatedData() {
    FusionOverview::Page page;
    page.storageResult("/ 15G 62G 25%\n/ 15G 62G 25%\n/home 5G 10G 50%\ninvalid\n/bad 3G 4G nope\n", true);
    const auto bars = page.findChildren<QProgressBar *>("overviewDiskUsage"); QCOMPARE(bars.size(), 2);
    QCOMPARE(bars[0]->value(), 25); QCOMPARE(bars[1]->value(), 50);
    page.storageResult({}, false);
    QCOMPARE(page.findChildren<QProgressBar *>("overviewDiskUsage").size(), 0);
    QVERIFY(!page.findChild<QLabel *>("overviewStorageMessage")->isHidden());
    page.systemResult("CPU: Example CPU\nGPU: Example GPU\nKERNEL: 7.3\nUPTIME: 10 minutes\nRAM: 2Gi 23Gi\nRAMPCT: 9\n", true);
    QCOMPARE(page.findChild<QProgressBar *>("overviewRamBar")->value(), 9);
    QCOMPARE(label(page,"overviewCpu"), QString("Example CPU"));
    QVERIFY(!label(page,"overviewSystemMeta").contains("up up"));
    page.systemResult("RAMPCT: 999\n", true);
    QCOMPARE(label(page,"overviewRamPercent"), QString("—"));
  }
  void permissionAndRecoveryStates() {
    FusionOverview::Page page;
    page.healthResult("NOAUTH", true);
    QVERIFY(label(page,"overviewHealth").contains("Not checked"));
    page.healthResult("nvme0n1: FAILING", true);
    QVERIFY(label(page,"overviewHealth").contains("FAILING"));
    page.recoveryResult({}, {}, 0);
    QVERIFY(label(page,"overviewRecoveryState").contains("first"));
    page.recoveryResult("backup.iso", "4 GiB", 40);
    QVERIFY(label(page,"overviewRecoveryDetail").contains("fresh copy"));
    page.setBusy(true); QVERIFY(!page.refresh->isEnabled());
    page.setBusy(false); QVERIFY(page.refresh->isEnabled());
  }
  void layoutFitsAndScrollsAtSmallerSizes() {
    FusionOverview::Page page; page.resize(1280,800); page.show(); QTest::qWait(30);
    QCOMPARE(page.property("overviewColumns").toInt(),3);
    for (const QSize size : {QSize(850,650),QSize(600,480),QSize(1280,800)}) {
      page.resize(size); QTest::qWait(30);
      auto *scroll=page.findChild<QScrollArea *>("overviewScroll");
      QCOMPARE(scroll->horizontalScrollBar()->maximum(),0);
      QList<QRect> cards;
      for (const auto *name : {"overviewStorage","overviewServices","overviewUpdates","overviewRecovery"}) {
        auto *card=page.findChild<QFrame *>(name); for (const auto &other:cards) QVERIFY(!card->geometry().intersects(other)); cards << card->geometry();
      }
      if(size.width()==600){QCOMPARE(page.property("overviewColumns").toInt(),1);QVERIFY(scroll->verticalScrollBar()->maximum()>0);}
    }
  }
  void aboutKeepsLogoIdentityClipboardAndCredits() {
    QWidget parent;
    auto *dialog=FusionAbout::show(&parent,FUSION_PROFILE_ROOT,"Control Panel","Example description","Example upstream credit");
    QVERIFY(!dialog->findChild<QLabel *>("aboutEngineLogo")->pixmap().isNull());
    QCOMPARE(label(*dialog,"aboutAuthor"),QString("Xetal — Thiago Costa"));
    QCOMPARE(label(*dialog,"aboutCredits"),QString("Example upstream credit"));
    QCOMPARE(FusionAbout::show(&parent,FUSION_PROFILE_ROOT,"Control Panel",{}),dialog);
    for(const auto *service:{"Discord","Echo"}) {
      auto *copy=dialog->findChild<QPushButton *>(QString("copy%1Username").arg(service));
      copy->click();QCOMPARE(QApplication::clipboard()->text(),QString("xetal"));QCOMPARE(copy->text(),QString("Copied"));
    }
    dialog->close(); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
    QVERIFY(!parent.findChild<QDialog *>("fusionAboutDialog"));
  }
  void aboutFitsWithoutScrollingAfterSmallResize() {
    QWidget parent;
    for (int pointSize : {10, 15}) {
      parent.setFont(QFont("Sans Serif", pointSize));
      auto *dialog=FusionAbout::show(&parent,FUSION_PROFILE_ROOT,"Control Panel",
          "System tools and desktop management for Hyper Fusion.",
          "Powered by the CachyOsTools C++ engine. All system tools and the ISO builder are included in this desktop's source. GPLv3.");
      QCoreApplication::processEvents(); dialog->resize(480,400); QCoreApplication::processEvents();
      QVERIFY(dialog->findChildren<QScrollArea *>().isEmpty());
      QVERIFY(dialog->findChildren<QScrollBar *>().isEmpty());
      for (auto *label : dialog->findChildren<QLabel *>()) {
        if (!label->isVisible()) continue;
        QVERIFY(dialog->rect().contains(QRect(label->mapTo(dialog,QPoint()),label->size())));
        if (label->wordWrap()) QVERIFY2(label->height()>=label->heightForWidth(label->width()),qPrintable(label->text()));
      }
      for (auto *button : dialog->findChildren<QPushButton *>())
        QVERIFY(dialog->rect().contains(QRect(button->mapTo(dialog,QPoint()),button->size())));
      dialog->close();QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
    }
  }
};
QTEST_MAIN(OverviewTests)
#include "overview_tests.moc"
