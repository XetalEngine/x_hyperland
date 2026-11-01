#include "window.h"
#include <KPropertiesDialog>
#include <QDBusAbstractAdaptor>
#include <QDBusConnection>

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
public slots:
  void ShowFolders(const QStringList &uris, const QString &) {
    for (const auto &uri : uris) {
      const QUrl url(uri);
      if (url.isValid() && !url.scheme().isEmpty())
        window()->openLocation(url);
    }
  }
  void ShowItems(const QStringList &uris, const QString &) {
    for (const auto &uri : uris) {
      const QUrl url(uri);
      if (url.isValid() && !url.scheme().isEmpty())
        window()->reveal(url);
    }
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
  parser.addOption({"service", "Activate the desktop file-manager service."});
  parser.addPositionalArgument("locations", "Paths or URLs to open.",
                               "[locations…]");
  parser.process(app);
  QObject owner;
  FileManagerService service(&owner);
  auto bus = QDBusConnection::sessionBus();
  bus.registerObject("/org/freedesktop/FileManager1", &owner,
                     QDBusConnection::ExportAdaptors);
  const bool registered = bus.registerService("org.freedesktop.FileManager1");
  if (!parser.isSet("service") || !registered) {
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
