#include "desktop.h"
#include "src/util.h"
#include <QDir>
#include <QFileInfo>
#include <QRegularExpression>

namespace XetalProton::Desktop {
QString root() { return qEnvironmentVariable("XETAL_HYPR_ROOT",QDir::homePath()+"/.config/hypr"); }
QString bridge() {
    const auto installed=root()+"/control_panel/proton/desktop_bridge.py";
    return QFileInfo::exists(installed)?installed:QString::fromUtf8(XETAL_PROTON_BRIDGE_PATH);
}
QString storage() { return QString::fromStdString(util::data_dir())+"/desktop-handlers"; }
QString manifest(const std::string &id) { return storage()+"/"+QString::fromStdString(id)+".json"; }
QStringList schemes(const std::string &value) {
    auto values=QString::fromStdString(value).toLower().split(QRegularExpression("[\\s,;]+"),Qt::SkipEmptyParts);
    values.removeDuplicates(); return values;
}
QString validate(const Shortcut &s) {
    if(!s.desktop.enabled)return {};
    if(!QRegularExpression("^[A-Za-z0-9_-]{1,128}$").match(QString::fromStdString(s.id)).hasMatch())return "Invalid shortcut identifier.";
    const auto values=schemes(s.desktop.schemes);
    if(values.isEmpty())return "Enter at least one custom URL scheme, such as grasshopper.";
    for(const auto &value:values)
        if(!QRegularExpression("^[a-z][a-z0-9+.-]*$").match(value).hasMatch() || QStringList{"http","https","file","ftp","mailto","data","javascript","about"}.contains(value))
            return "Enter custom URL schemes without ://. Web and file schemes are reserved.";
    const auto argument=QString::fromStdString(s.desktop.argument);
    if(argument.count("{url}")!=1 || argument.contains(QRegularExpression("[\\x00-\\x1f]")))
        return "The URL argument must contain {url} exactly once, with no line breaks.";
    if(s.verb=="waitforexitandrun")return "Browser sign-in needs the run verb so a callback can reach an already-running application.";
    return {};
}
LaunchSpec managedLaunch(LaunchSpec spec,const Shortcut &s) {
    if(s.desktop.enabled && spec.error.empty()) {
        spec.argv={"python3",bridge().toStdString(),"--launch",manifest(s.id).toStdString(),"--"};
        spec.private_output=s.desktop.private_output;
    }
    return spec;
}
}
