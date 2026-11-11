#include "profile.h"
#include <QCryptographicHash>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLockFile>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSet>
#include <QUuid>

namespace FusionRdp {
QJsonObject Profile::json() const {
    return {{"id", id}, {"name", name}, {"host", host}, {"port", port},
        {"username", username}, {"domain", domain}, {"sharedFolder", sharedFolder},
        {"gateway", gateway}, {"rememberPassword", rememberPassword},
        {"shareFolder", shareFolder}, {"clipboard", clipboard}, {"sound", sound},
        {"microphone", microphone}, {"printers", printers},
        {"dynamicResolution", dynamicResolution}, {"autoAcceptCertificate", autoAcceptCertificate},
        {"reconnect", reconnect}, {"fullscreen", fullscreen}, {"adminSession", adminSession},
        {"keyboardLayout", double(keyboardLayout)}};
}
Profile Profile::fromJson(const QJsonObject &o) {
    Profile p;
    p.id = o["id"].toString(); p.name = o["name"].toString(); p.host = o["host"].toString();
    p.port = o["port"].toInt(3389); p.username = o["username"].toString(); p.domain = o["domain"].toString();
    p.sharedFolder = o["sharedFolder"].toString(QDir::homePath()); p.gateway = o["gateway"].toString();
    p.rememberPassword = o["rememberPassword"].toBool(true);
    p.shareFolder = o["shareFolder"].toBool(true); p.clipboard = o["clipboard"].toBool(true);
    p.sound = o["sound"].toBool(true); p.microphone = o["microphone"].toBool(true);
    p.printers = o["printers"].toBool(true); p.dynamicResolution = o["dynamicResolution"].toBool(true);
    p.autoAcceptCertificate = o["autoAcceptCertificate"].toBool(true); p.reconnect = o["reconnect"].toBool(true);
    p.fullscreen = o["fullscreen"].toBool(); p.adminSession = o["adminSession"].toBool();
    p.keyboardLayout = quint32(o["keyboardLayout"].toDouble(0x0409));
    return p;
}
QString Profile::validate() const {
    if (QUuid(id).isNull()) return "Create a new connection before saving.";
    if (name.trimmed().isEmpty()) return "Give this connection a name.";
    if (host.trimmed().isEmpty()) return "Enter the PC's hostname or IP address.";
    const QRegularExpression invalid("[\\s/\\\\@?#]");
    if (host.contains(invalid) || host.contains(QChar::Null))
        return "Use a hostname or IP address, without a URL or username. Set the port separately.";
    if (port < 1 || port > 65535) return "The port must be between 1 and 65535.";
    if (username.contains(QChar::Null) || domain.contains(QChar::Null) || gateway.contains(QChar::Null))
        return "The connection details contain an invalid character.";
    if (!gateway.isEmpty() && (gateway.contains(invalid) || gateway.startsWith('-')))
        return "Use a gateway hostname, optionally followed by :port.";
    if (shareFolder && (!QDir::isAbsolutePath(sharedFolder) || !QFileInfo(sharedFolder).isDir()))
        return "Choose an existing folder to share, or turn off folder sharing.";
    return {};
}
QString Profile::credentialKey() const {
    // Editing a saved PC or account must never send its old password to a new host.
    const QJsonArray identity{id, host.toLower(), port, username, domain, gateway.toLower()};
    return QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(identity).toJson(QJsonDocument::Compact),
                                                      QCryptographicHash::Sha256).toHex());
}
ProfileStore::ProfileStore(QString filename) : path(std::move(filename)) {}
QList<Profile> ProfileStore::load(QString *error) const {
    if (error) error->clear();
    QFile file(path);
    if (!file.exists()) return {};
    if (!file.open(QIODevice::ReadOnly)) { if (error) *error = file.errorString(); return {}; }
    QJsonParseError parse;
    const auto document = QJsonDocument::fromJson(file.readAll(), &parse);
    if (parse.error != QJsonParseError::NoError || !document.isObject() ||
        document.object()["version"].toInt() != 1 || !document.object()["connections"].isArray()) {
        if (error) *error = "The saved RDP connections file is invalid. It has been left untouched.";
        return {};
    }
    QList<Profile> result;
    QSet<QString> seen;
    for (const auto &entry : document.object()["connections"].toArray()) {
        auto p = Profile::fromJson(entry.toObject());
        if (!entry.isObject() || QUuid(p.id).isNull() || seen.contains(p.id)) {
            if (error) *error = "The saved RDP connections contain an invalid or duplicate entry.";
            return {};
        }
        seen.insert(p.id); result.append(p);
    }
    return result;
}
bool ProfileStore::write(const QList<Profile> &profiles, QString *error) {
    QJsonArray entries;
    for (const auto &p : profiles) entries.append(p.json());
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) { *error = file.errorString(); return false; }
    if (!file.setPermissions(QFile::ReadOwner | QFile::WriteOwner)) {
        *error = "Could not protect the connection file's permissions."; return false;
    }
    const auto data = QJsonDocument(QJsonObject{{"version", 1}, {"connections", entries}}).toJson();
    if (file.write(data) != data.size() || !file.commit()) { *error = file.errorString(); return false; }
    error->clear(); return true;
}
bool ProfileStore::save(const Profile &profile, QString *error) {
    *error = profile.validate(); if (!error->isEmpty()) return false;
    const auto directory = QFileInfo(path).absolutePath();
    if (!QDir().mkpath(directory)) { *error = "Could not create the RDP connections folder."; return false; }
    QFile::setPermissions(directory, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    QLockFile lock(path + ".lock");
    if (!lock.tryLock(0)) { *error = "Another window is saving connections. Please try again."; return false; }
    auto profiles = load(error); if (!error->isEmpty()) return false;
    bool replaced = false;
    for (auto &p : profiles) if (p.id == profile.id) { p = profile; replaced = true; break; }
    if (!replaced) profiles.append(profile);
    return write(profiles, error);
}
bool ProfileStore::remove(const QString &id, QString *error) {
    QLockFile lock(path + ".lock");
    if (!lock.tryLock(0)) { *error = "Another window is saving connections. Please try again."; return false; }
    auto profiles = load(error); if (!error->isEmpty()) return false;
    for (auto it = profiles.begin(); it != profiles.end();) {
        if (it->id == id) it = profiles.erase(it); else ++it;
    }
    return write(profiles, error);
}
}
