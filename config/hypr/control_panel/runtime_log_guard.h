#pragma once
#include <QGroupBox>

class QCheckBox;
class QLabel;
class QProcess;
class QPushButton;
class QTimer;

class RuntimeLogGuard final : public QGroupBox {
  Q_OBJECT
public:
  explicit RuntimeLogGuard(const QString &helper, QWidget *parent = nullptr);
  ~RuntimeLogGuard() override;
protected:
  void showEvent(QShowEvent *event) override;
  void hideEvent(QHideEvent *event) override;
private:
  QString helper, action;
  QCheckBox *enabled, *disableFiles;
  QLabel *summary, *message, *loggingStatus;
  QPushButton *check;
  QProcess *process;
  QTimer *refresh, *timeout;
  bool previousEnabled = true;
  bool previousDisableFiles = false;
  void request(const QString &command);
  void finish(int code);
};
