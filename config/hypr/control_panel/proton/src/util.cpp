#include "util.h"
#include <filesystem>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <signal.h>

namespace fs = std::filesystem;

namespace util {

std::string home_dir() {
    const char* h = getenv("HOME");
    return h ? h : "/tmp";
}
std::string data_dir() {
    const char* portable = getenv("XETALPROTON_HOME");
    if (portable && *portable) return fs::absolute(portable).lexically_normal().string();
    const char* x = getenv("XDG_DATA_HOME");
    std::string base = (x && *x) ? x : home_dir() + "/.local/share";
    return base + "/XetalProton";
}
std::string config_dir() {
    const char* portable = getenv("XETALPROTON_HOME");
    if (portable && *portable) return data_dir() + "/config";
    const char* x = getenv("XDG_CONFIG_HOME");
    std::string base = (x && *x) ? x : home_dir() + "/.config";
    return base + "/XetalProton";
}
std::string logs_dir() { return data_dir() + "/logs"; }
std::string tools_dir() { return data_dir() + "/tools"; }
std::string runtimes_dir() { return data_dir() + "/runtimes"; }

bool file_exists(const std::string& p) { std::error_code ec; return fs::is_regular_file(p, ec); }
bool dir_exists(const std::string& p) { std::error_code ec; return fs::is_directory(p, ec); }
bool mkdirs(const std::string& p) { std::error_code ec; fs::create_directories(p, ec); return !ec || dir_exists(p); }

bool read_file(const std::string& p, std::string& out) {
    std::ifstream f(p, std::ios::binary);
    if (!f) return false;
    std::stringstream ss; ss << f.rdbuf(); out = ss.str();
    return true;
}
bool read_file_bytes(const std::string& p, std::vector<uint8_t>& out, size_t max_bytes) {
    std::ifstream f(p, std::ios::binary);
    if (!f) return false;
    f.seekg(0, std::ios::end);
    size_t n = (size_t)f.tellg();
    f.seekg(0);
    if (max_bytes && n > max_bytes) n = max_bytes;
    out.resize(n);
    if (n) f.read((char*)out.data(), (std::streamsize)n);
    return true;
}
bool write_file(const std::string& p, const std::string& data) {
    mkdirs(dirname(p));
    std::string tmp = p + ".tmp";
    { std::ofstream f(tmp, std::ios::binary); if (!f) return false; f << data; }
    std::error_code ec; fs::rename(tmp, p, ec);
    return !ec;
}
std::string basename(const std::string& p) { return fs::path(p).filename().string(); }
std::string dirname(const std::string& p) { return fs::path(p).parent_path().string(); }
std::string strip_ext(const std::string& name) { return fs::path(name).stem().string(); }
std::string lower(std::string s) { std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return (char)std::tolower(c); }); return s; }
std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n"); if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n"); return s.substr(a, b - a + 1);
}
bool ends_with_ci(const std::string& s, const std::string& suffix) {
    if (s.size() < suffix.size()) return false;
    return lower(s.substr(s.size() - suffix.size())) == lower(suffix);
}
std::string sanitize_filename(const std::string& s) {
    std::string out;
    for (unsigned char c : s) out += (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == ' ') ? (char)c : '_';
    out = trim(out);
    if (out.empty()) out = "unnamed";
    return out;
}
std::string shell_quote(const std::string& s) {
    if (!s.empty() && s.find_first_of(" \t\n'\"\\$`!*?[](){};&|<>~#") == std::string::npos) return s;
    std::string out = "'";
    for (char c : s) { if (c == '\'') out += "'\\''"; else out += c; }
    return out + "'";
}
std::string timestamp(const char* fmt) {
    char buf[64]; time_t t = time(nullptr); struct tm tmv; localtime_r(&t, &tmv);
    strftime(buf, sizeof buf, fmt, &tmv); return buf;
}
std::string time_now_hms() { return timestamp("%H:%M:%S"); }

std::vector<std::string> split_args(const std::string& s) {
    std::vector<std::string> out; std::string cur; bool in_s = false, in_d = false, has = false;
    for (size_t i = 0; i < s.size(); i++) {
        char c = s[i];
        if (in_s) { if (c == '\'') in_s = false; else cur += c; continue; }
        if (in_d) { if (c == '"') in_d = false; else if (c == '\\' && i + 1 < s.size() && (s[i+1] == '"' || s[i+1] == '\\')) cur += s[++i]; else cur += c; continue; }
        if (c == '\'') { in_s = true; has = true; }
        else if (c == '"') { in_d = true; has = true; }
        else if (c == '\\' && i + 1 < s.size()) { cur += s[++i]; has = true; }
        else if (std::isspace((unsigned char)c)) { if (has || !cur.empty()) { out.push_back(cur); cur.clear(); has = false; } }
        else { cur += c; has = true; }
    }
    if (has || !cur.empty()) out.push_back(cur);
    return out;
}
std::vector<std::string> list_dir(const std::string& p, bool dirs_only) {
    std::vector<std::string> out; std::error_code ec;
    for (auto& e : fs::directory_iterator(p, ec)) {
        if (dirs_only && !e.is_directory(ec)) continue;
        out.push_back(e.path().string());
    }
    std::sort(out.begin(), out.end());
    return out;
}
bool which(const std::string& exe, std::string* full) {
    if (exe.find('/') != std::string::npos) { if (access(exe.c_str(), X_OK) == 0) { if (full) *full = exe; return true; } return false; }
    const char* path = getenv("PATH"); if (!path) return false;
    std::stringstream ss(path); std::string dir;
    while (std::getline(ss, dir, ':')) {
        if (dir.empty()) continue;
        std::string cand = dir + "/" + exe;
        if (access(cand.c_str(), X_OK) == 0) { if (full) *full = cand; return true; }
    }
    return false;
}
void spawn_detached(const std::vector<std::string>& argv) {
    if (argv.empty()) return;
    pid_t pid = fork();
    if (pid == 0) {
        if (fork() != 0) _exit(0);   // double fork so we never leave a zombie
        setsid();
        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) { dup2(devnull, 0); dup2(devnull, 1); dup2(devnull, 2); }
        std::vector<char*> av; for (auto& a : argv) av.push_back((char*)a.c_str()); av.push_back(nullptr);
        execvp(av[0], av.data());
        _exit(127);
    } else if (pid > 0) {
        int st; waitpid(pid, &st, 0);
    }
}
std::string run_capture(const std::vector<std::string>& argv, int* exit_code) {
    std::string out; if (argv.empty()) return out;
    int pfd[2]; if (pipe(pfd) != 0) return out;
    pid_t pid = fork();
    if (pid == 0) {
        close(pfd[0]); dup2(pfd[1], 1); close(pfd[1]);
        std::vector<char*> av; for (auto& a : argv) av.push_back((char*)a.c_str()); av.push_back(nullptr);
        execvp(av[0], av.data());
        _exit(127);
    }
    close(pfd[1]);
    if (pid < 0) { close(pfd[0]); return out; }
    char buf[4096]; ssize_t n;
    while ((n = read(pfd[0], buf, sizeof buf)) > 0) out.append(buf, (size_t)n);
    close(pfd[0]);
    int st = 0; waitpid(pid, &st, 0);
    if (exit_code) *exit_code = WIFEXITED(st) ? WEXITSTATUS(st) : -1;
    return out;
}
uint64_t dir_size_bytes(const std::string& p) {
    uint64_t total = 0; std::error_code ec;
    for (auto it = fs::recursive_directory_iterator(p, fs::directory_options::skip_permission_denied, ec); it != fs::recursive_directory_iterator(); it.increment(ec)) {
        if (ec) break;
        if (it->is_symlink(ec)) continue;
        if (it->is_regular_file(ec)) { struct stat st; if (lstat(it->path().c_str(), &st) == 0) total += (uint64_t)st.st_blocks * 512; }
    }
    return total;
}
std::string human_size(uint64_t b) {
    const char* u[] = {"B","KB","MB","GB","TB"}; double v = (double)b; int i = 0;
    while (v >= 1024 && i < 4) { v /= 1024; i++; }
    char buf[32]; snprintf(buf, sizeof buf, i == 0 ? "%.0f %s" : "%.1f %s", v, u[i]); return buf;
}
}
