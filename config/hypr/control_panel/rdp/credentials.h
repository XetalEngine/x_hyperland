#pragma once
#include "profile.h"
#include <QObject>
#include <QProcess>
#include <QTimer>

namespace FusionRdp {
class CredentialJob : public QObject {
    Q_OBJECT
public:
    enum Operation { Lookup, Store, Forget };
    explicit CredentialJob(QObject *parent = nullptr, QString program = {});
    ~CredentialJob() override;
    void start(Operation operation, const Profile &profile, const QString &password = {});
signals:
    void completed(bool success, const QString &password, const QString &error);
private:
    QProcess process;
    QTimer deadline;
    QString program;
    Operation operation = Lookup;
    bool done = false;
    void finish(bool success, const QString &password, const QString &error);
};
}
