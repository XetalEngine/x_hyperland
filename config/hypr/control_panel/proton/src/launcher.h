#pragma once
#include <string>
#include <vector>
#include <map>
#include <deque>
#include <mutex>
#include <functional>
#include <sys/types.h>
#include "steam.h"
#include "config.h"

struct LaunchSpec {
    std::vector<std::string> argv;
    std::map<std::string, std::string> env;
    std::string cwd;
    std::string log_path;
    std::string label;
    std::string error;   // non-empty if the spec could not be built
    std::string prefix_path; // compatdata-style parent; always contains pfx/
    bool exclusive_prefix = false; // dependency installers must not overlap launches
};

// Build the full command for running `exe args` inside `prefix_path` with `proton`.
// verb: run | waitforexitandrun | runinprefix. For runinprefix, exe is passed to wine verbatim (e.g. "winecfg").
LaunchSpec build_launch(const ProtonVersion& proton, const std::string& prefix_path,
                        const std::string& exe, const std::string& args, const std::string& verb, bool use_runtime,
                        const std::map<std::string, std::string>& options, const std::string& custom_env,
                        const std::string& workdir, const std::string& label);

std::string spec_to_shell(const LaunchSpec& s);   // human-readable preview
std::string spec_to_script(const LaunchSpec& s);  // standalone .sh

struct ProcInfo { pid_t pid; std::string label; std::string log_path; bool running; int exit_code; std::string started; std::string prefix_path; };

class ProcessManager {
public:
    ~ProcessManager();
    pid_t start(const LaunchSpec& spec);
    void kill(pid_t pid, bool hard = false);
    std::vector<ProcInfo> snapshot();
    std::vector<std::string> drain_messages();
    void log(const std::string& msg);
private:
    void reap_locked();
    std::mutex mu_;
    std::vector<ProcInfo> procs_;
    std::deque<std::string> messages_;
};
