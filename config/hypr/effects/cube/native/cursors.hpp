// Optional pointer trails share the existing renderer adapter. No polling process,
// input interception, shared desktop settings, or frames while effects are idle.
struct CursorOptions {
    std::string style = "pearl", trail = "none";
    int size = 32, duration = 420, intensity = 65;
    bool ripple = false;
    Color color = {.22,.74,.97,1};
} cursorOptions;
struct CursorMark { Vector2D position; Clock::time_point born; bool click; };
std::vector<CursorMark> cursorMarks;
SP<CEventLoopTimer> cursorTimer;
void damageMarks() {
    for (auto &mark : cursorMarks)
        g_pHyprRenderer->damageBox(CBox{mark.position.x-42,mark.position.y-42,84,84});
}
void clearMarks() {
    damageMarks(); cursorMarks.clear();
    if (cursorTimer) cursorTimer->updateTimeout(std::nullopt);
}
bool cursorVisible(PHLMONITOR m) {
    return m && !PROTO::inputCapture->isCaptured() && !g_pSessionLockManager->isSessionLocked() && !g_pInputManager->isConstrained() &&
        std::any_of(cursorMarks.begin(),cursorMarks.end(),[&](auto &mark) {
            return mark.position.x+42 >= m->m_position.x && mark.position.x-42 < m->m_position.x+m->m_size.x &&
                mark.position.y+42 >= m->m_position.y && mark.position.y-42 < m->m_position.y+m->m_size.y;
        });
}
void reloadCursors() {
    auto root = configPath().parent_path().parent_path().parent_path();
    auto path = root/"cursors/settings.json";
    if (!std::filesystem::exists(path)) return;
    if (std::filesystem::file_size(path)>4096) throw std::runtime_error("Cursor settings too large");
    Cube::Json json(json_object_from_file(path.c_str()),json_object_put);
    if (!json || !json_object_is_type(json.get(),json_type_object)) throw std::runtime_error("Invalid cursor settings");
    CursorOptions next;
    auto member = [&](const char *key, json_type type) {
        json_object *value=nullptr;
        if (!json_object_object_get_ex(json.get(),key,&value) || !json_object_is_type(value,type))
            throw std::runtime_error(std::string("Invalid cursor setting: ")+key);
        return value;
    };
    next.style=json_object_get_string(member("style",json_type_string));
    next.trail=json_object_get_string(member("trail",json_type_string));
    if (!std::set<std::string>{"pearl","carbon","cyan","orchid","ember"}.contains(next.style) ||
        !std::set<std::string>{"none","comet","glow","sparkle"}.contains(next.trail)) throw std::runtime_error("Unknown cursor style or trail");
    next.size=json_object_get_int(member("size",json_type_int));
    next.duration=json_object_get_int(member("duration",json_type_int));
    next.intensity=json_object_get_int(member("intensity",json_type_int));
    next.ripple=json_object_get_boolean(member("click_ripple",json_type_boolean));
    std::string color=json_object_get_string(member("color",json_type_string));
    if (next.size<20 || next.size>64 || next.duration<100 || next.duration>1000 || next.intensity<10 || next.intensity>100 ||
        !std::regex_match(color,std::regex("#[a-fA-F0-9]{6}"))) throw std::runtime_error("Invalid cursor size or effect");
    for (int i=0;i<3;++i) next.color[i]=std::stoi(color.substr(1+i*2,2),nullptr,16)/255.f;
    auto data = root/"cursors/.build/data";
    auto theme = "Xetal-Cursor-"+next.style;
    if (!std::filesystem::exists(data/"icons"/theme/"manifest.hl")) throw std::runtime_error("Cursor artwork needs building. Apply cursors again.");
    // The compositor and its children get a profile-local search path only.
    const std::string priorData = std::getenv("XDG_DATA_DIRS") ? std::getenv("XDG_DATA_DIRS") : "/usr/local/share:/usr/share";
    const std::string priorIcons = std::getenv("XCURSOR_PATH") ? std::getenv("XCURSOR_PATH") : "/usr/share/icons";
    if (priorData.find(data.string())==std::string::npos) setenv("XDG_DATA_DIRS",(data.string()+":"+priorData).c_str(),1);
    if (priorIcons.find(data.string())==std::string::npos) setenv("XCURSOR_PATH",((data/"icons").string()+":"+priorIcons).c_str(),1);
    setenv("XCURSOR_THEME",theme.c_str(),1);setenv("XCURSOR_SIZE",std::to_string(next.size).c_str(),1);
    setenv("HYPRCURSOR_THEME",theme.c_str(),1);setenv("HYPRCURSOR_SIZE",std::to_string(next.size).c_str(),1);
    // Direct changeTheme deliberately avoids syncGsettings(), which would affect KDE.
    Pointer::Cursor::mgr()->changeTheme(theme,next.size);
    Pointer::Cursor::mgr()->setCursorFromName("left_ptr");
    Pointer::Cursor::mgr()->setXWaylandCursor();
    clearMarks();cursorOptions=next;
}
void addCursorMark(Vector2D position, bool click) {
    if ((click ? !cursorOptions.ripple : cursorOptions.trail=="none") || g_pSessionLockManager->isSessionLocked() ||
        g_pInputManager->isConstrained() || !g_pCompositor->m_sessionActive || PROTO::inputCapture->isCaptured()) return;
    auto now=Clock::now();
    if (!click && !cursorMarks.empty()) {
        auto &last=cursorMarks.back();
        if (!last.click && ((position-last.position).size()<2 || std::chrono::duration<double,std::milli>(now-last.born).count()<8)) return;
    }
    damageMarks();
    cursorMarks.push_back({position,now,click});
    if (cursorMarks.size()>96) cursorMarks.erase(cursorMarks.begin());
    damageMarks();
    if (auto m=State::monitorState()->query().vec(position).run()) m->recheckSolitary();
    cursorTimer->updateTimeout(std::chrono::milliseconds(16));
}
class CursorPass : public IPassElement {
    PHLMONITORREF monitor;
  public:
    explicit CursorPass(PHLMONITOR m):monitor(m) {}
    bool needsLiveBlur() override { return false; }
    bool needsPrecomputeBlur() override { return false; }
    const char *passName() override { return "XetalCursorEffects"; }
    ePassElementType type() override { return EK_CUSTOM; }
    bool disableSimplification() override { return true; }
    std::vector<UP<IPassElement>> draw() override {
        auto m=monitor.lock();
        if (stopping || !cursorVisible(m)) return {};
        Cube::GLState restore; graphics.begin(m);
        const auto now=Clock::now();
        for (auto &mark:cursorMarks) {
            double age=std::chrono::duration<double,std::milli>(now-mark.born).count()/cursorOptions.duration;
            if (age>=1) continue;
            const auto p=(mark.position-m->m_position)*m->m_scale;
            double radius=(mark.click? 6+age*28 : cursorOptions.trail=="glow" ? 12*(1-age) : 4*(1-age))*m->m_scale;
            auto color=cursorOptions.color;color[3]=(1-age)*cursorOptions.intensity/100.;
            glUniform1i(graphics.skyMode, cursorOptions.trail=="glow" && !mark.click ? 4 : 0);
            Cube::Polygon shape;shape.color=color;
            const int sides=cursorOptions.trail=="sparkle" && !mark.click ? 8:24;
            for(int n=0;n<sides;++n) {
                auto vertex=[&](int index,double r) {
                    double a=2*Cube::PI*index/sides;
                    if(sides==8 && index%2)r*=.27;
                    return Cube::Vertex{float((p.x+std::cos(a)*r)/m->m_transformedSize.x),float((p.y+std::sin(a)*r)/m->m_transformedSize.y),1,float(.5+std::cos(a)*.5),float(.5+std::sin(a)*.5)};
                };
                auto a=vertex(n,radius),b=vertex(n+1,radius);
                if(mark.click) {
                    auto c=vertex(n,std::max(0.,radius-2*m->m_scale)),d=vertex(n+1,std::max(0.,radius-2*m->m_scale));
                    shape.vertices.insert(shape.vertices.end(),{a,b,c,b,d,c});
                } else shape.vertices.insert(shape.vertices.end(),{{float(p.x/m->m_transformedSize.x),float(p.y/m->m_transformedSize.y),1,.5,.5},a,b});
            }
            graphics.draw(shape);
        }
        return {};
    }
};
