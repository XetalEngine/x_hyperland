#pragma once
#include <KJob>
#include <QPointer>
#include <QMap>
#include <QVariantMap>
#include <functional>

namespace Fusion {
// One JobView for the entire operation, including its questions. Native local
// transfers and remote KIO operations share this presentation and controls.
class TransferView : public QObject {
  Q_OBJECT
public:
  using Answer = std::function<void(const QVariantMap &)>;
  TransferView(KJob *job, const QVariantMap &initial);
  void ask(const QVariantMap &question, Answer answer, std::function<void()> fallback);
  void update(const QVariantMap &data);
  void enableQueue();
  void updateQueue(const QVariantMap &row = {}, const QVariantMap &state = {});
signals:
  void reviewRequested();
  void queueReady(bool available);
  void queueDecision(const QVariantMap &decision);

private slots:
  void cancel();
  void suspend();
  void resume();
  void review();
  void decideQueue(const QVariantMap &decision);

private:
  QPointer<KJob> job;
  QString path, owner;
  QVariantMap values, question;
  Answer answer;
  std::function<void()> fallback;
  bool ready = false, finished = false, unavailable = false;
  int error = 0;
  QString errorText;
  bool queueEnabled = false, queueChecked = false, queueAvailable = false, queueProbing = false;
  QMap<qlonglong, QVariantMap> queueRows;
  QVariantMap queueState;
  void flush();
  void probeQueue();
  void flushQueue();
  void sendQuestion();
  void finish(int code, const QString &text);
  void terminate();
};
}
