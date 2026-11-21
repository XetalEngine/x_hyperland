// Session-only four-face ownership. Existing windows are retained on overflow
// faces and restored on disable if the user has not moved them in the meantime.
std::string workspaceAddress(PHLWORKSPACE workspace) {
    return workspace->addressableName();
}
struct FaceOwner { PHLWORKSPACE workspace; bool persistent; };
struct FoldedWindow { PHLWINDOWREF window; PHLWORKSPACE from, to; };
std::map<std::string, std::vector<FaceOwner>> monitorFaces;
std::vector<FoldedWindow> foldedWindows;
using WorkspaceActionFn=Config::Actions::ActionResult (*)(PHLWORKSPACE);
WorkspaceActionFn nativeWorkspace=nullptr;
bool bypassWorkspace=false;
SDispatchResult ordinaryWorkspace(const std::string& input) {
    const auto previous=bypassWorkspace;bypassWorkspace=true;
    Hyprutils::Utils::CScopeGuard guard([&]{bypassWorkspace=previous;});
    return Fusion057::result(Config::Actions::changeWorkspace(input));
}
SDispatchResult ordinaryMove(const std::string& input) {
    const auto comma=input.find(',');
    const auto window=comma==std::string::npos?Desktop::focusState()->window():Desktop::viewState()->query().selector(input.substr(comma+1)).runWindow();
    return Fusion057::result(Config::Actions::moveToWorkspace(input.substr(0,comma),true,window));
}
bool persistent(PHLWORKSPACE w) {
    const auto regular=dynamicPointerCast<Workspace::CRegularWorkspace>(w);
    return regular&&regular->isPersistent();
}
void setPersistent(PHLWORKSPACE w,bool enabled) {
    if(auto regular=dynamicPointerCast<Workspace::CRegularWorkspace>(w))regular->setPersistent(enabled);
}
int64_t ruleID(const Config::CWorkspaceRule& rule) {
    try {size_t end=0;const auto id=std::stoll(rule.m_workspaceString,&end);return end==rule.m_workspaceString.size()&&id>0?id:0;}
    catch(...){return 0;}
}
SP<CEventLoopTimer> faceTimer;
bool reconcilingFaces = false;

std::filesystem::path faceStatePath() {
    const char *runtime = std::getenv("XDG_RUNTIME_DIR"), *signature = std::getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if (!runtime || !signature || std::string(signature).find('/') != std::string::npos) return {};
    return std::filesystem::path(runtime)/"hypr"/signature/"xetal-cube-faces";
}
void writeFaceState() {
    auto path = faceStatePath();
    if (path.empty()) return;
    auto temporary = path.string()+".tmp";
    std::ofstream out(temporary);
    out << (settings.enabled && !stopping ? "enabled\n" : "disabled\n");
    if (settings.enabled && !stopping)
        for (auto &[name, faces] : monitorFaces)
            for (size_t i = 0; i < faces.size(); ++i) {
                auto name=faces[i].workspace->displayName();std::replace(name.begin(),name.end(),'\n',' ');
                out << Fusion057::numberedID(faces[i].workspace) << ' ' << i+1 << '\t' << name << '\n';
            }
    out.close();
    std::error_code ec;
    std::filesystem::rename(temporary, path, ec);
}
void releaseFaces() {
    for (auto &fold : foldedWindows)
        if (auto w = fold.window.lock(); w && w->mapped() && valid(fold.from) &&
            w->m_workspace == fold.to && fold.from->m_monitor == fold.to->m_monitor)
            ordinaryMove(std::format("{},address:0x{:x}", workspaceAddress(fold.from), reinterpret_cast<uintptr_t>(w.get())));
    foldedWindows.clear();
    for (auto &[name, faces] : monitorFaces)
        for (auto &face : faces)
            if (valid(face.workspace)) setPersistent(face.workspace,face.persistent);
    monitorFaces.clear();
    writeFaceState();
}
void reconcileFaces() {
    if (reconcilingFaces || scene) { if (faceTimer) faceTimer->updateTimeout(std::chrono::milliseconds(100)); return; }
    reconcilingFaces = true;
    Hyprutils::Utils::CScopeGuard guard([] { reconcilingFaces = false; });
    if (!settings.enabled || stopping) { releaseFaces(); return; }
    std::set<std::string> connected;
    for (auto m : State::monitorState()->monitors()) {
        if (!m || m->isMirror() || !m->m_activeWorkspace) continue;
        connected.insert(m->m_name);
        auto &faces = monitorFaces[m->m_name];
        std::erase_if(faces, [&](auto &f) {
            if (valid(f.workspace) && f.workspace->m_monitor == m) return false;
            if (valid(f.workspace)) setPersistent(f.workspace,f.persistent);
            return true;
        });
        auto candidates = Cube::faces(workspaceList(), m->m_id, Fusion057::numberedID(m->m_activeWorkspace));
        // Keep the visible desktop in the first four when enabling an old setup.
        if (faces.empty() && candidates.size() > 4 &&
            std::find(candidates.begin(), candidates.begin()+4, Fusion057::numberedID(m->m_activeWorkspace)) == candidates.begin()+4) {
            candidates[3] = Fusion057::numberedID(m->m_activeWorkspace); candidates.resize(4); std::sort(candidates.begin(), candidates.end());
        }
        for (auto id : candidates) {
            if (!id || faces.size() == 4) break;
            if (std::any_of(faces.begin(), faces.end(), [&](auto &f) { return Fusion057::numberedID(f.workspace) == id; })) continue;
            auto w = State::workspaceState()->query().numbered(Workspace::SWorkspaceNumberedID{uint32_t(id)}).run();
            if (valid(w) && w->m_monitor == m) faces.push_back({w, persistent(w)});
        }
        while (faces.size() < 4) {
            auto used = workspaceList();
            for (auto &rule : Config::workspaceRuleMgr()->getAllWorkspaceRules())
                if (rule->isEnabled() && ruleID(*rule) > 0) used.push_back({ruleID(*rule), -1, false});
            auto w = State::workspaceState()->createNumbered(Workspace::SWorkspaceNumberedID{uint32_t(Cube::unusedID(used))}, m);
            if(!w)throw std::runtime_error("Cannot create a cube workspace");
            w->ready();faces.push_back({w, false});
        }
        std::sort(faces.begin(), faces.end(), [](auto &a, auto &b) { return Fusion057::numberedID(a.workspace) < Fusion057::numberedID(b.workspace); });
        for (auto &f : faces) setPersistent(f.workspace,true);
        auto destination = faces.back().workspace;
        for (auto w : Desktop::windowState()->windows()) {
            if (!w->mapped() || w->m_monitor != m || !w->m_workspace || w->onSpecialWorkspace()) continue;
            if (std::any_of(faces.begin(), faces.end(), [&](auto &f) { return f.workspace == w->m_workspace; })) continue;
            auto from = w->m_workspace;
            auto result = ordinaryMove(std::format("{},address:0x{:x}", workspaceAddress(destination), reinterpret_cast<uintptr_t>(w.get())));
            if (result.success) foldedWindows.push_back({w, from, destination});
        }
        if (std::none_of(faces.begin(), faces.end(), [&](auto &f) { return f.workspace == m->m_activeWorkspace; }))
            m->changeWorkspace(destination, false, true);
    }
    std::erase_if(monitorFaces, [&](auto &pair) {
        if (connected.contains(pair.first)) return false;
        for (auto &f : pair.second) if (valid(f.workspace)) setPersistent(f.workspace,f.persistent);
        return true;
    });
    writeFaceState();
}
void scheduleFaces() {
    if (!reconcilingFaces && faceTimer) faceTimer->updateTimeout(std::chrono::milliseconds(50));
}
std::vector<int64_t> faceIDs(PHLMONITOR m) {
    auto it = monitorFaces.find(m->m_name);
    if (it == monitorFaces.end()) return Cube::faces(workspaceList(), m->m_id, Fusion057::numberedID(m->m_activeWorkspace));
    std::vector<int64_t> ids;
    for (auto &f : it->second) ids.push_back(Fusion057::numberedID(f.workspace));
    return ids;
}
