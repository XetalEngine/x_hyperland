#include "window.h"
#include "picker.h"
#include <KPropertiesDialog>
#include <QDBusAbstractAdaptor>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QLocalSocket>
#include <QLockFile>
#include <csignal>
#include <memory>

static volatile sig_atomic_t stopping = 0;

class FileManagerService : public QDBusAbstractAdaptor {
  Q_OBJECT
  Q_CLASSINFO("D-Bus Interface", "org.freedesktop.FileManager1")
public:
  explicit FileManagerService(QObject *parent) : QDBusAbstractAdaptor(parent) {}
  QPointer<FilesWindow> active;
  FilesWindow *window() {
    if (!active)
      active = new FilesWindow;
    active->show();
    active->raise();
    active->activateWindow();
    return active;
  }
  void openWithDefault(const QStringList &uris, bool select, const QString &startupId) {
    QStringList arguments{"--external"};
    if (select) arguments << "--select";
    for (const auto &uri : uris) {
      const QUrl url(uri);
      if (url.isValid() && !url.scheme().isEmpty()) arguments << url.toString(QUrl::FullyEncoded);
    }
    if (arguments.size() <= (select ? 2 : 1)) return;
    // The service can outlive a Default Apps change. Resolve the current
    // choice for each request instead of permanently claiming folder actions.
    // The direct Fusion launcher does not call this interface, so no loop.
    QProcess launcher;
    launcher.setProgram(Fusion::root() + "/scripts/file-manager.sh");
    launcher.setArguments(arguments);
    auto environment = QProcessEnvironment::systemEnvironment();
    environment.remove("DESKTOP_STARTUP_ID");
    environment.remove("XDG_ACTIVATION_TOKEN");
    if (!startupId.isEmpty()) {
      environment.insert("DESKTOP_STARTUP_ID", startupId);
      environment.insert("XDG_ACTIVATION_TOKEN", startupId);
    }
    launcher.setProcessEnvironment(environment);
    if (!launcher.startDetached())
      QMessageBox::warning(window(), "Could not open folder", "The selected file manager could not be started.");
  }
public slots:
  void ShowFolders(const QStringList &uris, const QString &startupId) {
    openWithDefault(uris, false, startupId);
  }
  void ShowItems(const QStringList &uris, const QString &startupId) {
    openWithDefault(uris, true, startupId);
  }
  void ShowItemProperties(const QStringList &uris, const QString &) {
    if (uris.isEmpty())
      return;
    window()->reveal(QUrl(uris.first()));
    auto *dialog = new KPropertiesDialog(QUrl(uris.first()), active);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->show();
  }
};

int main(int argc, char **argv) {
  QApplication app(argc, argv);
  app.setApplicationName("Fusion Files");
  app.setApplicationVersion("1.0");
  app.setOrganizationName("Hyper Fusion");
  app.setDesktopFileName("xetal-files");
  app.setStyle("Fusion");
  QIcon::setThemeName("Papirus-Dark");
  QCommandLineParser parser;
  parser.setApplicationDescription("Fusion Files — files, folders and This PC");
  parser.addHelpOption();
  parser.addVersionOption();
  parser.addOption({"this-pc", "Open This PC."});
  parser.addOption(
      {"select", "Select the specified file in its parent folder."});
  parser.addOption({"new-window", "Open a new window."});
  parser.addOption({"external", "Open a centered floating folder window for another application."});
  parser.addOption({"from-desktop", "Treat locations supplied by a desktop association as external requests."});
  parser.addOption({"service", "Activate the desktop file-manager service."});
  parser.addOption({"picker", "Open a file chooser using a JSON request on standard input."});
  parser.addPositionalArgument("locations", "Paths or URLs to open.",
                               "[locations…]");
  parser.process(app);
  if (parser.isSet("picker")) return runPicker(app);
  // Establish the role before any native window is created. The compositor
  // applies its floating/centering rule on the first map, never after showing.
  if (parser.isSet("external") || parser.isSet("select") ||
      (parser.isSet("from-desktop") && !parser.positionalArguments().isEmpty()))
    app.setDesktopFileName("xetal-files-external");
  const bool sessionService = parser.isSet("service");
  QLocalSocket lifetime;
  std::unique_ptr<QLockFile> serviceLock;
  QTimer signalTimer;
  if (sessionService) {
    // The shared user bus does not inherit Hyprland's profile-local activation
    // directories. Own the folder interface for this login, even with no Files
    // windows open, so Chrome's OpenDirectory portal cannot activate Dolphin.
    const auto signature = qEnvironmentVariable("HYPRLAND_INSTANCE_SIGNATURE");
    const auto runtime = qEnvironmentVariable("XDG_RUNTIME_DIR");
    if (signature.isEmpty() || runtime.isEmpty()) return 1;
    const auto instance = runtime + "/hypr/" + signature;
    lifetime.connectToServer(instance + "/.socket2.sock");
    if (!lifetime.waitForConnected(1500)) return 1;
    serviceLock = std::make_unique<QLockFile>(instance + "/fusion-files-service.lock");
    serviceLock->setStaleLockTime(0);
    if (!serviceLock->tryLock(0)) return 0;
    app.setQuitOnLastWindowClosed(false);
    QObject::connect(&lifetime, &QLocalSocket::readyRead, &lifetime,
                     [&lifetime] { lifetime.readAll(); });
    QObject::connect(&lifetime, &QLocalSocket::disconnected, &app,
                     &QApplication::quit);
    QObject::connect(&signalTimer, &QTimer::timeout, &app, [&app] {
      if (stopping) app.quit();
    });
    signalTimer.start(200);
    for (const auto number : {SIGTERM, SIGINT, SIGHUP})
      std::signal(number, [](int) { stopping = 1; });
  }
  QObject owner;
  FileManagerService service(&owner);
  auto bus = QDBusConnection::sessionBus();
  if (!bus.registerObject("/org/freedesktop/FileManager1", &owner,
                          QDBusConnection::ExportAdaptors) && sessionService)
    return 1;
  if (auto *interface = bus.interface()) {
    // A normal Files window yields to the resident router. An existing manager
    // that refuses replacement keeps its windows; our service waits silently
    // until it releases the name, never opening an unwanted This PC window.
    auto registered = interface->registerService(
        "org.freedesktop.FileManager1",
        sessionService ? QDBusConnectionInterface::ReplaceExistingService
                       : QDBusConnectionInterface::DontQueueService,
        sessionService ? QDBusConnectionInterface::DontAllowReplacement
                       : QDBusConnectionInterface::AllowReplacement);
    if (sessionService && registered.isValid() &&
        registered.value() == QDBusConnectionInterface::ServiceNotRegistered)
      registered = interface->registerService("org.freedesktop.FileManager1",
                                               QDBusConnectionInterface::QueueService);
    if (sessionService && (!registered.isValid() ||
                          registered.value() == QDBusConnectionInterface::ServiceNotRegistered))
      return 1;
    if (sessionService && registered.value() == QDBusConnectionInterface::ServiceQueued)
      qInfo("Fusion Files folder service is waiting for the existing file manager to exit.");
  } else if (sessionService) {
    return 1;
  }
  if (!sessionService) {
    const auto paths = parser.positionalArguments();
    const QUrl first =
        paths.isEmpty() || parser.isSet("this-pc")
            ? Fusion::computerUrl()
            : Fusion::userUrl(paths.first(),
                              QUrl::fromLocalFile(QDir::currentPath()));
    auto *window = new FilesWindow(
        parser.isSet("select") ? first.adjusted(QUrl::RemoveFilename) : first);
    service.active = window;
    if (parser.isSet("select") && !paths.isEmpty())
      window->browser()->selectUrl(first);
    for (int i = 1; i < paths.size(); ++i)
      window->openLocation(
          Fusion::userUrl(paths[i], QUrl::fromLocalFile(QDir::currentPath())),
          true);
    window->show();
  }
  return app.exec();
}
#include "main.moc"
