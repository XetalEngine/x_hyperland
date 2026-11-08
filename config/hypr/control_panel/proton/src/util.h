#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace util {
std::string home_dir();
std::string data_dir();     // ~/.local/share/XetalProton
std::string config_dir();   // ~/.config/XetalProton
std::string logs_dir();     // data_dir()/logs
std::string tools_dir();    // app-owned Proton and UMU installations
std::string runtimes_dir(); // app-owned UMU runtime storage
bool file_exists(const std::string& p);
bool dir_exists(const std::string& p);
bool mkdirs(const std::string& p);
bool read_file(const std::string& p, std::string& out);
bool read_file_bytes(const std::string& p, std::vector<uint8_t>& out, size_t max_bytes = 0);
bool write_file(const std::string& p, const std::string& data);
std::string basename(const std::string& p);
std::string dirname(const std::string& p);
std::string strip_ext(const std::string& name);
std::string lower(std::string s);
std::string trim(const std::string& s);
bool ends_with_ci(const std::string& s, const std::string& suffix);
std::string sanitize_filename(const std::string& s);
std::string shell_quote(const std::string& s);
std::string timestamp(const char* fmt = "%Y%m%d-%H%M%S");
std::string time_now_hms();
std::vector<std::string> split_args(const std::string& s);   // shell-like splitting with quotes
std::vector<std::string> list_dir(const std::string& p, bool dirs_only = false);
bool which(const std::string& exe, std::string* full = nullptr);
void spawn_detached(const std::vector<std::string>& argv);   // fire & forget (dolphin, xdg-open)
std::string run_capture(const std::vector<std::string>& argv, int* exit_code = nullptr); // blocking
uint64_t dir_size_bytes(const std::string& p);
std::string human_size(uint64_t bytes);
}
