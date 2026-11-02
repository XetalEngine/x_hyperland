#pragma once
#include "window.h"

// Shared by the desktop portal and the profile-local Qt platform theme. No
// content is written here: the requesting application owns open/save itself.
class PickerWindow : public FilesWindow {
  Q_OBJECT
public:
  explicit PickerWindow(const QJsonObject &request, const QString &settingsPath = {},
                        bool scanDrives = true);
  void acceptSelection();
signals:
  void finished(const QJsonObject &result);
protected:
  void openItem(const KFileItem &item, bool newTab = false) override;
  void closeEvent(QCloseEvent *event) override;
private:
  QJsonObject request;
  QLineEdit *name;
  QComboBox *types;
  QJsonArray filters;
  QList<QPair<QString, QWidget *>> choices;
  QString key;
  bool saving, directory, multiple, completed = false;
  void fail(const QString &message);
  void finish(const QList<QUrl> &urls);
  QString withExtension(const QString &path) const;
};

int runPicker(QApplication &app);
