#pragma once
#include <QDir>
#include <QJsonArray>
#include <QJsonObject>
#include <QLayout>
#include <QObject>
#include <QString>
#include <QTabBar>
#include <QTabWidget>
#include <QVector>
// Inactive tools must not impose their minimum size on the selected tool.
class PanelTabs : public QTabWidget {
public:
  explicit PanelTabs(QWidget *parent = nullptr) : QTabWidget(parent) {
    connect(this, &QTabWidget::currentChanged, this,
            [this] { updateGeometry(); });
  }
  QSize sizeHint() const override {
    return currentWidget()
               ? currentWidget()->sizeHint() +
                     QSize(4, tabBar()->isHidden()
                                  ? 4
                                  : tabBar()->sizeHint().height() + 4)
               : QSize(0, 0);
  }
  QSize minimumSizeHint() const override {
    return currentWidget()
               ? currentWidget()->minimumSizeHint() +
                     QSize(4, tabBar()->isHidden()
                                  ? 4
                                  : tabBar()->minimumSizeHint().height() + 4)
               : QSize(0, 0);
  }
  bool hasHeightForWidth() const override {
    return currentWidget() && currentWidget()->hasHeightForWidth();
  }
  int heightForWidth(int width) const override {
    if (!currentWidget()) return -1;
    // A scroll area's minimum height must not include a text editor's preferred
    // 200px height. Let expanding outputs shrink while wrapped labels fit.
    const auto *layout = currentWidget()->layout();
    const int height = layout ? layout->minimumHeightForWidth(width - 4)
                              : currentWidget()->heightForWidth(width - 4);
    return height < 0 ? -1 : height + (tabBar()->isHidden() ? 4 : tabBar()->sizeHint().height() + 4);
  }
};
class MainWindow;
class QStackedWidget;
class QLabel;
class QLineEdit;
class QGridLayout;
class QPushButton;
class QProcess;
class QWidget;
class QEvent;
class QScrollArea;
class QCheckBox;
namespace HyperPanel {
inline QString root() {
  const auto value = qEnvironmentVariable("XETAL_HYPR_ROOT");
  return value.isEmpty() ? QDir::homePath() + "/.config/hypr" : value;
}
QString terminal();
QString accent();
QJsonObject request(const QString &action,
                    const QJsonObject &input = QJsonObject());
void shortcut(const QJsonObject &input);
} // namespace HyperPanel
class PanelController : public QObject {
  Q_OBJECT
public:
  explicit PanelController(MainWindow *window);
  void open(const QString &id);
  QJsonObject inventory() const;
  QJsonArray verifyNavigation();

protected:
  bool eventFilter(QObject *object, QEvent *event) override;

private:
  MainWindow *owner;
  QStackedWidget *stack;
  QWidget *home;
  QWidget *isoActions;
  QScrollArea *body;
  QCheckBox *startupScreen;
  QLabel *startupStatus;
  QCheckBox *numLockStartup;
  QLabel *numLockStatus;
  QLabel *crumb, *count;
  QLineEdit *search;
  QPushButton *back;
  QProcess *themeProcess;
  struct Tool {
    QJsonObject data;
    QPushButton *button;
  };
  struct Group {
    QWidget *box;
    QGridLayout *grid;
    QVector<Tool> tools;
  };
  QVector<Group> groups;
  QString current;
  void arrange();
  void theme();
  void prepareTools();
  void loadStartupPreference();
};
