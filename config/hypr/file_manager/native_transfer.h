#pragma once
#include <KJob>
#include <QJsonObject>
#include <QPointer>
#include <QProcess>
#include <QUrl>

namespace Fusion {
class NativeTransfer : public KJob {
  Q_OBJECT
public:
  explicit NativeTransfer(QJsonObject request);
  ~NativeTransfer() override;
  void start() override;
  void answer(const QString &choice);
  void resolve(const QVariantMap &decision);
  QString journal() const { return journalPath; }
signals:
  void progress(const QVariantMap &values);
  void issue(const QVariantMap &values);
  void question(const QUrl &source, const QUrl &destination, bool replaceAllowed);
  void moved(const QUrl &source, const QUrl &destination);
  void destinationReady(const QUrl &destination);
protected:
  bool doKill() override;
  bool doSuspend() override;
  bool doResume() override;
private:
  QJsonObject request;
  QProcess process, authority;
  QByteArray buffer;
  QJsonObject outcome;
  QString journalPath, authorizationToken;
  bool started = false, finished = false, paused = false;
  void command(const QJsonObject &message);
  void receive();
  void authenticate(QJsonObject scope);
  void complete(int code, const QString &message);
};

// Custom commands share KIO's serial sequence, so Ctrl+Z still undoes the
// newest operation when copies, renames and Trash operations are interleaved.
class TransferHistory : public QObject {
  Q_OBJECT
public:
  static TransferHistory *self();
  void record(const QString &journal, bool moving);
  bool available() const;
  QString text() const;
  QString pending() const;
  void consumed(const QString &journal);
signals:
  void changed();
private:
  TransferHistory();
  struct Entry { quint64 serial; QString journal; bool moving; };
  QList<Entry> entries;
};
}
