#pragma once
#include "drives.h"

namespace PrefixDrives {
struct Locations {
  QString home, config, data, portable, wine;
  static Locations environment();
};
// Read only the prefix registry and shallow prefix/library directories.
// Called on a worker so a disconnected external Steam library cannot freeze Files.
QList<Volume> discover(const Locations &locations);
}
