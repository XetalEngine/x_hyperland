#include "kernel_catalog.h"
#include <QtTest>

class KernelCatalogTests : public QObject {
    Q_OBJECT
private slots:
    void searchesAllColumnsAndNeverInstallsHiddenSelection() {
        QTemporaryDir directory;
        QFile script(directory.filePath("catalog.py")); QVERIFY(script.open(QIODevice::WriteOnly));
        script.write("import json\nprint(json.dumps({'kernels': ["
                     "{'package':'linux','version':'7.2.14','repo':'core','description':'Standard Linux kernel','headers':'linux-headers','method':'pacman'},"
                     "{'package':'linux-cachyos-bore','version':'7.2.14','repo':'cachyos','description':'BORE scheduler','method':'pacman'}]}))\n");
        script.close();
        KernelCatalog dialog(script.fileName()); dialog.show();
        auto *table = dialog.findChild<QTreeWidget *>("kernelCatalog");
        auto *search = dialog.findChild<QLineEdit *>("kernelSearch");
        QTRY_COMPARE(table->topLevelItemCount(), 5);
        table->setCurrentItem(table->topLevelItem(0));
        QCOMPARE(KernelCatalog::installCommand(dialog.selection()), QString("sudo pacman -Syu --needed -- 'core/linux' 'core/linux-headers'"));
        search->setText("BORE cachyos");
        QVERIFY(table->topLevelItem(0)->isHidden()); QVERIFY(!table->topLevelItem(1)->isHidden());
        QVERIFY(dialog.selection().isEmpty());
        search->clear(); QVERIFY(!table->topLevelItem(0)->isHidden());
        QVERIFY(KernelCatalog::installCommand({{"package","linux;reboot"},{"method","pacman"},{"repo","core"}}).isEmpty());
        QVERIFY(KernelCatalog::installCommand({{"package","linux"},{"method","pacman"},{"repo","core'"}}).isEmpty());
        dialog.populate({{"kernels", QJsonArray()}, {"kvm_kernel", QJsonObject{{"release", "7.2.11-arch1-1"}, {"installed", false}}}});
        search->setText("7.2.11");
        table->setCurrentItem(table->topLevelItem(0));
        QVERIFY(!table->topLevelItem(0)->isHidden());
        QVERIFY(KernelCatalog::compatibleKernel(dialog.selection()));
        QCOMPARE(dialog.selection()["kernel"].toString(), QString("7.2.11-arch1-1"));
        QVERIFY(!KernelCatalog::compatibleKernel({{"method","compatible-kvm"}, {"kernel","7.2.11-arch1-1;reboot"}}));
    }
};
QTEST_MAIN(KernelCatalogTests)
#include "kernel_catalog_tests.moc"
