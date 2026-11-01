#pragma once
#include <QJsonArray>
#include <QJsonObject>
#include <QMap>
#include <QWidget>

class QGridLayout;
class QLabel;
class QLineEdit;
class QProcess;
class QProgressBar;
class QPushButton;
class QStackedWidget;
class QTimer;
class QToolButton;
class QTreeWidget;

class DefaultApps final : public QWidget {
  Q_OBJECT
public:
  explicit DefaultApps(const QString &helper, QWidget *parent = nullptr);
  ~DefaultApps() override;
  void focusSearch();

protected:
  void showEvent(QShowEvent *event) override;
  void resizeEvent(QResizeEvent *event) override;

private:
  QString helper, action, revision, undoToken, pendingMessage;
  QProcess *process;
  QTimer *timeout;
  QWidget *cards;
  QGridLayout *grid;
  QStackedWidget *pages;
  QToolButton *everyday, *byType;
  QPushButton *refresh, *undo, *changeType;
  QLineEdit *search;
  QTreeWidget *types;
  QLabel *status, *typeCount;
  QProgressBar *progress;
  QJsonArray applications;
  QMap<QString, QJsonObject> appIndex, roleIndex;
  QList<QPushButton *> roleCards;
  bool busy = false;
  int columns = 0;
  void request(const QString &operation, const QJsonObject &data = {});
  void setBusy(bool value);
  void display(const QJsonObject &data);
  void arrange();
  void filterTypes();
  void choose(const QString &title, const QStringList &mimeTypes,
              const QString &current, const QJsonObject &target);
};
