#include "window_enum_hyprland.h"
#include "window_enum_backend.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QMap>
#include <QRegularExpression>
#include <QSet>

QString windowEnumAutomaticBackend(const QString &session, const QString &display,
                                   const QString &desktop, const QString &hyprland) {
    const auto name = desktop.toLower();
    if (session != "wayland" && display.isEmpty()) return "x11";
    if (!hyprland.isEmpty() || name.contains("hyprland")) return "hyprland";
    return name.contains("kde") ? "kwin" : name.contains("gnome") ? "gnome" : "wayland";
}

namespace {
HyprlandReply execute(const QStringList &arguments) {
    QProcess process;
    process.start("hyprctl", arguments);
    if (!process.waitForStarted(1500)) return {{}, "Could not start hyprctl: " + process.errorString()};
    if (!process.waitForFinished(2000)) {
        process.kill(); process.waitForFinished(1000);
        return {{}, "Hyprland did not answer. Refresh to reconnect."};
    }
    if (process.exitStatus() != QProcess::NormalExit || process.exitCode())
        return {{}, "Hyprland request failed: " + QString::fromUtf8(process.readAllStandardError()).left(500)};
    auto output = process.readAllStandardOutput();
    if (output.size() > 16*1024*1024) return {{}, "Hyprland returned too much window data."};
    return {output, {}};
}
bool addressValid(const QString &address) {
    static const QRegularExpression format("^0x[0-9a-fA-F]+$");
    return format.match(address).hasMatch() && address != "0x0";
}
QJsonObject base(const QString &id, const QString &type, const QJsonObject &raw) {
    return {{"id", id}, {"type", type}, {"backend", "hyprland"},
            {"geometryUnits", "Compositor logical pixels"}, {"capabilities", QJsonArray{}},
            {"nativeProperties", raw}};
}
}

QJsonObject windowEnumHyprland(const QJsonObject &request, HyprlandCommand command) {
    if (!command) command = execute;
    const auto action = request.value("action").toString();
    QString error;
    if (action != "list" && action != "details" && !windowEnumValidateAction(request, &error)) return {{"error", error}};
    auto query = [&](const QString &name, bool all = false) {
        QStringList args{"-j"}; if (all) args << "-a"; args << name;
        const auto reply = command(args);
        if (!reply.error.isEmpty()) { error = reply.error; return QJsonDocument(); }
        QJsonParseError parse;
        auto json = QJsonDocument::fromJson(reply.output, &parse);
        if (parse.error != QJsonParseError::NoError) error = "Invalid response from Hyprland (" + name + ").";
        return json;
    };
    const auto clients = query("clients", true);
    if (!clients.isArray()) return {{"error", error.isEmpty() ? "Hyprland did not return a window list." : error}};
    const auto metadata = query("xetal-windows").object(); // Optional on other Hyprland installations.
    const auto layers = query("layers");
    const auto monitors = query("monitors").array();
    const auto active = query("activewindow").object().value("address").toString();
    QJsonArray rows;
    QMap<QString, QJsonObject> owners;
    for (const auto &entry : clients.array()) {
        const auto raw = entry.toObject();
        const auto address = raw["address"].toString();
        if (!addressValid(address)) continue;
        const auto meta = metadata[address].toObject();
        const auto stable = raw["stableId"].toString(meta["stableId"].toString());
        const auto id = "hyprland:window:" + address + ":" + (stable.isEmpty() ? QString::number(raw["pid"].toInt()) : stable);
        const bool x11 = raw["xwayland"].toBool();
        const bool managed = meta["geometry_managed"].toBool(!x11);
        auto row = base(id, x11 ? (managed ? "XWayland window" : "XWayland unmanaged window") : "Wayland window", raw);
        for (const auto *key : {"title", "class", "pid", "mapped", "hidden", "floating", "pinned"})
            if (raw.contains(key)) row[key] = raw[key];
        row["appId"] = raw["class"];
        row["pidSource"] = "Hyprland client PID";
        row["managed"] = managed;
        row["active"] = address == active;
        row["maximized"] = raw["fullscreen"].toInt() == 1;
        row["fullscreen"] = raw["fullscreen"].toInt() == 2;
        if (raw.contains("visible")) row["visibility"] = raw["visible"].toBool() ? "Visible" : "Not visible";
        const auto at = raw["at"].toArray(), size = raw["size"].toArray();
        if (at.size() == 2) { row["x"] = at[0]; row["y"] = at[1]; }
        if (size.size() == 2) { row["width"] = size[0]; row["height"] = size[1]; }
        const auto workspace = raw["workspace"].toObject();
        row["desktop"] = workspace["id"].toInt() > 0 ? QJsonValue(workspace["id"].toInt()-1) : workspace["name"];
        for (const auto &monitor : monitors)
            if (monitor.toObject()["id"] == raw["monitor"]) row["monitor"] = monitor.toObject()["name"];
        QJsonArray caps;
        if (managed && raw["mapped"].toBool() && !raw["hidden"].toBool() && raw["pid"].toInt() > 0) {
            caps = {"activate", "close"};
            if (raw["floating"].toBool()) {
                caps.append("raise"); caps.append("lower");
                if (!raw["fullscreen"].toInt()) { caps.append("move"); caps.append("resize"); }
            }
        }
        row["capabilities"] = caps;
        row["roleMetadata"] = meta;
        owners["window:"+address] = row;
        rows.append(row);
    }
    const auto layerObject = layers.object();
    for (auto monitor = layerObject.begin(); monitor != layerObject.end(); ++monitor) {
        const auto levels = monitor.value().toObject()["levels"].toObject();
        for (auto level = levels.begin(); level != levels.end(); ++level) {
            for (const auto &entry : level.value().toArray()) {
                const auto raw = entry.toObject(); const auto address = raw["address"].toString();
                if (!addressValid(address)) continue;
                const auto names = QStringList{"Background", "Bottom", "Top", "Overlay"};
                const int number = level.key().toInt();
                auto row = base("hyprland:layer:"+address, "Layer · "+names.value(number,level.key()), raw);
                row["class"] = raw["namespace"]; row["appId"] = raw["namespace"];
                row["pid"] = raw["pid"]; row["pidSource"] = "Wayland client credentials";
                row["monitor"] = monitor.key(); row["role"] = "layer-shell";
                row["x"] = raw["x"]; row["y"] = raw["y"]; row["width"] = raw["w"]; row["height"] = raw["h"];
                row["opacity"] = raw["alpha"].toDouble(1)*100;
                row["above"] = number >= 2; row["managed"] = false;
                owners["layer:"+address] = row; rows.append(row);
            }
        }
    }
    const auto surfaces = query("xetal-inspector-surfaces").object();
    const bool detailed = surfaces["version"].toInt() == 1 && surfaces["surfaces"].isArray();
    if (detailed) for (const auto &entry : surfaces["surfaces"].toArray()) {
        const auto raw = entry.toObject();
        if (!addressValid(raw["address"].toString()) || !QSet<QString>{"popup","subsurface"}.contains(raw["role"].toString())) continue;
        auto row = base("hyprland:surface:"+raw["address"].toString(),
                        raw["role"] == "popup" ? "Wayland popup" : "Wayland child surface", raw);
        for (const auto *key : {"x","y","width","height","pid","mapped","role"}) row[key] = raw[key];
        row["pidSource"] = "Wayland client credentials";
        row["managed"] = false; row["visibility"] = raw["visible"].toBool() ? "Visible" : "Not visible";
        const auto owner = owners.value(raw["ownerType"].toString()+":"+raw["ownerAddress"].toString());
        if (!owner.isEmpty()) { row["parent"] = owner["id"]; row["class"] = owner["class"]; row["appId"] = owner["appId"]; }
        rows.append(row);
    }
    for (auto entry = rows.begin(); entry != rows.end(); ++entry) {
        auto row = entry->toObject(); windowEnumProcessInfo(row); *entry = row;
    }
    if (action == "list") {
        QString coverage = "Hyprland windows and desktop layers";
        if (detailed) coverage += ", including popup menus and child surfaces.";
        else coverage += ". Log out and back in after updating Hyper Fusion to include popup menus and child surfaces.";
        if (!layers.isObject()) coverage += " Desktop layers could not be read; refresh to retry.";
        coverage += " Overlays drawn inside an application's own surface belong to that window.";
        return {{"windows", rows}, {"coverage", coverage}};
    }
    QJsonObject selected;
    for (const auto &entry : rows) if (entry.toObject()["id"] == request["id"]) { selected = entry.toObject(); break; }
    if (selected.isEmpty()) return {{"error", "This window or surface has closed. Refresh and select it again."}};
    if (request.contains("pid") && request["pid"] != selected["pid"])
        return {{"error", "The selected window's owner changed. Refresh and select it again."}};
    if (action == "details") return {{"window", selected}};
    const auto caps = selected["capabilities"].toArray();
    if (action != "geometry" && !caps.contains(action)) return {{"error", "This control is not available for the selected surface."}};
    const auto address = selected["nativeProperties"].toObject()["address"].toString();
    const auto selector = "address:" + address;
    QList<QStringList> commands;
    if (action == "geometry") {
        const bool move = request["move"].toBool(true), resize = request["resize"].toBool(true);
        if ((move && !caps.contains("move")) || (resize && !caps.contains("resize")))
            return {{"error", "Geometry can only be changed for ordinary floating windows."}};
        if (resize) commands << QStringList{"dispatch", "resizewindowpixel", QString("exact %1 %2,%3").arg(request["width"].toInt()).arg(request["height"].toInt()).arg(selector)};
        if (move) commands << QStringList{"dispatch", "movewindowpixel", QString("exact %1 %2,%3").arg(request["x"].toInt()).arg(request["y"].toInt()).arg(selector)};
    } else if (action == "activate") commands << QStringList{"dispatch", "focuswindow", selector};
    else if (action == "close") commands << QStringList{"dispatch", "closewindow", selector};
    else if (action == "raise" || action == "lower") commands << QStringList{"dispatch", "alterzorder", (action == "raise" ? "top," : "bottom,") + selector};
    for (const auto &arguments : commands) {
        const auto reply = command(arguments);
        if (!reply.error.isEmpty() || reply.output.trimmed() != "ok")
            return {{"error", reply.error.isEmpty() ? "Hyprland rejected the window action: "+QString::fromUtf8(reply.output).left(500) : reply.error}};
    }
    return {{"ok", true}, {"message", "Window action sent. Refreshing the current state…"}};
}
