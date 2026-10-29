#include "wheel_guard.h"
#include <QtTest>
#include <QtWidgets>

class WheelGuardTests : public QObject {
  Q_OBJECT
  static void wheel(QWidget *widget, QPoint angle = QPoint(0, -120), QPoint pixel = {}) {
    const auto position = widget->rect().center();
    QWheelEvent event(position, widget->mapToGlobal(position), pixel, angle,
                      Qt::NoButton, Qt::NoModifier, Qt::NoScrollPhase, false);
    QApplication::sendEvent(widget, &event);
  }
private slots:
  void initTestCase() { new SettingsWheelGuard(qApp); }
  void focusedAndHoveredFieldsCannotChange() {
    QScrollArea area; area.resize(440, 220);
    auto *body = new QWidget; body->setMinimumSize(400, 1100);
    auto *layout = new QVBoxLayout(body);
    auto *spin = new QSpinBox; spin->setValue(42);
    auto *decimal = new QDoubleSpinBox; decimal->setValue(4.2);
    auto *slider = new QSlider(Qt::Horizontal); slider->setValue(42);
    auto *dial = new QDial; dial->setValue(42);
    auto *date = new QDateEdit(QDate(2026, 10, 29));
    auto *combo = new QComboBox; combo->addItems({"one", "two", "three"}); combo->setCurrentIndex(1);
    auto *editable = new QComboBox; editable->setEditable(true); editable->addItems({"one", "two"});
    auto *text = new QLineEdit("unchanged");
    const QList<QWidget *> controls{spin, decimal, slider, dial, date, combo, editable, text};
    for (auto *control : controls) layout->addWidget(control);
    area.setWidget(body); area.show(); QTest::qWait(10);
    QSignalSpy writes(spin, &QSpinBox::valueChanged);
    for (auto *control : controls) {
      for (bool focused : {false, true}) {
        if (focused) control->setFocus(); else control->clearFocus();
        wheel(control); wheel(control, QPoint(0, 120));
        wheel(control, QPoint(-120, 0)); wheel(control, {}, QPoint(0, -24));
      }
    }
    QCOMPARE(spin->value(), 42); QCOMPARE(decimal->value(), 4.2);
    QCOMPARE(slider->value(), 42); QCOMPARE(dial->value(), 42);
    QCOMPARE(date->date(), QDate(2026, 10, 29)); QCOMPARE(combo->currentIndex(), 1);
    QCOMPARE(editable->currentText(), QString("one")); QCOMPARE(text->text(), QString("unchanged"));
    QCOMPARE(writes.count(), 0);
    auto *bar = area.verticalScrollBar(); bar->setValue(0);
    wheel(area.viewport()); const int distance = bar->value(); QVERIFY(distance > 0);
    bar->setValue(0); wheel(spin->findChild<QLineEdit *>());
    QCOMPARE(bar->value(), distance); QCOMPARE(spin->value(), 42);
  }
  void deliberateInputStillWorksWithoutAPage() {
    QSpinBox spin; spin.setValue(42); spin.show();
    wheel(&spin); QCOMPARE(spin.value(), 42);
    QTest::keyClick(&spin, Qt::Key_Up); QCOMPARE(spin.value(), 43);
    spin.selectAll(); QTest::keyClicks(&spin, "27"); QTest::keyClick(&spin, Qt::Key_Return);
    QCOMPARE(spin.value(), 27);
  }
  void popupListsAndLogsStillScroll() {
    QComboBox combo; for (int i = 0; i < 100; ++i) combo.addItem(QString::number(i));
    combo.setStyleSheet("QComboBox {combobox-popup:0;}"); combo.setMaxVisibleItems(5);
    combo.show(); combo.showPopup(); QTest::qWait(10);
    wheel(combo.view()->viewport()); QVERIFY(combo.view()->verticalScrollBar()->value() > 0);
    QCOMPARE(combo.currentIndex(), 0); combo.hidePopup();
    QPlainTextEdit log; log.resize(300, 100);
    for (int i = 0; i < 100; ++i) log.appendPlainText(QString::number(i));
    log.show(); log.verticalScrollBar()->setValue(0); QTest::qWait(10);
    wheel(log.viewport()); QVERIFY(log.verticalScrollBar()->value() > 0);
  }
};
QTEST_MAIN(WheelGuardTests)
#include "wheel_guard_tests.moc"
