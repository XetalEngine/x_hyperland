// Disposable native-Wayland integration fixture. Never uses real user folders.
#include "window.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>

int main(int argc,char **argv) {
  QApplication app(argc,argv);app.setApplicationName("Fusion drag probe");app.setStyle("Fusion");
  if(argc!=3)return 2;
  const QString root=QString::fromLocal8Bit(argv[1]), report=QString::fromLocal8Bit(argv[2]);
  FilesWindow window(QUrl::fromLocalFile(root),false,root+"/../preferences.ini");
  window.setWindowTitle("Fusion drag probe");window.resize(650,650);window.show();
  auto* tab=window.browser();
  QTimer timer;
  QObject::connect(&timer,&QTimer::timeout,&window,[&]{
    QJsonObject data;
    for(int row=0;row<tab->proxy->rowCount();++row){
      const auto index=tab->proxy->index(row,0);
      const auto item=tab->model->itemForIndex(tab->proxy->mapToSource(index));
      const auto pos=tab->view()->viewport()->mapTo(&window,tab->view()->visualRect(index).center());
      data[item.name()]=QJsonArray{pos.x(),pos.y()};
    }
    QSaveFile output(report);if(output.open(QIODevice::WriteOnly)){
      output.write(QJsonDocument(data).toJson());output.commit();
    }
  });timer.start(150);
  return app.exec();
}
