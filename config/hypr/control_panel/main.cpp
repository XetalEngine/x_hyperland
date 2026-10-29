#include "backend/mainwindow.h"
#include "backend/window_enum_backend.h"
#include "native.h"
#include "disk_visualizer.h"
#include "wheel_guard.h"
#include <QJsonDocument>
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QtWidgets>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <memory>
static volatile sig_atomic_t stopping = 0;
int main(int argc, char **argv) {
  if (argc > 1 && (std::strcmp(argv[1], "--window-enum-x11") == 0 ||
                   std::strcmp(argv[1], "--window-enum-wayland") == 0)) {
    QCoreApplication app(argc, argv);
    if (std::strcmp(argv[1], "--window-enum-wayland") == 0)
      return windowEnumWayland();
    auto request =
        QJsonDocument::fromJson(argc > 2 ? QByteArray(argv[2]) : QByteArray())
            .object();
    auto output = windowEnumX11(request);
    auto text = QJsonDocument(output).toJson(QJsonDocument::Compact);
    std::fwrite(text.data(), 1, size_t(text.size()), stdout);
    return output.contains("error") ? 1 : 0;
  }
  QApplication app(argc, argv);
  SettingsWheelGuard wheelGuard(&app);
  app.setApplicationName("Hyper Fusion Control Panel");
  app.setDesktopFileName("xetal-control-panel");
  auto iconPaths = QIcon::themeSearchPaths();
  iconPaths << QDir::homePath() + "/.local/share/icons"
            << "/usr/local/share/icons" << "/usr/share/icons";
  iconPaths.removeDuplicates();
  QIcon::setThemeSearchPaths(iconPaths);
  QIcon::setFallbackSearchPaths({"/usr/share/icons", "/usr/local/share/icons"});
  QIcon::setFallbackThemeName("Papirus-Dark");
  if (!QIcon::hasThemeIcon("media-optical"))
    QIcon::setThemeName("Papirus-Dark");
  QSettings::setDefaultFormat(QSettings::IniFormat);
  QSettings::setPath(QSettings::NativeFormat, QSettings::UserScope,
                     HyperPanel::root() + "/control_panel/state");
  QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                     HyperPanel::root() + "/control_panel/state");
  // Language: Dashboard flag dropdown persists the choice; applied on startup.
  // CACHYOSTOOLS_LANG=pt_BR|de|en overrides the saved setting (handy for
  // testing).
  QString lang = qEnvironmentVariable("CACHYOSTOOLS_LANG");
  if (lang.isEmpty()) {
    lang = QSettings("XetalHyperland", "ControlPanel")
               .value("language/code", "en")
               .toString();
  }
  if (lang != "en") {
    QTranslator *qtTranslator = new QTranslator(&app);
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    const QString qtTrDir = QLibraryInfo::path(QLibraryInfo::TranslationsPath);
#else
    const QString qtTrDir =
        QLibraryInfo::location(QLibraryInfo::TranslationsPath);
#endif
    if (qtTranslator->load(QLocale(lang), "qtbase", "_", qtTrDir)) {
      app.installTranslator(qtTranslator);
    }
    QTranslator *appTranslator = new QTranslator(&app);
    if (appTranslator->load(":/i18n/cachyostools_" + lang + ".qm")) {
      app.installTranslator(appTranslator);
    }
  }

  QCommandLineParser parser;
  parser.addHelpOption();
  parser.addOption({"section", "Open a tool", "id"});
  parser.addOption({"smoke-size", "Override test window size (WIDTHxHEIGHT)", "size"});
  parser.addOption({"smoke-disk-path", "Scan a disk fixture without sudo (only with --smoke-dir)", "path"});
  parser.addOption({"smoke-dir",
                    "Capture navigation and home in a test directory",
                    "directory"});
  parser.process(app);
  bool smoke = parser.isSet("smoke-dir");
  QLocalSocket lifetime;
  QLocalServer commands;
  std::unique_ptr<QLockFile> instanceLock;
  if (!smoke) {
    auto signature = qEnvironmentVariable("HYPRLAND_INSTANCE_SIGNATURE"),
         runtime = qEnvironmentVariable("XDG_RUNTIME_DIR");
    if (signature.isEmpty() || runtime.isEmpty())
      return 1;
    lifetime.connectToServer(runtime + "/hypr/" + signature + "/.socket2.sock");
    if (!lifetime.waitForConnected(1500))
      return 1;
    QObject::connect(&lifetime, &QLocalSocket::readyRead, &lifetime,
                     [&lifetime] { lifetime.readAll(); });
    QObject::connect(&lifetime, &QLocalSocket::disconnected, &app,
                     &QApplication::quit);
    const auto endpoint =
        runtime + "/hypr/" + signature + "/.xpanel.sock";
    instanceLock = std::make_unique<QLockFile>(endpoint + ".lock");
    instanceLock->setStaleLockTime(0);
    if (!instanceLock->tryLock(800)) {
      QLocalSocket existing;
      existing.connectToServer(endpoint);
      if (!existing.waitForConnected(1500))
        return 1;
      existing.write(
          QJsonDocument(QJsonObject{{"section", parser.value("section")}})
              .toJson(QJsonDocument::Compact) +
          "\n");
      if (!existing.waitForBytesWritten(1000))
        return 1;
      return existing.waitForReadyRead(5000) ? 0 : 1;
    }
    QLocalServer::removeServer(endpoint);
    commands.setSocketOptions(QLocalServer::UserAccessOption);
    if (!commands.listen(endpoint))
      return 1;
  }
  MainWindow window;
  PanelController controller(&window);
  if (smoke) {
    const auto size = parser.value("smoke-size").split('x');
    window.resize(size.size() == 2 ? QSize(size[0].toInt(), size[1].toInt()) : QSize(1280, 800));
  }
  window.show();
  if (parser.isSet("section"))
    controller.open(parser.value("section"));
  if (smoke && parser.isSet("smoke-disk-path")) {
    controller.open("cleaner");
    if (auto *disk = window.findChild<DiskVisualizer *>()) {
      window.findChild<QTabWidget *>("cleanerSubTabs")->setCurrentWidget(disk);
      disk->scanFixture(parser.value("smoke-disk-path"));
    }
  }
  auto receive = [&] {
    while (auto *peer = commands.nextPendingConnection()) {
      auto read = [&, peer] {
        if (!peer->canReadLine())
          return;
        const auto request =
            QJsonDocument::fromJson(peer->readLine(4096)).object();
        window.showNormal();
        window.raise();
        window.activateWindow();
        const auto section = request["section"].toString();
        if (!section.isEmpty())
          controller.open(section);
        peer->write("ok\n");
        peer->disconnectFromServer();
      };
      QObject::connect(peer, &QLocalSocket::readyRead, &app, read);
      QObject::connect(peer, &QLocalSocket::disconnected, peer,
                       &QObject::deleteLater);
      read();
    }
  };
  QObject::connect(&commands, &QLocalServer::newConnection, &app, receive);
  QTimer::singleShot(0, &app, receive);
  QTimer signalTimer;
  QObject::connect(&signalTimer, &QTimer::timeout, &app, [&app] {
    if (stopping)
      app.quit();
  });
  signalTimer.start(200);
  std::signal(SIGTERM, [](int) { stopping = 1; });
  std::signal(SIGINT, [](int) { stopping = 1; });
  std::signal(SIGHUP, [](int) { stopping = 1; });
  if (smoke)
    QTimer::singleShot(2000, &app, [&] {
      const auto errors = controller.verifyNavigation();
      QTimer::singleShot(80, &app, [&, errors] {
        auto directory = parser.value("smoke-dir");
        QDir().mkpath(directory);
        auto inventory = controller.inventory();
        inventory["navigationErrors"] = errors;
        QFile report(directory + "/inventory.json");
        report.open(QIODevice::WriteOnly);
        report.write(QJsonDocument(inventory).toJson());
        window.grab().save(directory + "/panel.png");
        app.quit();
      });
    });
  return app.exec();
}
