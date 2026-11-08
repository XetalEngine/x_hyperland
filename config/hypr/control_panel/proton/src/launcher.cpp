#include "launcher.h"
#include "util.h"
#include "tools.h"
#include <filesystem>
#include <sstream>
#include <cstring>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/file.h>
#include <cctype>

extern char** environ;

static bool environment_name(const std::string& name) {
    if (name.empty() || !(std::isalpha(static_cast<unsigned char>(name[0])) || name[0]=='_')) return false;
    for (unsigned char ch : name) if (!(std::isalnum(ch) || ch=='_')) return false;
    return true;
}

LaunchSpec build_launch(const ProtonVersion& proton, const std::string& prefix_path,
                        const std::string& exe, const std::string& args, const std::string& verb_in, bool use_runtime,
                        const std::map<std::string, std::string>& options, const std::string& custom_env,
                        const std::string& workdir, const std::string& label)
{
    LaunchSpec s;
    s.label = label;
    if (exe.empty()) { s.error = "No executable set"; return s; }
    if (prefix_path.empty()) { s.error = "No prefix selected"; return s; }
    if (!std::filesystem::path(prefix_path).is_absolute()) { s.error = "Prefix path must be absolute"; return s; }
    if (!util::file_exists(proton.script())) { s.error = "Proton script not found: " + proton.script(); return s; }
    std::string verb = verb_in.empty() ? "run" : verb_in;
    if (verb != "run" && verb != "waitforexitandrun" && verb != "runinprefix") { s.error = "Unsupported Proton verb"; return s; }
    const auto umu = use_runtime ? toolstore::umu_launcher() : std::string();
    if (use_runtime && umu.empty()) { s.error = "Install the UMU launcher from Tools before launching. Steam is not required."; return s; }
    if (!util::which("python3")) { s.error = "Python 3 is required to run Proton and UMU"; return s; }
    s.prefix_path = prefix_path;

    // environment
    s.env["STEAM_COMPAT_DATA_PATH"] = prefix_path;
    s.env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = "";
    s.env["STEAM_COMPAT_LIBRARY_PATHS"] = "";
    std::string exe_dir = exe.find('/') != std::string::npos ? util::dirname(exe) : "";
    if (!exe_dir.empty()) { s.env["STEAM_COMPAT_INSTALL_PATH"] = exe_dir; s.env["STEAM_COMPAT_MOUNTS"] = exe_dir; }
    s.env["PROTON_LOG_DIR"] = util::logs_dir();
    std::string game_id = util::sanitize_filename(label);
    for (auto& ch : game_id) if (ch == ' ') ch = '_';
    s.env["SteamGameId"] = "0";
    if (!options.count("STEAM_COMPAT_APP_ID") || options.at("STEAM_COMPAT_APP_ID").empty()) { s.env["STEAM_COMPAT_APP_ID"] = "0"; s.env["SteamAppId"] = "0"; }
    else { s.env["STEAM_COMPAT_APP_ID"] = options.at("STEAM_COMPAT_APP_ID"); s.env["SteamAppId"] = options.at("STEAM_COMPAT_APP_ID"); s.env["SteamGameId"] = options.at("STEAM_COMPAT_APP_ID"); }

    std::vector<std::string> wrappers;  // outer-most first
    for (auto& [k, v] : options) {
        if (v.empty()) continue;
        if (k.empty()) continue;
        if (k[0] == '@') continue;
        if (!environment_name(k)) { s.error = "Invalid environment variable name: " + k; return s; }
        s.env[k] = v;
    }
    auto opt = [&](const char* k) { auto it = options.find(k); return it == options.end() ? std::string() : it->second; };
    if (opt("@gamemoderun") == "1") wrappers.push_back("gamemoderun");
    if (opt("@gamescope") == "1") {
        std::string gs = "gamescope " + opt("@gamescope_args") + " --";
        wrappers.push_back(gs);
    }
    if (!opt("@wrapper").empty()) wrappers.push_back(opt("@wrapper"));

    // custom env text: KEY=VALUE per line, '#' comments
    std::stringstream ss(custom_env); std::string line;
    while (std::getline(ss, line)) {
        line = util::trim(line);
        if (line.empty() || line[0] == '#') continue;
        auto eq = line.find('=');
        if (eq == std::string::npos || eq == 0) continue;
        std::string k = util::trim(line.substr(0, eq)), v = line.substr(eq + 1);
        if (!environment_name(k)) { s.error = "Invalid environment variable name: " + k; return s; }
        if (v.size() >= 2 && ((v.front() == '"' && v.back() == '"') || (v.front() == '\'' && v.back() == '\''))) v = v.substr(1, v.size() - 2);
        s.env[k] = v;
    }

    // Bind the selected tool and prefix after user options. Never inherit a
    // launcher context that could redirect installs into Steam's directories.
    s.env["PROTONPATH"] = proton.dir;
    s.env["WINEPREFIX"] = use_runtime ? prefix_path : prefix_path + "/pfx";
    s.env["STEAM_COMPAT_DATA_PATH"] = prefix_path;
    s.env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = "";
    s.env["STEAM_COMPAT_LIBRARY_PATHS"] = "";
    s.env["UMU_FOLDERS_PATH"] = util::runtimes_dir();
    s.env["XDG_CACHE_HOME"] = util::data_dir() + "/cache";
    s.env["PROTON_VERB"] = verb;
    s.env["UMU_NO_RUNTIME"] = "";
    s.env["UMU_NO_PROTON"] = opt("@native") == "1" ? "1" : "";
    s.env["STEAM_COMPAT_TOOL_PATHS"] = proton.dir;
    if (!s.env.count("GAMEID")) s.env["GAMEID"] = s.env["SteamAppId"] != "0" ? "umu-" + s.env["SteamAppId"] : "umu-default";

    // command
    std::vector<std::string> cmd;
    for (auto& w : wrappers) for (auto& a : util::split_args(w)) cmd.push_back(a);
    if (use_runtime) {
        cmd.push_back(umu);
        if (opt("@native") == "1") {
            // Native Wine helpers bypass Proton's WINEPREFIX adjustment.
            cmd.push_back("/usr/bin/env");
            cmd.push_back("WINEPREFIX=" + prefix_path + "/pfx");
        }
    } else if (opt("@native") != "1") {
        cmd.push_back(proton.script());
        cmd.push_back(verb);
    }
    cmd.push_back(exe);
    for (auto& a : util::split_args(args)) cmd.push_back(a);
    s.argv = cmd;
    s.cwd = !workdir.empty() ? workdir : (!exe_dir.empty() && util::dir_exists(exe_dir) ? exe_dir : util::home_dir());
    s.log_path = util::logs_dir() + "/" + game_id + "-" + util::timestamp() + "-" + new_id() + ".log";
    return s;
}

std::string spec_to_shell(const LaunchSpec& s) {
    std::string out;
    if (!s.error.empty()) return "ERROR: " + s.error;
    if (!s.prefix_path.empty()) out += "mkdir -p " + util::shell_quote(s.prefix_path + "/pfx") + "\n";
    out += "cd " + util::shell_quote(s.cwd) + "\n";
    for (auto& [k, v] : s.env) out += "export " + k + "=" + util::shell_quote(v) + "\n";
    for (size_t i = 0; i < s.argv.size(); i++) { out += (i ? " " : "") + util::shell_quote(s.argv[i]); }
    return out + "\n";
}
std::string spec_to_script(const LaunchSpec& s) {
    std::string body = spec_to_shell(s);
    if (!body.empty() && body.back() == '\n') body.pop_back();
    return "#!/bin/sh\n# Generated by XetalProton\nset -e\n" + body + " \"$@\"\n";
}

ProcessManager::~ProcessManager() {}

void ProcessManager::log(const std::string& msg) {
    std::lock_guard<std::mutex> l(mu_);
    messages_.push_back("[" + util::time_now_hms() + "] " + msg);
}
std::vector<std::string> ProcessManager::drain_messages() {
    std::lock_guard<std::mutex> l(mu_);
    reap_locked();
    std::vector<std::string> out(messages_.begin(), messages_.end()); messages_.clear(); return out;
}
void ProcessManager::reap_locked() {
    for (auto& p : procs_) {
        if (!p.running) continue;
        int status = 0;
        if (waitpid(p.pid, &status, WNOHANG) != p.pid) continue;
        p.running = false;
        p.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : (WIFSIGNALED(status) ? 128 + WTERMSIG(status) : -1);
        messages_.push_back("[" + util::time_now_hms() + "] '" + p.label + "' exited with code " + std::to_string(p.exit_code));
    }
}
std::vector<ProcInfo> ProcessManager::snapshot() { std::lock_guard<std::mutex> l(mu_); reap_locked(); return procs_; }

void ProcessManager::kill(pid_t pid, bool hard) {
    // signal the whole session (setsid in child)
    ::kill(-pid, hard ? SIGKILL : SIGTERM);
    ::kill(pid, hard ? SIGKILL : SIGTERM);
}

pid_t ProcessManager::start(const LaunchSpec& spec) {
    if (!spec.error.empty()) { log("Launch failed: " + spec.error); return -1; }
    if (spec.argv.empty()) { log("Launch failed: empty command"); return -1; }
    if (!spec.prefix_path.empty() && !util::mkdirs(spec.prefix_path + "/pfx")) { log("Cannot create the prefix folder"); return -1; }
    util::mkdirs(util::logs_dir());
    if (!util::dir_exists(spec.cwd)) { log("Working directory does not exist: " + spec.cwd); return -1; }
    // Build env array in the parent (async-signal-safe execve in child)
    std::map<std::string, std::string> env;
    for (char** e = environ; e && *e; e++) { std::string kv = *e; auto eq = kv.find('='); if (eq != std::string::npos) env[kv.substr(0, eq)] = kv.substr(eq + 1); }
    for (auto& [k, v] : spec.env) env[k] = v;
    std::vector<std::string> envs; for (auto& [k, v] : env) envs.push_back(k + "=" + v);
    std::vector<char*> envp; for (auto& e : envs) envp.push_back((char*)e.c_str()); envp.push_back(nullptr);
    std::vector<char*> argv; for (auto& a : spec.argv) argv.push_back((char*)a.c_str()); argv.push_back(nullptr);
    std::string exe_path; if (!util::which(spec.argv[0], &exe_path)) { log("Launch failed: command not found: " + spec.argv[0]); return -1; }
    int prefix_lock = -1;
    if (!spec.prefix_path.empty()) {
        prefix_lock = open((spec.prefix_path + "/.xetalproton.lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
        if (prefix_lock < 0 || flock(prefix_lock, (spec.exclusive_prefix ? LOCK_EX : LOCK_SH) | LOCK_NB)) {
            if (prefix_lock >= 0) close(prefix_lock);
            log("Prefix is busy. Close its programs or wait for the dependency installer to finish.");
            return -1;
        }
    }

    // Write header to the log
    { std::string hdr = "# XetalProton launch: " + spec.label + "\n# " + util::timestamp("%Y-%m-%d %H:%M:%S") + "\n" + spec_to_shell(spec) + "\n----\n"; util::write_file(spec.log_path, hdr); }
    int logfd = open(spec.log_path.c_str(), O_WRONLY | O_APPEND | O_CREAT, 0644);

    pid_t pid = fork();
    if (pid == 0) {
        // Retain only this child's lock across exec. It also protects the prefix
        // if the XetalProton window closes while UMU is still running.
        if (prefix_lock >= 0) fcntl(prefix_lock, F_SETFD, 0);
        setsid();
        if (chdir(spec.cwd.c_str()) != 0) { /* ignore */ }
        int devnull = open("/dev/null", O_RDONLY);
        if (devnull >= 0) dup2(devnull, 0);
        if (logfd >= 0) { dup2(logfd, 1); dup2(logfd, 2); }
        execve(exe_path.c_str(), argv.data(), envp.data());
        const char* msg = "execve failed\n"; ssize_t r = write(2, msg, strlen(msg)); (void)r;
        _exit(127);
    }
    if (prefix_lock >= 0) close(prefix_lock);
    if (logfd >= 0) close(logfd);
    if (pid < 0) { log("fork() failed"); return -1; }
    {
        std::lock_guard<std::mutex> l(mu_);
        procs_.push_back({ pid, spec.label, spec.log_path, true, 0, util::time_now_hms(), spec.prefix_path });
        messages_.push_back("[" + util::time_now_hms() + "] Started '" + spec.label + "' (pid " + std::to_string(pid) + ") log: " + spec.log_path);
    }
    return pid;
}
