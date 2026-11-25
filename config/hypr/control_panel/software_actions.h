#pragma once
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QRegularExpression>
#include <QStringList>
#include "backend/script_helpers.h"

namespace SoftwareActions {
inline QString pinCommand(const QString &root,const QString &package) {
    return "python3 "+shQuote(root+"/control_panel/software_favorites.py")+" --package "+shQuote(package);
}
inline QString removePackage(const QString &name) {
    static const QRegularExpression valid("^[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\\-]*$");
    if(!valid.match(name).hasMatch())return {};
    return "sudo pacman -R -- "+shQuote(name)+"\nsoftware_remove_status=$?\n"
        "printf '\\n'\nif [ \"$software_remove_status\" -eq 0 ]; then\n"
        "printf '%s\\n' 'Application uninstalled.'\nelse\nprintf '%s\\n' 'Uninstall did not complete. Check the output above.'\nfi\n"
        "read -r -p 'Press Enter to close...'\nexit \"$software_remove_status\"\n";
}

// Only published per-user installer locations can be removed automatically.
// A development checkout or an arbitrary portable directory is never inferred
// to be an installation from a desktop file alone.
inline QStringList localRemovalPaths(const QString &product,const QString &desktop,const QString &home=QDir::homePath()) {
    const QHash<QString,QStringList> locations{
        {"echo",{".local/share/echo",".local/opt/Echo"}},
        {"linuxstudio",{".local/opt/LinuxStudio"}},
        {"xmusic",{".local/opt/XMusic"}},
        {"xvideo",{".local/opt/XVideo"}}
    };
    if(!locations.contains(product))return {};
    const QDir base(home);const QFileInfo launcher(desktop);
    if(launcher.isSymLink()||launcher.absolutePath()!=base.filePath(".local/share/applications")||!launcher.isFile())return {};
    QFile file(desktop);if(!file.open(QIODevice::ReadOnly))return {};
    const QString text=QString::fromUtf8(file.read(64*1024));
    const auto exec=QRegularExpression("^Exec=(.*)$",QRegularExpression::MultilineOption).match(text).captured(1);
    for(const auto &relative:locations[product]){
        const QString folder=base.filePath(relative);const QFileInfo info(folder);
        if(!info.isDir()||info.isSymLink()||info.canonicalFilePath()!=QDir::cleanPath(folder))continue;
        if(!QFileInfo::exists(folder+"/run.sh")||!exec.contains(folder+"/run.sh"))continue;
        return {folder,launcher.absoluteFilePath()};
    }
    return {};
}
}
