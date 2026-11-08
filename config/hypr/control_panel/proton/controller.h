#pragma once
#include "src/config.h"
#include "src/dependencies.h"
#include "src/tools.h"
#include <QObject>
#include <QTimer>
#include <future>
#include <memory>

namespace XetalProton {
struct Prefix { std::string name, path, version; bool custom = true; };
struct TaskResult {
    toolstore::ReleasePage page;
    toolstore::UpdateReport updates;
    std::string message;
};
class Controller : public QObject {
    Q_OBJECT
public:
    explicit Controller(QObject *parent = nullptr);
    ~Controller() override;
    Config config;
    SteamInfo discovery;
    std::vector<Prefix> prefixes;
    std::vector<toolstore::Installation> installed;
    std::vector<toolstore::Release> releases;
    std::vector<toolstore::Update> updates;
    std::vector<ProcInfo> processes;
    std::string current, provider = "ge";
    int page = 0;
    bool more = false, loaded = false;
    QString notice, updateNotice, phase;
    uint64_t done = 0, total = 0;
    enum Task { None, Catalog, Install, Remove, Updates };
    Task task = None;
    bool busy() const { return task != None; }
    bool reload();
    bool save(const Config &next);
    bool selectPrefix(const std::string &path);
    bool selectProton(const std::string &path);
    bool createPrefix(const QString &name);
    bool importPrefix(const QString &path);
    bool renamePrefix(const QString &name);
    bool removePrefix(bool deleteFiles);
    bool addShortcut(const QString &path, bool launch);
    bool updateShortcut(const Shortcut &shortcut);
    bool removeShortcut(const std::string &id);
    bool duplicateShortcut(const std::string &id);
    Shortcut *shortcut(const std::string &id);
    const ProtonVersion *proton(const std::string &prefix, const std::string &override = {}) const;
    LaunchSpec command(const Shortcut &shortcut) const;
    pid_t launch(const LaunchSpec &spec);
    pid_t launchShortcut(const std::string &id);
    pid_t runTool(const std::string &exe, const std::string &args = {});
    pid_t forceStopPrefix();
    bool exportScript(const std::string &id, const QString &path);
    void stopProcess(pid_t pid, bool force);
    void loadReleases(int number);
    void installRelease(const toolstore::Release &release);
    bool removeTool(const toolstore::Installation &installation);
    void checkUpdates();
    void cancel();
    bool installDependency(const std::string &verb);
    std::vector<std::string> protectedTools() const;
    void report(const QString &text);
    void poll();
signals:
    void changed();
    void taskChanged();
    void processChanged();
    void message(const QString &text);
private:
    QByteArray saved;
    bool configReadable = false;
    ProcessManager manager;
    QTimer timer;
    std::shared_ptr<downloads::Job> job;
    std::future<TaskResult> future;
    std::mutex progressMutex;
    std::string progressPhase;
    uint64_t progressDone = 0, progressTotal = 0;
    int requestedPage = 0;
    struct DependencyJob { std::string prefix, verb; bool stopped = false; };
    std::map<pid_t, DependencyJob> dependencyJobs;
    void scan();
    void start(Task kind, std::function<TaskResult(downloads::Job &)> work);
    void pinDefaults(Config &next) const;
};
}
