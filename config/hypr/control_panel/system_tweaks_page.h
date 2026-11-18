#pragma once
#include <QJsonObject>
#include <QWidget>
#include <QMap>

class QComboBox;
class QGridLayout;
class QLabel;
class QLineEdit;
class QProcess;
class QPushButton;
class QSpinBox;
class QTabWidget;
class QTimer;

class SystemTweaksPage final : public QWidget {
  Q_OBJECT
public:
  explicit SystemTweaksPage(const QString &root, QWidget *parent = nullptr);
  ~SystemTweaksPage() override;
  void selectCategory(const QString &name);
  void display(const QJsonObject &snapshot);
signals:
  void openTool(const QString &id);
  void operationRequested(const QString &action, const QString &id, const QString &value, const QString &revision);
protected:
  void showEvent(QShowEvent *event) override;
  void resizeEvent(QResizeEvent *event) override;
private:
  struct Card {
    QWidget *box;
    QLabel *current, *saved, *note, *details;
    QComboBox *combo = nullptr;
    QSpinBox *number = nullptr;
    QPushButton *apply, *restore;
    QJsonObject spec;
    bool dirty = false;
  };
  QString root, revision, action, activeId;
  QTabWidget *tabs;
  QLineEdit *search;
  QLabel *message, *summary;
  QPushButton *refresh;
  QProcess *process = nullptr;
  QTimer *deadline;
  QMap<QString, Card> cards;
  QMap<QString, QGridLayout *> grids;
  QMap<QString, QWidget *> categoryPages;
  QMap<QString, QList<QWidget *>> categoryCards;
  void request(const QString &command, const QString &id = {}, const QString &value = {});
  void finished(int code);
  void arrange();
  void busy(bool active);
  QString value(const Card &card) const;
  void updateButtons();
  void addCard(const QJsonObject &spec);
  void addLink(const QString &category, const QString &title, const QString &description, const QString &tool);
};
