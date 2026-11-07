// Complete, live Qt palettes scoped to this Hyprland profile. Qt 5 and Qt 6 builds.
#include <qpa/qplatformthemeplugin.h>
#include <qpa/qplatformtheme.h>
#include <qpa/qwindowsysteminterface.h>
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QFileSystemWatcher>
#include <QFont>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPalette>
#include <QTimer>
#include "file_preview.hpp"
#include "file_picker.hpp"
#include "icon_theme.hpp"
#include "dialog_sounds.hpp"

class XetalTheme final : public QObject, public QPlatformTheme {
    QPalette colors;
    QFont systemFont{"Noto Sans", 10};
    QFileSystemWatcher *watcher = nullptr;
    QString config, mode, iconTheme;
    QStringList iconPaths;
    QJsonObject read(const QString &path) {
        QFile file(path); if (!file.open(QIODevice::ReadOnly)) return {};
        return QJsonDocument::fromJson(file.readAll()).object();
    }
    void load() {
        const auto state = read(config);
        const auto root=QFileInfo(config).dir().absoluteFilePath("..");
        iconTheme=XetalIcons::name(root);iconPaths=XetalIcons::paths(root);
        mode = state.value("mode").toString("dark");
        auto all = read(QFileInfo(config).dir().filePath("palettes.json"));
        auto design = state.value("design").toString("raw");
        if (auto app = QCoreApplication::instance()) {
            const auto local = app->property("xetalThemeDesign").toString();
            if (local == "raw" || all.value(local).isObject()) design = local;
        }
        if (design != "raw" && all.value(design).isObject()) all = all.value(design).toObject();
        systemFont.setFamily(design == "blackwood" ? "Noto Serif" : design == "breakpoint" || design == "binaryknife" || design == "tidalglass" || design == "porcelainink" || design == "obsidianforge" || design == "candycloud" || design == "shadowedge" || design == "hyperfusionblue" || design == "midnighttransit" ? "Inter" : "Noto Sans");
        auto values = all.value(mode).toObject();
        if (values.isEmpty()) { mode = "dark"; values = all.value(mode).toObject(); }
        colors = QPalette(QColor(values.value("Window").toString("#171b22")));
        const std::pair<const char *, QPalette::ColorRole> roles[] = {
            {"Window",QPalette::Window}, {"WindowText",QPalette::WindowText}, {"Base",QPalette::Base},
            {"AlternateBase",QPalette::AlternateBase}, {"Text",QPalette::Text}, {"Button",QPalette::Button},
            {"ButtonText",QPalette::ButtonText}, {"BrightText",QPalette::BrightText}, {"Light",QPalette::Light},
            {"Midlight",QPalette::Midlight}, {"Dark",QPalette::Dark}, {"Mid",QPalette::Mid}, {"Shadow",QPalette::Shadow},
            {"Highlight",QPalette::Highlight}, {"HighlightedText",QPalette::HighlightedText}, {"Link",QPalette::Link},
            {"LinkVisited",QPalette::LinkVisited}, {"ToolTipBase",QPalette::ToolTipBase}, {"ToolTipText",QPalette::ToolTipText},
            {"PlaceholderText",QPalette::PlaceholderText}
        };
        for (const auto &role : roles) colors.setColor(QPalette::All, role.second, QColor(values.value(role.first).toString()));
#if QT_VERSION >= QT_VERSION_CHECK(6,6,0)
        colors.setColor(QPalette::All, QPalette::Accent, QColor(values.value("Accent").toString()));
#endif
        for (auto role : {QPalette::Text,QPalette::WindowText,QPalette::ButtonText,QPalette::PlaceholderText})
            colors.setColor(QPalette::Disabled, role, QColor(values.value("Disabled").toString()));
    }
    void notify() {
        load();
        if (watcher && !watcher->files().contains(config)) watcher->addPath(config);
        if (qobject_cast<QApplication *>(QCoreApplication::instance())) QApplication::setPalette(colors);
        QIcon::setThemeSearchPaths(iconPaths);
        QIcon::setFallbackThemeName("hicolor");QIcon::setThemeName(iconTheme);
#if QT_VERSION >= QT_VERSION_CHECK(6,0,0)
        QWindowSystemInterface::handleThemeChange();
#else
        QWindowSystemInterface::handleThemeChange(nullptr);
#endif
    }
public:
    explicit XetalTheme(const QString &path) : config(path) {
        load();
        // Platform themes are constructed before QApplication's event dispatcher
        // is ready. Create the watcher after startup so its socket is registered.
        QTimer::singleShot(0, this, [this] {
            watcher = new QFileSystemWatcher(this);
            watcher->addPaths({QFileInfo(config).absolutePath(), config});
            connect(watcher, &QFileSystemWatcher::directoryChanged, this, [this] { notify(); });
            connect(watcher, &QFileSystemWatcher::fileChanged, this, [this] { notify(); });
            notify();
            XetalPreview::install();
            XetalSounds::install(QFileInfo(config).dir().absoluteFilePath(".."));
        });
    }
    const QPalette *palette(Palette) const override { return &colors; }
    const QFont *font(Font) const override { return &systemFont; }
    bool usePlatformNativeDialog(DialogType type) const override {
        return type == FileDialog && qEnvironmentVariable("XETAL_FILE_PICKER") != "1" &&
            QFileInfo::exists(QFileInfo(config).dir().filePath("../file_manager/.build/xetal-files"));
    }
    QPlatformDialogHelper *createPlatformDialogHelper(DialogType type) const override {
        if (!usePlatformNativeDialog(type)) return nullptr;
        return new XetalFilePicker(QFileInfo(config).dir().absoluteFilePath(".."));
    }
    QVariant themeHint(ThemeHint hint) const override {
        if (hint == StyleNames) return QStringList{"Fusion"};
        if (hint == SystemIconThemeName) return iconTheme;
        if (hint == SystemIconFallbackThemeName) return "hicolor";
        if (hint == IconThemeSearchPaths) return iconPaths;
        return QPlatformTheme::themeHint(hint);
    }
#if QT_VERSION >= QT_VERSION_CHECK(6,5,0)
    Qt::ColorScheme colorScheme() const override { return mode == "light" ? Qt::ColorScheme::Light : Qt::ColorScheme::Dark; }
#endif
};

class XetalThemePlugin final : public QPlatformThemePlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QPlatformThemeFactoryInterface_iid FILE "plugin.json")
public:
    QPlatformTheme *create(const QString &key, const QStringList &) override {
        const auto config = qEnvironmentVariable("XETAL_THEME_CONFIG");
        if (key == "xetal" && !config.isEmpty() && !qEnvironmentVariable("HYPRLAND_INSTANCE_SIGNATURE").isEmpty())
            return new XetalTheme(config);
        return nullptr;
    }
};
#include "platformtheme.moc"
