// Render the production widgets with fixture data. No system actions run.
#include "../config/hypr/control_panel/overview_page.h"
#include "../config/hypr/theme/about.hpp"
#include "../config/hypr/theme/icon_theme.hpp"
int main(int argc, char **argv) {
  QApplication app(argc, argv); if(argc != 4) return 2;
  const QString root=argv[1], stylePath=argv[2], output=argv[3]; QDir().mkpath(output);
  QFile style(stylePath); if(style.open(QIODevice::ReadOnly)) app.setStyleSheet(QString::fromUtf8(style.readAll()));
  QFile colors(stylePath+".json"); if(colors.open(QIODevice::ReadOnly)) {
    const auto values=QJsonDocument::fromJson(colors.readAll()).object(); QPalette palette; const auto roles=QMetaEnum::fromType<QPalette::ColorRole>();
    for(auto it=values.begin();it!=values.end();++it) { int role=roles.keyToValue(it.key().toLatin1().constData()); if(role>=0) palette.setColor(QPalette::All,QPalette::ColorRole(role),QColor(it.value().toString())); }
    app.setPalette(palette);
  }
  XetalIcons::apply(root);
  FusionOverview::Page page; page.resize(1280,800);
  page.systemResult("CPU: AMD Ryzen 7 7800X3D 8-Core Processor\nGPU: AMD Radeon RX 7900 XTX\nKERNEL: 7.3.5-arch1-1\nUPTIME: 8 minutes\nRAM: 2.3Gi 23Gi\nRAMPCT: 9\n",true);
  page.storageResult("/ 15G 62G 25%\n/home 82G 500G 16%\n",true);
  page.servicesResult("RUNNING: 12\n",true);
  QStringList updates; for(int i=0;i<181;++i) updates << (i==0?"alsa-card-profiles":i==1?"amd-ucode":i==2?"at-spi2-core":QString("package-%1").arg(i))+" 1 -> 2";
  page.updatesResult(updates.join('\n'),0); page.healthResult("NOAUTH",true); page.recoveryResult({}, {}, 0); page.setBusy(false); page.show();
  QTimer::singleShot(150,&app,[&] {
    page.grab().save(output+"/overview.png"); page.resize(600,520);
    QTimer::singleShot(100,&app,[&] {
      page.grab().save(output+"/overview-compact.png");page.hide();
      auto *about=FusionAbout::show(&page,root,"Control Panel","System tools and desktop management for Hyper Fusion.","Powered by the CachyOsTools C++ engine. All system tools and the ISO builder are included in this desktop's source. GPLv3.");
      QTimer::singleShot(100,&app,[&,about] { about->grab().save(output+"/about-native.png");about->close();app.quit(); });
    });
  }); return app.exec();
}
