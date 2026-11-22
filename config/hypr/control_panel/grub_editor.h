#pragma once
#include <QJsonObject>
#include <QJsonArray>
#include <QWidget>

class QTreeWidget;
class QBoxLayout;
class QLabel;
class QLineEdit;
class QListWidget;
class QProcess;
class QProgressBar;
class QPushButton;
class QTabWidget;
class GrubAppearance;
class QComboBox;
class QCheckBox;
class QSpinBox;

class GrubEditor final : public QWidget {
  Q_OBJECT
public:
  explicit GrubEditor(const QString &helper, QWidget *parent = nullptr);
  ~GrubEditor() override;
  int heightForWidth(int width) const override;
protected:
  void showEvent(QShowEvent *event) override;
  void resizeEvent(QResizeEvent *event) override;
private:
  QString helper, revision, menuRevision, operation, optionsRevision;
  QProcess *reader, *worker;
  QByteArray output, errors;
  QJsonObject pending;
  QJsonArray managedEntries;
  QBoxLayout *choicesLayout;
  QTabWidget *tabs;
  GrubAppearance *appearance;
  QTreeWidget *drives, *entries;
  QListWidget *systems;
  QLineEdit *name;
  QPushButton *refresh, *detect, *properties, *add, *load, *rename, *remove, *undo;
  QLabel *status, *mode, *selection, *saved, *notes, *driveCount, *entryDetails;
  QProgressBar *progress;
  QComboBox *defaultEntry, *timeoutStyle, *efiPartition;
  QCheckBox *rememberEntry, *firmwareFirst;
  QSpinBox *bootTimeout;
  QLineEdit *firmwareLabel;
  QTreeWidget *firmwareEntries;
  QLabel *rememberReason, *firmwareStatus;
  QPushButton *moveUp, *moveDown, *optionsLoad, *optionsSave, *optionsUndo, *firmwareLoad, *firmwareRegister;
  bool rememberSupported = false, optionsCanUndo = false, firmwareAvailable = false, firmwareLoaded = false;
  bool busy = false, supported = false, loaded = false, canUndo = false;
  void refreshDrives();
  void request(const QJsonObject &data);
  void readWorker();
  void result(const QJsonObject &data);
  void setBusy(bool value);
  void updateActions();
  void chooseDrive();
  void scanDrive();
  void showDriveProperties(const QJsonObject &drive);
  void chooseSystem();
  void editEntry();
  void chooseEntry();
  void moveEntry(int direction);
  void loadTab();
  void reviewFirmware(const QJsonObject &review);
  QJsonObject drive() const;
  QJsonObject system() const;
  QJsonObject entry() const;
};
