#pragma once
#include <KFileItem>
class QApplication;
class KPropertiesDialog;
class QWidget;

namespace Fusion {
KPropertiesDialog *propertiesDialog(const KFileItemList &items, QWidget *parent = nullptr);
bool openProperties(const QStringList &uris);
int runProperties(QApplication &app, const QStringList &uris);
}
