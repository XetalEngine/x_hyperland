// Optional pointer trails share the existing renderer adapter. No polling process,
// input interception, shared desktop settings, or frames while effects are idle.
#include "cursor_art.hpp"
struct CursorOptions {
    std::string style = "pearl", trail = "none", effect = "none";
    int size = 32, duration = 420, intensity = 65;
    bool ripple = false;
    Color color = {.22,.74,.97,1};
    std::array<Color,3> colors;
} cursorOptions;
std::vector<MouseArt::Mark> cursorMarks;
PHLMONITORREF cursorRenderingMonitor;
unsigned cursorSeed=0;
uint64_t cursorFrames=0,cursorVertices=0;
double cursorNow(){return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();}
void damageMarks(PHLMONITOR only=nullptr) {
    for (auto &mark : cursorMarks) {
        CBox b{mark.p.x-64,mark.p.y-64,128,128};
        if(!only)g_pHyprRenderer->damageBox(b);
        else {
            CRegion region(b);region.translate(-only->m_position).scale(only->m_scale);
            region.intersect(CBox{0,0,only->m_transformedSize.x,only->m_transformedSize.y});
            if(!region.empty())only->addDamage(region);
        }
    }
}
void clearMarks() {
    damageMarks(); cursorMarks.clear();
}
bool cursorVisible(PHLMONITOR m) {
    return m && !PROTO::inputCapture->isCaptured() && !g_pSessionLockManager->isSessionLocked() && !g_pInputManager->isConstrained() &&
        std::any_of(cursorMarks.begin(),cursorMarks.end(),[&](auto &mark) {
            return mark.p.x+64 >= m->m_position.x && mark.p.x-64 < m->m_position.x+m->m_size.x &&
                mark.p.y+64 >= m->m_position.y && mark.p.y-64 < m->m_position.y+m->m_size.y;
        });
}
void reloadCursors() {
    auto root = configPath().parent_path().parent_path().parent_path();
    auto path = root/"cursors/settings.json";
    if(auto overridePath=std::getenv("XETAL_CURSOR_CONFIG")){path=overridePath;root=path.parent_path().parent_path();}
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
    if (!std::set<std::string>{"pearl","carbon","cyan","orchid","ember","sumi"}.contains(next.style) ||
        !std::set<std::string>{"none","follow","plasma","orbit","fracture","circuit","tidal","ink","cinder","cloud","blade","comet","glow","sparkle"}.contains(next.trail)) throw std::runtime_error("Unknown cursor style or trail");
    next.size=json_object_get_int(member("size",json_type_int));
    next.duration=json_object_get_int(member("duration",json_type_int));
    next.intensity=json_object_get_int(member("intensity",json_type_int));
    next.ripple=json_object_get_boolean(member("click_ripple",json_type_boolean));
    std::string color=json_object_get_string(member("color",json_type_string));
    if (next.size<20 || next.size>64 || next.duration<100 || next.duration>1000 || next.intensity<10 || next.intensity>100 ||
        !std::regex_match(color,std::regex("#[a-fA-F0-9]{6}"))) throw std::runtime_error("Invalid cursor size or effect");
    for (int i=0;i<3;++i) next.color[i]=std::stoi(color.substr(1+i*2,2),nullptr,16)/255.f;
    std::string design="raw";auto themePath=root/"theme/state.json";
    if(std::filesystem::exists(themePath)&&std::filesystem::file_size(themePath)<65536){
        Cube::Json theme(json_object_from_file(themePath.c_str()),json_object_put);json_object* value=nullptr;
        if(theme&&json_object_object_get_ex(theme.get(),"design",&value)&&json_object_is_type(value,json_type_string))design=json_object_get_string(value);
    }
    next.effect=MouseArt::resolve(next.trail,design);
    auto palette=MouseArt::palette(next.effect);
    for(int n=0;n<3;++n){for(int i=0;i<3;++i)next.colors[n][i]=std::stoi(palette[n].substr(1+i*2,2),nullptr,16)/255.f;next.colors[n][3]=1;}
    if(next.trail!="follow")next.colors[0]=next.color;
    if(std::set<std::string>{"none","comet","glow","sparkle"}.contains(next.effect))next.colors.fill(next.color);
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
    // Refuse fallback: XCursor's loadTheme also synchronizes shared GSettings.
    static auto useHyprcursor = CConfigValue<Config::INTEGER>("cursor:enable_hyprcursor");
    if (!*useHyprcursor) throw std::runtime_error("Enable cursor:enable_hyprcursor to use these cursor styles.");
    Hyprcursor::SManagerOptions options;
    options.allowDefaultFallback = false;
    Hyprcursor::CHyprcursorManager check(theme.c_str(), options);
    if (!check.valid() || !check.loadThemeStyle({static_cast<unsigned int>(next.size)}) ||
        check.getShape("left_ptr", {static_cast<unsigned int>(next.size)}).images.empty())
        throw std::runtime_error("The selected cursor theme could not be loaded. Apply cursors again to rebuild its artwork.");
    // Valid Hyprcursor themes avoid XCursor's shared-settings synchronization.
    Pointer::Cursor::mgr()->changeTheme(theme,next.size);
    Pointer::Cursor::mgr()->setCursorFromName("left_ptr");
    Pointer::Cursor::mgr()->setXWaylandCursor();
    clearMarks();cursorOptions=next;
}
void addCursorMark(Vector2D position, bool click) {
    if ((click ? !cursorOptions.ripple : cursorOptions.trail=="none") || g_pSessionLockManager->isSessionLocked() ||
        g_pInputManager->isConstrained() || !g_pCompositor->m_sessionActive || PROTO::inputCapture->isCaptured()) return;
    auto now=cursorNow();
    if (!click && !cursorMarks.empty()) {
        auto &last=cursorMarks.back();
        if (!last.click && std::hypot(position.x-last.p.x,position.y-last.p.y)<4) return;
    }
    MouseArt::Point p{position.x,position.y},direction{1,0};
    if(!cursorMarks.empty()){
        auto delta=p-cursorMarks.back().p;double distance=std::hypot(delta.x,delta.y);
        if(distance>0)direction=delta*(1/distance);
        // Teleports must not draw a line across the desktop. Distance-based
        // samples keep ribbons continuous regardless of mouse polling rate.
        if(!click&&!cursorMarks.back().click&&distance>=8&&distance<256){
            auto previous=cursorMarks.back();int count=std::min(24,int(distance/4));
            for(int i=1;i<count;++i)cursorMarks.push_back({previous.p+delta*(double(i)/count),direction,
                previous.born+(now-previous.born)*i/count,++cursorSeed,false});
        }
    }
    cursorMarks.push_back({p,direction,now,++cursorSeed,click});
    if (cursorMarks.size()>160){damageMarks();cursorMarks.erase(cursorMarks.begin(),cursorMarks.end()-160);}
    damageMarks();
    if (auto m=State::monitorState()->query().vec(position).run()) m->recheckSolitary();
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
        const auto art=MouseArt::make(cursorOptions.effect,cursorMarks,cursorNow(),cursorOptions.duration/1000.);
        glUniform1i(graphics.skyMode,5);++cursorFrames;
        for(size_t i=0;i<art.size();++i){
            Cube::Polygon shape;shape.color=cursorOptions.colors[i];shape.color[3]=cursorOptions.intensity/100.;
            shape.vertices.reserve(art[i].size());cursorVertices+=art[i].size();
            for(auto v:art[i])shape.vertices.push_back({float((v.x-m->m_position.x)*m->m_scale/m->m_transformedSize.x),
                float((v.y-m->m_position.y)*m->m_scale/m->m_transformedSize.y),1,v.alpha,0});
            graphics.draw(shape); // At most three uploads/draws per output.
        }
        return {};
    }
};
