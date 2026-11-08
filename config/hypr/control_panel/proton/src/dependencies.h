#pragma once
#include "launcher.h"
#include <map>
#include <set>
#include <string>
#include <vector>

namespace dependencies {
struct Component { std::string verb, name, category, description; };
struct Status {
    std::set<std::string> installed;
    std::map<std::string, std::string> failures;
};
const std::vector<Component>& catalog();
Status status(const std::string& prefix);
std::set<std::string> available(const ProtonVersion& proton);
LaunchSpec build_install(const ProtonVersion& proton, const std::string& prefix, const std::string& verb, bool retry = false);
void record_result(const std::string& prefix, const std::string& verb, const std::string& error);
bool busy(const std::string& prefix);
}
