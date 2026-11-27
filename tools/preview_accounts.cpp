// Actual Users & Groups widgets with sample accounts; never invokes an action.
#include "../config/hypr/control_panel/accounts_page.h"
#include "../config/hypr/control_panel/account_picker.h"
int main(int argc,char **argv){
  QApplication app(argc,argv);if(argc!=4)return 2;
  QFile style(argv[2]);if(style.open(QIODevice::ReadOnly))app.setStyleSheet(QString::fromUtf8(style.readAll()));
  QFile colors(QString(argv[2])+".json");if(colors.open(QIODevice::ReadOnly)){
    const auto values=QJsonDocument::fromJson(colors.readAll()).object();QPalette palette;const auto roles=QMetaEnum::fromType<QPalette::ColorRole>();
    for(auto it=values.begin();it!=values.end();++it){int role=roles.keyToValue(it.key().toLatin1().constData());if(role>=0)palette.setColor(QPalette::All,QPalette::ColorRole(role),QColor(it.value().toString()));}
    app.setPalette(palette);
  }
  const QString root=argv[1],out=argv[3];QDir().mkpath(out);
  FusionAccounts::Page page(root);page.resize(1200,780);
  const QStringList rows[]={ {"alex",QString::number(getuid()),"/home/alex","/bin/bash","alex wheel video"},
    {"studio",QString::number(getuid()+1),"/home/studio","/bin/bash","studio audio"},
    {"root","0","/root","/bin/bash","root"} };
  page.table->setRowCount(3);
  for(int row=0;row<3;++row)for(int col=0;col<5;++col)page.table->setItem(row,col,new QTableWidgetItem(rows[row][col]));
  for(int row=0;row<3;++row)page.table->item(row,0)->setIcon(QIcon(root+"/account_avatars/assets/"+QStringList{"red-panda.png","astronaut.png","original.gif"}[row]));
  page.table->selectRow(0);page.rebuilt();page.show();
  QTimer::singleShot(150,&app,[&]{
    page.grab().save(out+"/users-groups.png");page.hide();
    auto *picker=new FusionAccounts::Picker(root,root+"/account_avatars/assets/red-panda.png");picker->show();
    picker->findChild<QComboBox *>("avatarCategory")->setCurrentText("Animal friends");
    QTimer::singleShot(150,&app,[&,picker]{picker->grab().save(out+"/avatar-picker.png");picker->close();app.quit();});
  });return app.exec();
}
