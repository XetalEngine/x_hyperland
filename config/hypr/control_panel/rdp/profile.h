#pragma once
#include <QDir>
#include <QJsonObject>
#include <QList>
#include <QString>

namespace FusionRdp {
struct Profile {
    QString id, name, host, username, domain;
    int port = 3389;
    QString sharedFolder = QDir::homePath();
    QString gateway;
    bool rememberPassword = true, shareFolder = true, clipboard = true;
    bool sound = true, microphone = true, printers = true;
    bool dynamicResolution = true, autoAcceptCertificate = true, reconnect = true;
    bool fullscreen = false, adminSession = false;
    quint32 keyboardLayout = 0x0409;
    QJsonObject json() const;
    static Profile fromJson(const QJsonObject &object);
    QString validate() const;
    QString credentialKey() const;
};

class ProfileStore {
public:
    explicit ProfileStore(QString filename);
    QList<Profile> load(QString *error = nullptr) const;
    bool save(const Profile &profile, QString *error);
    bool remove(const QString &id, QString *error);
private:
    QString path;
    bool write(const QList<Profile> &profiles, QString *error);
};
}
