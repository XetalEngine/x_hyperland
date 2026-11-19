#pragma once
#include "core.h"
#include "drives.h"
class WindowsComputerView;

class VolumeCard : public QFrame {
  Q_OBJECT
public:
  explicit VolumeCard(QWidget *parent = nullptr);
  Volume volume() const { return current; }
  void setVolume(const Volume &volume);
  void setSelected(bool selected);
  void setListMode(bool list);
  void setPartitionMode(bool partition);
  void setOriginalMode(bool original);
signals:
  void selected();
  void openRequested();
  void mountRequested();
  void stepRequested(int step);
protected:
  void mousePressEvent(QMouseEvent *) override;
  void mouseDoubleClickEvent(QMouseEvent *) override;
  void keyPressEvent(QKeyEvent *) override;
  void focusInEvent(QFocusEvent *) override;
  void focusOutEvent(QFocusEvent *) override;
  void enterEvent(QEnterEvent *) override;
  void leaveEvent(QEvent *) override;
  void resizeEvent(QResizeEvent *) override;
  void changeEvent(QEvent *) override;
  bool eventFilter(QObject *, QEvent *) override;
private:
  Volume current;
  QLabel *art = nullptr, *name, *description, *space, *status;
  QProgressBar *usage;
  QPushButton *mount;
  QWidget *metrics, *identityBody, *actionsBody;
  QStackedLayout *actionStack;
  QHBoxLayout *row;
  QVBoxLayout *identity;
  bool listMode = false, compact = false, partitionMode = false, originalMode = false;
  void updateMount();
  void updateLayout();
  void updateIcon();
};

class DriveShelf : public QWidget {
  Q_OBJECT
public:
  DriveShelf(Fusion::Preferences *preferences, Drives *drives, QWidget *parent = nullptr);
  void refresh();
  Volume selectedVolume() const;
  void selectDevice(const QString &device, bool focus = false);
  QVariantMap place() const;
  void restorePlace(const QVariantMap &state);
signals:
  void selectionChanged();
  void locationRequested(const QUrl &url);
  void controlPanelRequested();
  void operationRequested(const Volume &volume, const QString &operation);
  void volumeContextRequested(const Volume &volume, const QPoint &position);
  void backgroundContextRequested(const QPoint &position);
protected:
  bool eventFilter(QObject *, QEvent *) override;
  void changeEvent(QEvent *) override;
  void resizeEvent(QResizeEvent *) override;
private:
  Fusion::Preferences *preferences;
  Drives *drives;
  QScrollArea *scroll;
  QWidget *body = nullptr;
  QGridLayout *grid;
  QLabel *empty = nullptr, *hint = nullptr;
  QToolButton *originalButton = nullptr, *shelfButton = nullptr, *listButton = nullptr;
  QButtonGroup *viewChoices = nullptr;
  QCheckBox *showUnmounted = nullptr;
  QStackedWidget *viewStack = nullptr;
  WindowsComputerView *windowsView = nullptr;
  QGridLayout *headerLayout = nullptr;
  QWidget *headingBody = nullptr, *viewButtons = nullptr;
  int headerMode = -1;
  struct Tile {
    QFrame *frame;
    QVBoxLayout *layout;
    QLabel *heading;
  };
  struct Group {
    QFrame *frame;
    QWidget *heading;
    QLabel *art, *name, *description;
    QCheckBox *automatic;
    QVBoxLayout *layout, *dataLayout;
    QBoxLayout *systemLayout;
    QWidget *systemBody;
    QToolButton *disclosure;
    QMap<QString, Tile> tiles;
    QStringList volumes;
  };
  struct Section {
    QWidget *body;
    QLabel *heading;
    QGridLayout *items;
  };
  QMap<QString, Group> groups;
  QMap<QString, VolumeCard *> cards;
  QStringList order;
  QMap<QString, int> categories;
  QMap<int, Section> sections;
  QString selected;
  int columns = 0, removableColumns = 0;
  bool sideBySide = false;
  bool layoutQueued = false, topologyChanged = false;
  QString expansionKey(const QString &drive) const;
  void queueLayout();
  void relayout();
  void step(VolumeCard *from, int delta);
  QString viewMode() const;
  bool windowsMode() const;
  void layoutHeader();
};
