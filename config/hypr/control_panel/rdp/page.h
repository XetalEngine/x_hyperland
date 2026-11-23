#pragma once
#include "profile.h"
#include <QCheckBox>
#include <QComboBox>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QSpinBox>
#include <QTabWidget>
#include <QWidget>
#include <functional>
class QFormLayout;
class QGroupBox;
class QToolButton;

namespace FusionRdp {
class Page : public QWidget {
    Q_OBJECT
public:
    using SessionOpener = std::function<void(const Profile &, const QString &)>;
    explicit Page(const QString &root, QWidget *parent = nullptr, SessionOpener opener = {});
    Profile draft() const;
    void showHosting();
private:
    QTabWidget *modes;
    ProfileStore store;
    QList<Profile> profiles;
    SessionOpener opener;
    QListWidget *connections;
    QLineEdit *filter, *name, *host, *username, *domain, *password, *sharedFolder, *gateway;
    QSpinBox *port;
    QComboBox *keyboard, *protocol, *vncSecurity;
    QCheckBox *vncViewOnly, *vncShared;
    QFormLayout *connectionForm;
    QGroupBox *sharingGroup, *vncOptions;
    QWidget *advanced;
    QToolButton *advancedToggle;
    QLabel *sessionHint;
    QCheckBox *remember, *shareFolder, *clipboard, *sound, *microphone, *printers;
    QCheckBox *dynamicResolution, *autoAcceptCertificate, *reconnect, *fullscreen, *adminSession;
    QPushButton *save, *connectButton, *remove, *create;
    QLabel *status;
    QWidget *editorWidget;
    QString currentId, passwordIdentity;
    quint64 lookupGeneration = 0;
    bool loading = false, busy = false, dirty = false, lookupPending = false;
    void refresh(const QString &select = {});
    void load(const Profile &profile);
    void newConnection();
    void persist(bool connect);
    void removeConnection();
    void setBusy(bool value);
    void updateActions();
    void clearStalePassword();
    void protocolChanged(bool resetPort = true);
    void say(const QString &message, bool error = false);
};
}
