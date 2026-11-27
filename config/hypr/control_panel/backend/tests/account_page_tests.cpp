#include "../../account_picker.h"
#include "../../accounts_page.h"
#include <QtTest>

class AccountTests : public QObject {
  Q_OBJECT
  QString root;
private slots:
  void initTestCase(){root=qEnvironmentVariable("XETAL_HYPR_ROOT");QVERIFY(QFileInfo::exists(root+"/account_avatars/assets/icons.json"));}
  void gallerySearchCollectionsAndCancel(){
    FusionAccounts::Picker picker(root,root+"/theme/assets/account.gif");picker.show();QTest::qWait(20);
    auto *list=picker.findChild<QListWidget *>("avatarGallery");QCOMPARE(list->count(),301);
    auto *search=picker.findChild<QLineEdit *>("avatarSearch");search->setText("red panda");
    int visible=0;QListWidgetItem *found=nullptr;
    for(int i=0;i<list->count();++i)if(!list->item(i)->isHidden()){visible++;found=list->item(i);}
    QCOMPARE(visible,1);QCOMPARE(found->text(),QString("Red panda"));
    list->setCurrentItem(found);QCOMPARE(picker.findChild<QLabel *>("avatarChoiceName")->text(),QString("Red panda"));
    search->setText("no such picture");
    auto *buttons=picker.findChild<QDialogButtonBox *>();QVERIFY(!buttons->button(QDialogButtonBox::Ok)->isEnabled());
    buttons->button(QDialogButtonBox::Cancel)->click();QCOMPARE(picker.result(),int(QDialog::Rejected));QVERIFY(picker.selectedId().isEmpty());
  }
  void acceptReturnsVerifiedIdentity(){
    FusionAccounts::Picker picker(root,root+"/account_avatars/assets/fedora.png");
    picker.findChild<QDialogButtonBox *>()->button(QDialogButtonBox::Ok)->click();
    QCOMPARE(picker.result(),int(QDialog::Accepted));QCOMPARE(picker.selectedId(),QString("fedora"));
  }
  void accountSelectionAndProtectedUsers(){
    FusionAccounts::Page page(root);page.resize(1100,720);
    const QStringList rows[]={ {"root","0","/root","/bin/bash","root"},
      {"demo",QString::number(getuid()),"/home/demo","/bin/bash","demo wheel video"},
      {"guest",QString::number(getuid()+1),"/home/guest","/bin/bash","guest"} };
    page.table->setRowCount(3);
    for(int row=0;row<3;++row)for(int col=0;col<5;++col)page.table->setItem(row,col,new QTableWidgetItem(rows[row][col]));
    page.table->selectRow(1);page.rebuilt();page.show();QTest::qWait(20);
    QCOMPARE(page.findChild<QLabel *>("usersSelectedName")->text(),QString("demo"));QVERIFY(!page.remove->isEnabled());
    auto *list=page.findChild<QListWidget *>("accountsList");list->setCurrentRow(2);QVERIFY(page.remove->isEnabled());
    QCOMPARE(page.table->currentRow(),2);QCOMPARE(page.findChild<QLabel *>("usersSelectedName")->text(),QString("guest"));
    list->setCurrentRow(0);QVERIFY(!page.remove->isEnabled());
    for(const auto &size:{QSize(1100,720),QSize(960,640)}){
      page.resize(size);QTest::qWait(10);QVERIFY(page.icon->visibleRegion().contains(page.icon->rect()));
      QVERIFY(page.add->visibleRegion().contains(page.add->rect()));
    }
  }
};
QTEST_MAIN(AccountTests)
#include "account_page_tests.moc"
