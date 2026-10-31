// Session-only four-face ownership. Existing windows are retained on overflow
// faces and restored on disable if the user has not moved them in the meantime.
std::string workspaceAddress(PHLWORKSPACE workspace) {
    return workspace->m_id > 0 ? std::to_string(workspace->m_id) : "name:"+workspace->m_name;
}
struct FaceOwner { PHLWORKSPACE workspace; bool persistent; };
struct FoldedWindow { PHLWINDOWREF window; PHLWORKSPACE from, to; };
std::map<std::string, std::vector<FaceOwner>> monitorFaces;
std::vector<FoldedWindow> foldedWindows;
std::function<SDispatchResult(std::string)> ordinaryWorkspace, ordinaryMove;
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
                auto name=faces[i].workspace->m_name;std::replace(name.begin(),name.end(),'\n',' ');
                out << faces[i].workspace->m_id << ' ' << i+1 << '\t' << name << '\n';
            }
    out.close();
    std::error_code ec;
    std::filesystem::rename(temporary, path, ec);
}
void releaseFaces() {
    for (auto &fold : foldedWindows)
        if (auto w = fold.window.lock(); w && w->m_isMapped && valid(fold.from) &&
            w->m_workspace == fold.to && fold.from->m_monitor == fold.to->m_monitor)
            ordinaryMove(std::format("{},address:0x{:x}", workspaceAddress(fold.from), reinterpret_cast<uintptr_t>(w.get())));
    foldedWindows.clear();
    for (auto &[name, faces] : monitorFaces)
        for (auto &face : faces)
            if (valid(face.workspace)) face.workspace->setPersistent(face.persistent);
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
            if (valid(f.workspace)) f.workspace->setPersistent(f.persistent);
            return true;
        });
        auto candidates = Cube::faces(workspaceList(), m->m_id, m->activeWorkspaceID());
        // Keep the visible desktop in the first four when enabling an old setup.
        if (faces.empty() && candidates.size() > 4 &&
            std::find(candidates.begin(), candidates.begin()+4, m->activeWorkspaceID()) == candidates.begin()+4) {
            candidates[3] = m->activeWorkspaceID(); candidates.resize(4); std::sort(candidates.begin(), candidates.end());
        }
        for (auto id : candidates) {
            if (!id || faces.size() == 4) break;
            if (std::any_of(faces.begin(), faces.end(), [&](auto &f) { return f.workspace->m_id == id; })) continue;
            auto w = State::workspaceState()->query().id(id).run();
            if (valid(w) && w->m_monitor == m) faces.push_back({w, w->isPersistent()});
        }
        while (faces.size() < 4) {
            auto used = workspaceList();
            for (auto &rule : Config::workspaceRuleMgr()->getAllWorkspaceRules())
                if (rule->isEnabled() && rule->m_workspaceId > 0) used.push_back({rule->m_workspaceId, -1, false});
            auto w = State::workspaceState()->create(Cube::unusedID(used), m->m_id);
            faces.push_back({w, false});
        }
        std::sort(faces.begin(), faces.end(), [](auto &a, auto &b) { return a.workspace->m_id < b.workspace->m_id; });
        for (auto &f : faces) f.workspace->setPersistent(true);
        auto destination = faces.back().workspace;
        for (auto w : Desktop::windowState()->windows()) {
            if (!w->m_isMapped || w->m_monitor != m || !w->m_workspace || w->onSpecialWorkspace()) continue;
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
        for (auto &f : pair.second) if (valid(f.workspace)) f.workspace->setPersistent(f.persistent);
        return true;
    });
    writeFaceState();
}
void scheduleFaces() {
    if (!reconcilingFaces && faceTimer) faceTimer->updateTimeout(std::chrono::milliseconds(50));
}
std::vector<WORKSPACEID> faceIDs(PHLMONITOR m) {
    auto it = monitorFaces.find(m->m_name);
    if (it == monitorFaces.end()) return Cube::faces(workspaceList(), m->m_id, m->activeWorkspaceID());
    std::vector<WORKSPACEID> ids;
    for (auto &f : it->second) ids.push_back(f.workspace->m_id);
    return ids;
}
