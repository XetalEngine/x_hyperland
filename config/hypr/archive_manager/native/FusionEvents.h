// SPDX-License-Identifier: LGPL-2.1-or-later
// HyperFusion's optional structured events for the pinned 7-Zip console.
// Compression and archive handling remain upstream 7-Zip code.
#ifndef FUSION_7ZIP_EVENTS_H
#define FUSION_7ZIP_EVENTS_H
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <sys/stat.h>
#include <string>
#include <mutex>
#include <chrono>
#include "../../../Common/StringConvert.h"
namespace FusionEvents {
inline int descriptor() {
  static int fd = [] { const char *s = getenv("FUSION_7ZIP_EVENT_FD"); return s ? atoi(s) : -1; }();
  return fd;
}
inline bool isSocket(UInt32 mode) {
  // Inspect the actual type, never a filename suffix. Link handling and every
  // other input type retain upstream semantics. Exclude before item counting.
  return descriptor() >= 0 && S_ISSOCK(mode);
}
inline std::mutex &mutex() { static std::mutex value; return value; }
inline std::string quote(const wchar_t *value) {
  AString utf8;
  UnicodeStringToMultiByte2(utf8, UString(value ? value : L""), CP_UTF8);
  std::string out = "\"";
  const char hex[] = "0123456789abcdef";
  for (unsigned i = 0; i < utf8.Len(); ++i) {
    const unsigned char c = (unsigned char)utf8[i];
    if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
    else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
    else out += (char)c;
  }
  return out + '"';
}
inline void send(const std::string &body) {
  if (descriptor() < 0) return;
  const std::string line = "{" + body + "}\n";
  std::lock_guard<std::mutex> lock(mutex());
  size_t at = 0;
  while (at < line.size()) {
    const ssize_t n = write(descriptor(), line.data() + at, line.size() - at);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) break;
    at += (size_t)n;
  }
}
inline void progress(UInt64 total, UInt64 completed, UInt64 files, const wchar_t *name, const char *command, bool force = false) {
  if (descriptor() < 0) return;
  static std::mutex throttle;
  std::lock_guard<std::mutex> lock(throttle);
  static auto last = std::chrono::steady_clock::now() - std::chrono::seconds(1);
  const auto now = std::chrono::steady_clock::now();
  if (!force && now - last < std::chrono::milliseconds(80)) return;
  last = now;
  send("\"event\":\"progress\",\"total\":" + std::to_string(total)
       + ",\"completed\":" + std::to_string(completed) + ",\"files\":" + std::to_string(files)
       + ",\"path\":" + quote(name) + ",\"command\":" + quote(GetUnicodeString(command, CP_UTF8)));
}
inline void error(const wchar_t *path, unsigned code, const char *stage) {
  send("\"event\":\"error\",\"path\":" + quote(path) + ",\"code\":" + std::to_string(code)
       + ",\"stage\":\"" + stage + "\"");
}
inline bool password(UString &value) {
  const char *setting = getenv("FUSION_7ZIP_PASSWORD_FD");
  if (!setting) { send("\"event\":\"password\""); return false; }
  static std::string saved = [setting] {
    std::string result;
    char buffer[1024];
    const int fd = atoi(setting);
    for (;;) {
      const ssize_t n = read(fd, buffer, sizeof(buffer));
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) break;
      result.append(buffer, (size_t)n);
    }
    close(fd);
    return result;
  }();
  value = GetUnicodeString(saved.c_str(), CP_UTF8);
  return true;
}
}
#endif
