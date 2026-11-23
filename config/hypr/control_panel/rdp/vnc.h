#pragma once
#include "profile.h"
#include <QProcessEnvironment>
#include <QStringList>
class QWidget;

namespace FusionRdp {
QString vncExecutable(const QString &root);
QStringList vncArguments(const Profile &profile);
QProcessEnvironment vncEnvironment(const Profile &profile, const QString &password);
void openVncSession(const QString &root, const Profile &profile, const QString &password, QWidget *parent);
}
