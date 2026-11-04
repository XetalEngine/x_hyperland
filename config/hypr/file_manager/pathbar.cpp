#include "pathbar.h"
#include "core.h"
#include <KUrlCompletion>

PathBar::PathBar(QWidget *parent)
    : QWidget(parent), history{Fusion::computerUrl()} {
  auto *layout = new QHBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  stack = new QStackedWidget;
  layout->addWidget(stack);
  setMinimumWidth(160);
  scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scroll->setFixedHeight(36);
  crumbs = new QWidget;
  crumbs->setObjectName("breadcrumbs");
  trail = new QHBoxLayout(crumbs);
  trail->setContentsMargins(4, 0, 4, 0);
  trail->setSpacing(2);
  scroll->setWidget(crumbs);
  crumbs->installEventFilter(this);
  scroll->viewport()->installEventFilter(this);
  stack->addWidget(scroll);
  input = new KUrlComboBox(KUrlComboBox::Directories, true);
  input->setObjectName("pathEditor");
  input->setInsertPolicy(QComboBox::NoInsert);
  input->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  completion = new KUrlCompletion(KUrlCompletion::DirCompletion);
  completion->setParent(input);
  input->setCompletionObject(completion);
  input->setAutoDeleteCompletionObject(false);
  input->lineEdit()->installEventFilter(this);
  stack->addWidget(input);
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
    while (position > 0) {
      history.removeFirst();
      --position;
    }
    history.prepend(normalized);
    while (history.size() > 100)
      history.removeLast();
    render();
    emit urlChanged(normalized);
    emit historyChanged();
  } else
    render();
}
bool PathBar::goBack() {
  if (position + 1 >= history.size())
    return false;
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
bool PathBar::isUrlEditable() const { return stack->currentWidget() == input; }
void PathBar::setUrlEditable(bool value) {
  stack->setCurrentWidget(value ? static_cast<QWidget *>(input) : scroll);
  if (value) {
    input->setEditText(Fusion::displayPath(displayedUrl()));
    input->setFocus();
    input->lineEdit()->selectAll();
  }
  emit editableStateChanged(value);
}
void PathBar::render() {
  while (auto *item = trail->takeAt(0)) {
    if (item->widget())
      item->widget()->deleteLater();
    delete item;
  }
  const QUrl url = locationUrl();
  auto crumb = [this](const QString &text, const QUrl &url) {
    auto *button = new QToolButton;
    button->setText(QString(text).replace('&', "&&"));
    button->setToolTip(Fusion::displayPath(url));
    button->setAutoRaise(true);
    button->setMinimumHeight(30);
    button->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Preferred);
    connect(button, &QToolButton::clicked, this, [this, url] {
      if (QApplication::keyboardModifiers() & Qt::ControlModifier)
        emit tabRequested(url);
      else
        setLocationUrl(url);
    });
    trail->addWidget(button);
  };
  if (Fusion::isComputer(url))
    crumb("This PC", url);
  else {
    QUrl part = url;
    part.setPath("/");
    part.setQuery(QString());
    part.setFragment(QString());
    crumb(url.isLocalFile() ? "/" : url.scheme() + "://" + url.host(), part);
    QString path;
    for (const auto &segment : url.path().split('/', Qt::SkipEmptyParts)) {
      auto *arrow = new QLabel("›");
      arrow->setObjectName("muted");
      trail->addWidget(arrow);
      path += '/' + segment;
      part.setPath(path);
      crumb(segment, part);
    }
  }
  if (!selectedFile.isEmpty()) {
    auto *arrow = new QLabel("›");
    arrow->setObjectName("muted");
    trail->addWidget(arrow);
    // Files are shown as the final segment, never entered as directories.
    auto *file = new QLabel(selectedFile.fileName());
    file->setObjectName("selectedFilePath");
    file->setTextFormat(Qt::PlainText);
    file->setToolTip(Fusion::displayPath(selectedFile));
    file->installEventFilter(this);
    trail->addWidget(file);
  }
  auto *empty = new QWidget;
  empty->setMinimumWidth(20);
  empty->installEventFilter(this);
  trail->addWidget(empty, 1);
  crumbs->setMinimumWidth(trail->sizeHint().width());
  QSignalBlocker blocker(input);
  input->clear();
  for (const auto &entry : history)
    input->addItem(Fusion::displayPath(entry));
  input->setEditText(Fusion::displayPath(displayedUrl()));
  completion->setDir(url);
  QTimer::singleShot(0, this, [this] {
    scroll->horizontalScrollBar()->setValue(
        scroll->horizontalScrollBar()->maximum());
  });
}
bool PathBar::eventFilter(QObject *object, QEvent *event) {
  if (!input)
    return QWidget::eventFilter(object, event);
  if (object == input->lineEdit() && event->type() == QEvent::KeyPress &&
      static_cast<QKeyEvent *>(event)->key() == Qt::Key_Escape) {
    setUrlEditable(false);
    return true;
  }
  if (object != input->lineEdit() &&
      event->type() == QEvent::MouseButtonRelease &&
      static_cast<QMouseEvent *>(event)->button() == Qt::LeftButton) {
    setUrlEditable(true);
    return true;
  }
  return QWidget::eventFilter(object, event);
}
