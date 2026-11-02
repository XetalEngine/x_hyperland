#pragma once
#include <qpa/qplatformdialoghelper.h>
#include <QEventLoop>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QWindow>

// Native QFileDialog integration is private to the Xetal platform theme. Apps
// that explicitly request DontUseNativeDialog keep their own embedded dialog.
class XetalFilePicker final : public QPlatformFileDialogHelper {
    QString root, nameFilter, mimeFilter;
    QUrl folder;
    QList<QUrl> files;
    QProcess process;
    QJsonArray filters;
    bool answered = false;
public:
    explicit XetalFilePicker(const QString &profile) : root(profile) {
        connect(&process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
                [this](int code, QProcess::ExitStatus status) {
            if (answered) return;
            answered = true;
            const auto result = QJsonDocument::fromJson(process.readAllStandardOutput()).object();
            if (status != QProcess::NormalExit || code || result.value("response").toInt(1) != 0) {
                emit reject(); return;
            }
            files.clear();
            for (const auto &entry : result.value("uris").toArray()) files << QUrl(entry.toString());
            if (files.isEmpty()) { emit reject(); return; }
            const auto selected = result.value("current_filter").toArray();
            if (!selected.isEmpty()) {
                nameFilter = selected.at(0).toString();
                const auto patterns = selected.at(1).toArray();
                if (!patterns.isEmpty() && patterns.at(0).toArray().at(0).toInt() == 1)
                    mimeFilter = patterns.at(0).toArray().at(1).toString();
                emit filterSelected(nameFilter);
            }
            folder = options()->fileMode() == QFileDialogOptions::Directory || options()->fileMode() == QFileDialogOptions::DirectoryOnly
                         ? files.first() : files.first().adjusted(QUrl::RemoveFilename);
            emit directoryEntered(folder);
            emit currentChanged(files.first());
            emit filesSelected(files);
            if (files.size() == 1) emit fileSelected(files.first());
            emit accept();
        });
    }
    ~XetalFilePicker() override { hide(); }
    bool defaultNameFilterDisables() const override { return false; }
    void setDirectory(const QUrl &value) override { folder = value; }
    QUrl directory() const override { return folder; }
    void selectFile(const QUrl &value) override { files = {value}; }
    QList<QUrl> selectedFiles() const override { return files; }
    void setFilter() override {}
    void selectNameFilter(const QString &value) override { nameFilter = value; }
    QString selectedNameFilter() const override { return nameFilter; }
    void selectMimeTypeFilter(const QString &value) override { mimeFilter = value; }
    QString selectedMimeTypeFilter() const override { return mimeFilter; }
    bool isSupportedUrl(const QUrl &url) const override { return url.isEmpty() || url.isLocalFile(); }
    bool show(Qt::WindowFlags, Qt::WindowModality, QWindow *parent) override {
        if (process.state() != QProcess::NotRunning) return true;
        if (!QFileInfo::exists(root+"/file_manager/.build/xetal-files")) return false;
        const auto settings = options();
        const bool saving = settings->acceptMode() == QFileDialogOptions::AcceptSave;
        const bool directory = settings->fileMode() == QFileDialogOptions::Directory || settings->fileMode() == QFileDialogOptions::DirectoryOnly;
        if (folder.isEmpty()) folder = settings->initialDirectory();
        if (files.isEmpty()) files = settings->initiallySelectedFiles();
        if (nameFilter.isEmpty()) nameFilter = settings->initiallySelectedNameFilter();
        if (mimeFilter.isEmpty()) mimeFilter = settings->initiallySelectedMimeTypeFilter();
        QJsonObject request{{"method", saving ? "SaveFile" : "OpenFile"},
                            {"app_id", QCoreApplication::applicationFilePath()+':'+QCoreApplication::applicationName()},
                            {"title", settings->windowTitle()}, {"directory", directory},
                            {"multiple", settings->fileMode() == QFileDialogOptions::ExistingFiles},
                            {"current_folder", folder.toLocalFile()}, {"default_suffix", settings->defaultSuffix()},
                            {"dont_confirm_overwrite", settings->testOption(QFileDialogOptions::DontConfirmOverwrite)}};
        if (settings->isLabelExplicitlySet(QFileDialogOptions::Accept))
            request["accept_label"] = settings->labelText(QFileDialogOptions::Accept).remove('&');
        if (!files.isEmpty()) {
            request["current_name"] = files.first().fileName();
            if (files.first().isLocalFile()) request["current_file"] = files.first().toLocalFile();
        }
        if (parent && QGuiApplication::platformName() == "xcb")
            request["parent_window"] = "x11:" + QString::number(parent->winId(), 16);
        filters = {};
        for (const auto &filter : settings->mimeTypeFilters()) {
            QJsonArray entry{filter, QJsonArray{QJsonArray{1, filter}}};
            filters.append(entry);
            if (filter == mimeFilter) request["current_filter"] = entry;
        }
        if (filters.isEmpty()) for (const auto &filter : settings->nameFilters()) {
            QString patterns = filter;
            const int left = filter.lastIndexOf('('), right = filter.lastIndexOf(')');
            if (left >= 0 && right > left) patterns = filter.mid(left+1, right-left-1);
            QJsonArray globs;
            for (auto pattern : patterns.split(QRegularExpression("[ ;]+"), Qt::SkipEmptyParts)) {
                if (pattern == "*.*") pattern = "*";
                globs.append(QJsonArray{0, pattern});
            }
            QJsonArray entry{filter, globs};
            filters.append(entry);
            if (filter == nameFilter) request["current_filter"] = entry;
        }
        request["filters"] = filters;
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert("XETAL_FILE_PICKER", "1");
        environment.insert("XETAL_FILES_ROOT", root);
        process.setProcessEnvironment(environment);
        process.setProcessChannelMode(QProcess::ForwardedErrorChannel);
        answered = false;
        process.start("/usr/bin/python3", {root+"/file_manager/launch.py", "--picker"});
        if (!process.waitForStarted(1500)) return false;
        process.write(QJsonDocument(request).toJson(QJsonDocument::Compact)+'\n');
        process.closeWriteChannel();
        return true;
    }
    void exec() override {
        if (answered || process.state() == QProcess::NotRunning) return;
        QEventLoop loop;
        connect(this, &QPlatformDialogHelper::accept, &loop, &QEventLoop::quit);
        connect(this, &QPlatformDialogHelper::reject, &loop, &QEventLoop::quit);
        loop.exec(QEventLoop::DialogExec);
    }
    void hide() override {
        if (process.state() == QProcess::NotRunning) return;
        answered = true;
        process.terminate();
        if (!process.waitForFinished(150)) { process.kill(); process.waitForFinished(500); }
        emit reject();
    }
};
