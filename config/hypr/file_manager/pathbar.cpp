#include "pathbar.h"
#include "core.h"
#include <KUrlCompletion>

PathBar::PathBar(QWidget *parent)
    : QWidget(parent), history{Fusion::computerUrl()} {
  auto *layout = new QHBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  setMinimumWidth(160);
  input = new KUrlComboBox(KUrlComboBox::Directories, true);
  input->setObjectName("pathEditor");
  input->setInsertPolicy(QComboBox::NoInsert);
  input->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  completion = new KUrlCompletion(KUrlCompletion::DirCompletion);
  completion->setParent(input);
  input->setCompletionObject(completion);
  input->setAutoDeleteCompletionObject(false);
  input->lineEdit()->installEventFilter(this);
  layout->addWidget(input);
  connect(input->lineEdit(), &QLineEdit::returnPressed, this, &PathBar::submit);
  connect(input, qOverload<int>(&QComboBox::activated), this, [this](int) {
    submit();
  });
  render();
}
QUrl PathBar::locationUrl() const {
  return history.value(position, Fusion::computerUrl());
}
QUrl PathBar::displayedUrl() const {
  return selectedFile.isEmpty() ? locationUrl() : selectedFile;
}
void PathBar::setSelectedFileUrl(const QUrl &url) {
  if (selectedFile == url) return;
  selectedFile = url;
  render();
}
void PathBar::submit() {
  const auto url = Fusion::userUrl(input->currentText(), locationUrl());
  if (!selectedFile.isEmpty() && url == selectedFile)
    emit fileActivated(url);
  else
    setLocationUrl(url);
}
void PathBar::setLocationUrl(const QUrl &url) {
  if (!url.isValid() || url.isEmpty())
    return;
  selectedFile.clear();
  QUrl normalized = url.adjusted(QUrl::NormalizePathSegments);
  if (normalized.path().size() > 1 && normalized.path().endsWith('/'))
    normalized.setPath(normalized.path().chopped(1));
  if (normalized != locationUrl()) {
    emit aboutToNavigate();
    const auto previous = states.value(history.indexOf(normalized));
    while (position > 0) {
      history.removeFirst();
      states.removeFirst();
      --position;
    }
    history.prepend(normalized);
    states.prepend(previous);
    while (history.size() > 100) {
      history.removeLast();
      states.removeLast();
    }
    render();
    emit urlChanged(normalized);
    emit historyChanged();
  } else
    render();
}
bool PathBar::goBack() {
  if (position + 1 >= history.size())
    return false;
  emit aboutToNavigate();
  ++position;
  selectedFile.clear();
  render();
  emit urlChanged(locationUrl());
  emit historyChanged();
  return true;
}
bool PathBar::goForward() {
  if (position == 0)
    return false;
  emit aboutToNavigate();
  --position;
  selectedFile.clear();
  render();
  emit urlChanged(locationUrl());
  emit historyChanged();
  return true;
}
bool PathBar::goUp() {
  const QUrl url = locationUrl();
  if (Fusion::isComputer(url))
    return false;
  if (url.path().isEmpty() || url.path() == "/") {
    setLocationUrl(Fusion::computerUrl());
    return true;
  }
  QUrl parent = url;
  QString path = url.path();
  while (path.endsWith('/') && path.size() > 1)
    path.chop(1);
  parent.setPath(path.left(path.lastIndexOf('/') + 1));
  setLocationUrl(parent);
  return true;
}
bool PathBar::isUrlEditable() const { return true; }
QVariantMap PathBar::session() const {
  QVariantList urls, visits;
  for (int i = 0; i < history.size(); ++i) { urls << history[i]; visits << states[i]; }
  return {{"urls", urls}, {"visits", visits}, {"position", position}};
}
void PathBar::restoreSession(const QVariantMap &saved) {
  const auto urls = saved.value("urls").toList(), visits = saved.value("visits").toList();
  const int index = saved.value("position").toInt();
  if (urls.isEmpty() || urls.size() > 100 || visits.size() != urls.size() || index < 0 || index >= urls.size()) return;
  for (const auto &value : urls) if (!value.toUrl().isValid() || value.toUrl().isEmpty()) return;
  emit aboutToNavigate();
  history.clear(); states.clear();
  for (int i = 0; i < urls.size(); ++i) { history << urls[i].toUrl(); states << visits[i].toMap(); }
  position = index; selectedFile.clear(); render();
  emit urlChanged(locationUrl()); emit historyChanged();
}
void PathBar::setUrlEditable(bool focus) {
  input->setEditText(Fusion::displayPath(displayedUrl()));
  if (focus) {
    input->setFocus();
    input->lineEdit()->selectAll();
  }
}
void PathBar::render() {
  const QUrl url = locationUrl();
  QSignalBlocker blocker(input);
  input->clear();
  for (const auto &entry : history)
    input->addItem(Fusion::displayPath(entry));
  input->setEditText(Fusion::displayPath(displayedUrl()));
  completion->setDir(url);
}

bool PathBar::eventFilter(QObject *object, QEvent *event) {
  if (!input)
    return QWidget::eventFilter(object, event);
  if (object == input->lineEdit() && event->type() == QEvent::KeyPress &&
      static_cast<QKeyEvent *>(event)->key() == Qt::Key_Escape) {
    setUrlEditable(false);
    emit editingCancelled();
    return true;
  }
  return QWidget::eventFilter(object, event);
}
