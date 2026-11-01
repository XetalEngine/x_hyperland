#pragma once
#include <QJsonObject>
#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QListWidget;
class QProcess;
class QProgressBar;
class QPushButton;

class GrubEditor final : public QWidget {
  Q_OBJECT
public:
  explicit GrubEditor(const QString &helper, QWidget *parent = nullptr);
  ~GrubEditor() override;
protected:
  void showEvent(QShowEvent *event) override;
private:
  QString helper, revision, operation;
  QProcess *reader, *worker;
  QByteArray output, errors;
  QJsonObject pending;
  QComboBox *drives;
  QListWidget *systems, *entries;
  QLineEdit *name;
  QPushButton *refresh, *add, *load, *rename, *remove, *undo;
  QLabel *status, *mode, *selection, *saved, *notes;
  QProgressBar *progress;
  bool busy = false, supported = false, loaded = false, canUndo = false;
  void refreshDrives();
  void request(const QJsonObject &data);
  void readWorker();
  void result(const QJsonObject &data);
  void setBusy(bool value);
  void updateActions();
  void chooseDrive();
  void chooseSystem();
  QJsonObject system() const;
  QJsonObject entry() const;
};
