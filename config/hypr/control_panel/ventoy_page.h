#pragma once
#include <QJsonObject>
#include <QWidget>

class QCheckBox;
class QComboBox;
class QLabel;
class QPlainTextEdit;
class QProcess;
class QProgressBar;
class QPushButton;
class QTimer;

class VentoyPage : public QWidget {
  Q_OBJECT
public:
  explicit VentoyPage(const QString &profileRoot, QWidget *parent = nullptr);
  ~VentoyPage() override;
protected:
  void showEvent(QShowEvent *event) override;
  void hideEvent(QHideEvent *event) override;
  bool eventFilter(QObject *object, QEvent *event) override;
private:
  QString root, helper, operation;
  bool busy = false, scanning = false, bundleReady = false, confirming = false;
  QByteArray pending, errors;
  QJsonObject completion;
  QComboBox *disks, *style;
  QCheckBox *secure;
  QLabel *bundle, *details, *status;
  QPushButton *refreshButton, *createButton, *updateButton, *openButton, *saveButton;
  QProgressBar *progress;
  QPlainTextEdit *log;
  QProcess *scanProcess, *worker;
  QTimer *refreshTimer, *scanTimeout;
  QJsonObject selected() const;
  void refresh();
  void display(const QJsonObject &data);
  void selectionChanged();
  void updateControls();
  void confirm(const QString &action);
  void start(const QString &action, const QJsonObject &request);
  void readOutput();
  void finish(int code);
};
