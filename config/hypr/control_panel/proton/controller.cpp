#include "controller.h"
#include "src/util.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QLockFile>
#include <QSaveFile>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <filesystem>

namespace fs = std::filesystem;
namespace XetalProton {
namespace {
QString q(const std::string &s) { return QString::fromStdString(s); }
std::string normalized(const QString &path) {
    QFileInfo info(path);
    return (info.exists() ? info.canonicalFilePath() : QDir::cleanPath(info.absoluteFilePath())).toStdString();
}
QByteArray encode(const Config &c, const QByteArray &previous) {
    using J = nlohmann::json;
    J doc = previous.isEmpty() ? J::object() : J::parse(previous.toStdString());
    const auto oldPrefixes = doc.value("prefixes", J::array());
    const auto oldShortcuts = doc.value("shortcuts", J::array());
    doc["prefixes_root"] = c.prefixes_root; doc["last_prefix"] = c.last_prefix;
    doc["ui_scale"] = c.ui_scale; doc["icon_size"] = c.icon_size;
    doc["discover_steam"] = c.discover_steam; doc["prefix_proton"] = c.prefix_proton;
    doc["prefixes"] = J::array(); doc["shortcuts"] = J::array();
    for (const auto &p : c.prefixes) {
        J entry = J::object();
        for (const auto &old : oldPrefixes) if (old.value("path", "") == p.path) entry = old;
        entry["name"] = p.name; entry["path"] = p.path; doc["prefixes"].push_back(entry);
    }
    for (const auto &s : c.shortcuts) {
        J entry = J::object();
        for (const auto &old : oldShortcuts) if (old.value("id", "") == s.id) entry = old;
        entry.update(J{{"id",s.id},{"name",s.name},{"exe",s.exe},{"args",s.args},{"workdir",s.workdir},
            {"prefix",s.prefix},{"proton",s.proton},{"verb",s.verb},{"use_runtime",s.use_runtime},
            {"env",s.env},{"custom_env",s.custom_env},{"icon_override",s.icon_override}});
        doc["shortcuts"].push_back(entry);
    }
    return QByteArray::fromStdString(doc.dump(2))+"\n";
}
}
Controller::Controller(QObject *parent) : QObject(parent) {
    connect(&timer, &QTimer::timeout, this, &Controller::poll);
    timer.start(200);
}
Controller::~Controller() {
    if (job) job->cancelled = true;
    if (future.valid()) future.wait();
}
void Controller::report(const QString &text) { notice = text; emit message(text); }
bool Controller::reload() {
    try {
        QFile file(q(config_path()));
        if (file.exists() && !file.open(QIODevice::ReadOnly)) throw std::runtime_error("Cannot read XetalProton configuration.");
        saved = file.isOpen() ? file.readAll() : QByteArray();
        if (file.isOpen() && !QJsonDocument::fromJson(saved).isObject())
            throw std::runtime_error("The existing XetalProton configuration is invalid. Restore it before saving changes.");
        config = load_config(); configReadable = true; loaded = true;
        scan(); emit changed(); return true;
    } catch (const std::exception &e) { configReadable = false; report(q(e.what())); return false; }
}
void Controller::scan() {
    discovery = scan_installations(config.discover_steam);
    installed = toolstore::installed(); prefixes.clear();
    for (const auto &p : config.prefixes) prefixes.push_back({p.name,p.path,{},true});
    for (const auto &p : discovery.prefixes)
        if (std::none_of(prefixes.begin(),prefixes.end(),[&](const auto &v){return v.path==p.path;}))
            prefixes.push_back({p.name+" [Steam]",p.path,p.version_hint,false});
    current = config.last_prefix;
    if (std::none_of(prefixes.begin(),prefixes.end(),[&](const auto &v){return v.path==current;}))
        current = prefixes.empty() ? "" : prefixes.front().path;
}
bool Controller::save(const Config &next) {
    if (!configReadable) { report("Reload a valid configuration before saving changes."); return false; }
    try {
        const QString path = q(config_path());
        if (!QDir().mkpath(QFileInfo(path).absolutePath())) throw std::runtime_error("Cannot create the configuration folder.");
        QLockFile lock(path+".panel-lock");
        if (!lock.tryLock(0)) throw std::runtime_error("Another Proton operation is saving configuration. Retry shortly.");
        QFile existing(path);
        if (existing.exists() && !existing.open(QIODevice::ReadOnly)) throw std::runtime_error("Cannot read the existing configuration.");
        if ((existing.isOpen() ? existing.readAll() : QByteArray()) != saved)
            throw std::runtime_error("XetalProton settings changed in another window. Reload before editing again.");
        const auto data = encode(next,saved);
        QSaveFile output(path); output.setDirectWriteFallback(false);
        if (!output.open(QIODevice::WriteOnly)) throw std::runtime_error("Cannot save Proton settings.");
        output.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner);
        if (output.write(data)!=data.size() || !output.commit()) throw std::runtime_error("Could not finish saving Proton settings.");
        saved=data; config=next;
        // Discovery failure must not undo a prefix after its configuration was committed.
        try { scan(); } catch (const std::exception &e) { report("Settings saved; could not refresh tools: "+q(e.what())); }
        emit changed(); return true;
    } catch (const std::exception &e) { report(q(e.what())); return false; }
}
const ProtonVersion *Controller::proton(const std::string &prefix, const std::string &override) const {
    if (!override.empty()) return find_proton(discovery,override);
    const auto selected = config.prefix_proton.find(prefix);
    if (selected!=config.prefix_proton.end() && !selected->second.empty()) return find_proton(discovery,selected->second);
    for (const auto &p:prefixes) if (p.path==prefix)
        if (const auto *found=guess_proton_for_prefix(discovery,p.version)) return found;
    return discovery.protons.empty() ? nullptr : &discovery.protons.front();
}
void Controller::pinDefaults(Config &next) const {
    for (const auto &p:prefixes) if (next.prefix_proton[p.path].empty())
        if (const auto *version=proton(p.path)) next.prefix_proton[p.path]=version->dir;
}
bool Controller::selectPrefix(const std::string &path) {
    if (std::none_of(prefixes.begin(),prefixes.end(),[&](const auto &v){return v.path==path;})) return false;
    auto next=config; next.last_prefix=path; return save(next);
}
bool Controller::selectProton(const std::string &path) {
    if (current.empty() || !find_proton(discovery,path)) return false;
    if (dependencies::busy(current)) { report("Close programs in this prefix before changing its Proton version."); return false; }
    auto next=config; next.prefix_proton[current]=path; return save(next);
}
bool Controller::createPrefix(const QString &name) {
    const auto label=name.trimmed().toStdString();
    if (label.empty() || label=="." || label=="..") { report("Enter a prefix name."); return false; }
    const auto path=normalized(q(config.prefixes_root)+"/"+q(util::sanitize_filename(label)));
    if (fs::exists(path)) { report("That prefix folder already exists. Import it or choose another name."); return false; }
    if (!util::mkdirs(path+"/pfx")) { report("Cannot create the prefix folder."); return false; }
    auto next=config; next.prefixes.push_back({label,path}); next.last_prefix=path;
    if (const auto *p=proton(current)) next.prefix_proton[path]=p->dir;
    if (save(next)) { report("Prefix created. Initialize it or launch an installer to create its Windows environment."); return true; }
    std::error_code ec; fs::remove(path+"/pfx",ec); fs::remove(path,ec); return false;
}
bool Controller::importPrefix(const QString &folder) {
    const auto path=normalized(folder);
    if (!util::dir_exists(path+"/pfx")) { report("Select a Proton prefix folder containing pfx/. A plain Wine prefix must be placed inside a parent folder as pfx/ first."); return false; }
    for (const auto &p:prefixes) if (normalized(q(p.path))==path) return selectPrefix(p.path);
    auto next=config; next.prefixes.push_back({util::basename(path),path}); next.last_prefix=path;
    return save(next);
}
bool Controller::renamePrefix(const QString &name) {
    if (name.trimmed().isEmpty()) return false;
    auto next=config;
    for (auto &p:next.prefixes) if (p.path==current) { p.name=name.trimmed().toStdString(); return save(next); }
    return false;
}
bool Controller::removePrefix(bool deleteFiles) {
    if (busy()) { report("Wait for the current Proton operation to finish before removing a prefix."); return false; }
    if (current.empty() || dependencies::busy(current)) { report("Close this prefix's programs and installers first."); return false; }
    if (std::none_of(config.prefixes.begin(),config.prefixes.end(),[&](const auto &p){return p.path==current;}))
        { report("Steam prefixes are managed by Steam."); return false; }
    const auto path=current;
    if (deleteFiles) {
        const fs::path root=normalized(q(config.prefixes_root)), target=normalized(q(path));
        if (target.parent_path()!=root || fs::is_symlink(path) || !fs::is_directory(target/"pfx"))
            { report("Only a prefix directly inside your prefixes folder can be deleted here. Imported folders can be removed from the list while keeping their files."); return false; }
        // Move first so a failed configuration save can restore the complete prefix.
        const fs::path retired=root/(".removed-"+new_id());
        std::error_code ec; fs::rename(target,retired,ec);
        if (ec) { report("Cannot move this prefix for removal: "+q(ec.message())); return false; }
        auto next=config; std::erase_if(next.prefixes,[&](const auto &p){return p.path==path;});
        std::erase_if(next.shortcuts,[&](const auto &s){return s.prefix==path;}); next.prefix_proton.erase(path); next.last_prefix.clear();
        if (!save(next)) { fs::rename(retired,target,ec); if (ec) report("The prefix remains at "+q(retired.string())+"; restore it manually."); return false; }
        start(Remove,[retired](auto &job){
            job.report("Removing prefix files");
            std::error_code ec; fs::remove_all(retired,ec); TaskResult result;
            result.message=ec ? "Prefix removed from the list; some files remain at "+retired.string() : "Prefix and its Windows files removed.";
            return result;
        });
        return true;
    }
    auto next=config; std::erase_if(next.prefixes,[&](const auto &p){return p.path==path;});
    std::erase_if(next.shortcuts,[&](const auto &s){return s.prefix==path;}); next.prefix_proton.erase(path); next.last_prefix.clear();
    return save(next);
}
Shortcut *Controller::shortcut(const std::string &id) {
    for (auto &s:config.shortcuts) if (s.id==id) return &s;
    return nullptr;
}
bool Controller::addShortcut(const QString &path, bool run) {
    if (current.empty()) { report("Create or select a prefix first."); return false; }
    if (!QFileInfo(path).isFile()) { report("Choose an existing Windows program or installer."); return false; }
    Shortcut s; s.id=new_id(); s.name=QFileInfo(path).completeBaseName().toStdString();
    s.exe=QFileInfo(path).absoluteFilePath().toStdString(); s.prefix=current;
    auto next=config; next.shortcuts.push_back(s); pinDefaults(next);
    if (!save(next)) return false;
    if (run) launchShortcut(s.id);
    return true;
}
bool Controller::updateShortcut(const Shortcut &s) {
    if (s.name.empty() || s.exe.empty()) { report("Enter a name and executable for this shortcut."); return false; }
    auto next=config;
    for (auto &entry:next.shortcuts) if (entry.id==s.id) { entry=s; return save(next); }
    return false;
}
bool Controller::removeShortcut(const std::string &id) {
    auto next=config; std::erase_if(next.shortcuts,[&](const auto &s){return s.id==id;}); return save(next);
}
bool Controller::duplicateShortcut(const std::string &id) {
    const auto *s=shortcut(id); if (!s) return false;
    auto copy=*s; copy.id=new_id(); copy.name+=" (copy)";
    auto next=config; next.shortcuts.push_back(copy); return save(next);
}
LaunchSpec Controller::command(const Shortcut &s) const {
    const auto *p=proton(s.prefix,s.proton);
    if (!p) { LaunchSpec result; result.error="The selected Proton version is unavailable. Download it or choose an installed version."; return result; }
    return build_launch(*p,s.prefix,s.exe,s.args,s.verb,s.use_runtime,s.env,s.custom_env,s.workdir,s.name);
}
pid_t Controller::launch(const LaunchSpec &spec) {
    if (task==Remove) { report("Wait for tool removal to finish before launching."); return -1; }
    if (!spec.error.empty()) { report(q(spec.error)); return -1; }
    const auto pid=manager.start(spec); poll(); return pid;
}
pid_t Controller::launchShortcut(const std::string &id) {
    const auto *s=shortcut(id); if (!s) return -1;
    const auto spec=command(*s);
    auto next=config; pinDefaults(next); if (next.prefix_proton!=config.prefix_proton && !save(next)) return -1;
    return launch(spec);
}
pid_t Controller::runTool(const std::string &exe, const std::string &args) {
    Shortcut s; s.prefix=current; s.exe=exe; s.args=args; s.verb="runinprefix"; s.name=exe;
    return launch(command(s));
}
pid_t Controller::forceStopPrefix() {
    const auto *p=proton(current); if (!p) { report("Select an installed Proton version first."); return -1; }
    std::string server=p->dir+"/files/bin/wineserver";
    if (!util::file_exists(server)) server=p->dir+"/dist/bin/wineserver";
    return launch(build_launch(*p,current,server,"-k","run",true,{{"@native","1"}},"",util::home_dir(),"Stop prefix wineserver"));
}
bool Controller::exportScript(const std::string &id,const QString &path) {
    const auto *s=shortcut(id); if (!s) return false;
    const auto spec=command(*s); if (!spec.error.empty()) { report(q(spec.error)); return false; }
    QSaveFile file(path); file.setDirectWriteFallback(false);
    const auto content=QByteArray::fromStdString(spec_to_script(spec));
    if (!file.open(QIODevice::WriteOnly) || file.write(content)!=content.size() || !file.commit()) { report("Could not export the launch script."); return false; }
    QFile::setPermissions(path,QFileDevice::ReadOwner|QFileDevice::WriteOwner|QFileDevice::ExeOwner);
    report("Launch script exported."); return true;
}
void Controller::stopProcess(pid_t pid,bool force) {
    const auto list=manager.snapshot();
    if (std::any_of(list.begin(),list.end(),[&](const auto &p){return p.pid==pid && p.running;})) {
        if (dependencyJobs.count(pid)) dependencyJobs[pid].stopped=true;
        manager.kill(pid,force);
    }
}
void Controller::start(Task kind,std::function<TaskResult(downloads::Job &)> work) {
    if (busy()) return;
    task=kind; job=std::make_shared<downloads::Job>(); phase="Starting"; done=total=0;
    { std::lock_guard<std::mutex> lock(progressMutex); progressPhase="Starting"; progressDone=progressTotal=0; }
    job->progress=[this](const auto &p,uint64_t d,uint64_t t) { std::lock_guard<std::mutex> lock(progressMutex); progressPhase=p; progressDone=d; progressTotal=t; };
    future=std::async(std::launch::async,[job=job,work]{return work(*job);}); emit taskChanged();
}
void Controller::loadReleases(int number) {
    if (busy()) return;
    const auto p=toolstore::provider(provider); requestedPage=number;
    start(Catalog,[p,number](auto &job){TaskResult r; r.page=toolstore::releases(p,number,job); return r;});
}
void Controller::installRelease(const toolstore::Release &release) {
    if (busy()) return;
    auto next=config; pinDefaults(next);
    if (next.prefix_proton!=config.prefix_proton && !save(next)) return;
    start(Install,[release](auto &job){TaskResult r; r.message="Installed "+toolstore::install(release,job).name+". Select it for a prefix when ready."; return r;});
}
std::vector<std::string> Controller::protectedTools() const {
    std::vector<std::string> paths;
    for (const auto &[prefix,path]:config.prefix_proton) if (!path.empty()) paths.push_back(path);
    for (const auto &s:config.shortcuts) if (!s.proton.empty()) paths.push_back(s.proton);
    for (const auto &p:prefixes) if (const auto *version=proton(p.path)) paths.push_back(version->dir);
    return paths;
}
bool Controller::removeTool(const toolstore::Installation &installation) {
    if (busy()) return false;
    for (const auto &p:prefixes) if (dependencies::busy(p.path)) { report("Close Proton programs before removing a tool."); return false; }
    for (const auto &p:manager.snapshot()) if (p.running) { report("Close Proton programs before removing a tool."); return false; }
    const auto paths=protectedTools();
    start(Remove,[installation,paths](auto &){toolstore::remove(installation,paths); TaskResult r; r.message="Removed "+installation.name+". Prefixes and Windows applications were kept."; return r;}); return true;
}
void Controller::checkUpdates() { start(Updates,[](auto &job){TaskResult r; r.updates=toolstore::check_updates(job); return r;}); }
void Controller::cancel() { if (job && task!=Remove) job->cancelled=true; }
bool Controller::installDependency(const std::string &verb) {
    const auto *p=proton(current); if (!p) { report("Choose an installed Proton version first."); return false; }
    try {
        const auto status=dependencies::status(current);
        if (status.installed.count(verb)) { report("This component is already recorded as installed."); return false; }
        const auto spec=dependencies::build_install(*p,current,verb,status.failures.count(verb));
        const auto pid=launch(spec); if (pid<=0) return false;
        dependencyJobs[pid]={current,verb,false};
        dependencies::record_result(current,verb,"Installation has not finished. Retry if interrupted.");
        return true;
    } catch (const std::exception &e) { report(q(e.what())); return false; }
}
void Controller::poll() {
    if (busy()) {
        { std::lock_guard<std::mutex> lock(progressMutex); phase=q(progressPhase); done=progressDone; total=progressTotal; }
        emit taskChanged();
        if (future.wait_for(std::chrono::milliseconds(0))==std::future_status::ready) {
            try {
                auto result=future.get();
                if (task==Catalog) {
                    if (requestedPage==1) releases.clear();
                    for (auto &r:result.page.releases) if (std::none_of(releases.begin(),releases.end(),[&](const auto &v){return v.url==r.url;})) releases.push_back(std::move(r));
                    page=requestedPage; more=result.page.has_more;
                    report(q(result.page.notice.empty() ? (releases.empty() ? "No downloadable releases on this page. Try older releases." : "Releases loaded.") : result.page.notice));
                } else if (task==Updates) {
                    updates=std::move(result.updates.updates); updateNotice=q(result.updates.notice);
                    report(updates.empty() ? (updateNotice.isEmpty() ? "No newer matching releases found." : "Some update checks failed; review Updates and retry.") : QString::number(updates.size())+" updates available.");
                } else report(q(result.message));
            } catch (const std::exception &e) { report(q(e.what())+(task==Install ? "\nRetry the same download to resume recoverable data." : "")); }
            job.reset(); task=None;
            try { scan(); } catch (const std::exception &e) { report(q(e.what())); }
            std::erase_if(updates,[&](const auto &u){return std::any_of(installed.begin(),installed.end(),[&](const auto &i){return i.id==toolstore::installation_id(u.release);});});
            emit changed(); emit taskChanged();
        }
    }
    processes=manager.snapshot();
    for (const auto &p:processes) if (!p.running && dependencyJobs.count(p.pid)) {
        const auto job=dependencyJobs[p.pid];
        std::string error=job.stopped ? "Installer stopped. Review the log and retry." : p.exit_code ? "Installer exited with code "+std::to_string(p.exit_code)+". Review the log." : "";
        try {
            dependencies::record_result(job.prefix,job.verb,error);
            if (error.empty() && !dependencies::status(job.prefix).installed.count(job.verb)) {
                error="Installer finished without recording the component. Review the log.";
                dependencies::record_result(job.prefix,job.verb,error);
            }
        } catch (const std::exception &e) { error=e.what(); }
        report(q(job.verb+": "+(error.empty() ? "Installed." : error))); dependencyJobs.erase(p.pid); emit changed();
    }
    for (const auto &text:manager.drain_messages()) report(q(text));
    if (!processes.empty()) emit processChanged();
}
}
