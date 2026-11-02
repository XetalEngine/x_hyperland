#pragma once
#include <QList>
#include <QUrl>
#include <atomic>
#include <memory>

namespace Fusion {
enum class TransferOperation { Copy, Move, Link };
struct TransferAccess {
  QList<QUrl> sources;
  QUrl destination;
  bool administrator = false;
};
// Read-only preflight, run off the GUI thread. KIO/admin owns all mutations
// and asks PolicyKit for authorization before accessing protected locations.
TransferAccess transferAccess(const QList<QUrl> &sources, const QUrl &destination,
                              TransferOperation operation,
                              const std::shared_ptr<std::atomic_bool> &cancelled);
QUrl ordinaryFileUrl(const QUrl &url);
}
