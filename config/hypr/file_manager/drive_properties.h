#pragma once
#include "drives.h"

class StorageChart;

class DriveProperties : public QDialog {
  Q_OBJECT
public:
  DriveProperties(const Volume &volume, Drives *drives,
                  QWidget *parent = nullptr);

private:
  Volume volume;
  bool connected = true;
  StorageChart *chart;
  QLabel *heading, *status, *usageHint;
  QLabel *used, *usedBytes, *free, *freeBytes, *reserved, *reservedBytes;
  QLabel *capacity, *capacityBytes;
  QLabel *device, *physical, *filesystem, *mount, *access, *uuid;
  QWidget *reservedRow;
  QPushButton *open;
  void refresh();
  QString summary() const;
};
