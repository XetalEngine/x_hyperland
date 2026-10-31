#pragma once
#include <QJsonObject>
#include <QWidget>

class QLabel;
class QProcess;
class QProgressBar;
class QPushButton;
class QRadioButton;
class QTimer;
class QGroupBox;

class RamCleaner final : public QWidget {
  Q_OBJECT
public:
  explicit RamCleaner(const QString &helper, QWidget *parent = nullptr);
  ~RamCleaner() override;
protected:
  void showEvent(QShowEvent *event) override;
  void hideEvent(QHideEvent *event) override;
private:
  QString helper;
  QProcess *statsProcess, *cleanProcess;
  QTimer *refreshTimer, *statsTimeout;
  QRadioButton *normal, *aggressive;
  QPushButton *clean;
  QProgressBar *memoryBar, *progress;
  QLabel *available, *fileCache, *metadataCache, *swap, *capacity, *status, *result;
  QGroupBox *resultBox;
  QByteArray cleanOutput;
  QJsonObject completion;
  bool busy = false;
  void refresh();
  void display(const QJsonObject &snapshot);
  void startCleanup();
  void readCleanup();
  void finishCleanup(int code);
};
