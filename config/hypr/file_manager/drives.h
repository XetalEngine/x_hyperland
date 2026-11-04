#pragma once
#include <QtWidgets>
#include "automount.h"

struct Volume {
  QString device, name, filesystem, mount, type, uuid;
  quint64 size = 0, available = 0, total = 0;
  bool removable = false, readOnly = false;
  QString driveDevice, driveModel, transport;
  quint64 driveSize = 0, freeBytes = 0;
  bool spaceKnown = false;
  bool system = false, verifiedMount = false;
  QString connection;
  QString driveKey() const {
    return driveDevice.isEmpty() ? device : driveDevice;
  }
  bool mounted() const { return !mount.isEmpty(); }
  bool usb() const {
    return removable || transport.compare("usb", Qt::CaseInsensitive) == 0;
  }
  bool locked() const {
    return filesystem == "crypto_LUKS" ||
           filesystem.compare("BitLocker", Qt::CaseInsensitive) == 0;
  }
  bool mountable() const {
    return !filesystem.isEmpty() && filesystem != "swap" && !locked() &&
           filesystem != "LVM2_member";
  }
};
Q_DECLARE_METATYPE(Volume)

class Drives : public QObject {
  Q_OBJECT
public:
  explicit Drives(QObject *parent = nullptr, bool automatic = true, bool autoMount = false,
                  const QString &autoMountSettings = {}, const QString &autoMountSession = {});
  ~Drives() override;
  QList<Volume> volumes;
  static QList<Volume> parse(const QByteArray &data);
  void refresh();
  void operate(const Volume &volume, const QString &operation, QWidget *parent);
  void menu(const Volume &volume, const QPoint &position, QWidget *parent);
  void showProperties(const Volume &volume, QWidget *parent);
  QUrl mountedLocation(const Volume &volume);
  bool busy() const { return operation.state() != QProcess::NotRunning; }
  void updateAutoMounts();
  AutoMountPolicy::Choice autoMountChoice(const QString &drive) const;
  void setAutoMount(const QString &drive, bool enabled);
signals:
  void changed();
  void message(const QString &text);
  void populateFileMenu(QMenu *menu, const Volume &volume);
  void browse(const QUrl &url);

private:
  QProcess scan, operation;
  QTimer timer, operationTimeout;
  AutoMountPolicy autoMountPolicy;
  QString openAfterMount;
  bool refreshAgain = false;
  bool scanningEnabled = true;
  bool automaticMounting = false;
  void mountAutomatically();
};

class DriveDelegate : public QStyledItemDelegate {
public:
  explicit DriveDelegate(QWidget *parent);
  QSize sizeHint(const QStyleOptionViewItem &,
                 const QModelIndex &) const override {
    return {320, 112};
  }
  void paint(QPainter *, const QStyleOptionViewItem &,
             const QModelIndex &) const override;
private:
  QGroupBox *cardStyle;
};
