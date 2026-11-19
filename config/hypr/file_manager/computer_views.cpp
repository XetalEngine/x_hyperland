#include "computer_views.h"
#include <functional>

namespace {
QString bytes(quint64 value) { return QLocale().formattedDataSize(value); }
QFont explorerFont(const QString &mode, int size = 9) {
  QFont result(mode == "winme" ? "Tahoma" : "Segoe UI", size);
  result.setStyleHint(QFont::SansSerif);
  return result;
}
void artwork(QPainter &painter, const QRectF &rect, const QString &kind,
             const QString &mode, const Volume &volume = {}) {
  painter.save(); painter.translate(rect.topLeft());
  painter.scale(rect.width() / 64., rect.height() / 64.);
  painter.setRenderHint(QPainter::Antialiasing, mode != "winme");
  auto path = [](std::initializer_list<QPointF> points) {
    QPainterPath result; bool first = true;
    for (const auto &point : points) { if (first) result.moveTo(point); else result.lineTo(point); first = false; }
    result.closeSubpath(); return result;
  };
  if (kind == "computer") {
    painter.setPen(QPen(QColor("#697b86"), 1.5)); painter.setBrush(QColor("#e0e1dd"));
    painter.drawRoundedRect(QRectF(8, 3, 48, 40), 3, 3);
    QLinearGradient screen(10, 6, 45, 35); screen.setColorAt(0, QColor("#92e8ff")); screen.setColorAt(.5, QColor("#1979b7")); screen.setColorAt(1, QColor("#183c81"));
    painter.setBrush(screen); painter.drawRect(QRectF(12, 7, 40, 30));
    painter.setBrush(QColor("#babebc")); painter.drawRect(QRectF(25, 44, 14, 6));
    painter.setBrush(QColor("#e1e2dc")); painter.drawPath(path({{9, 50}, {55, 50}, {62, 59}, {2, 59}}));
    painter.setPen(QColor("#777f80")); for (int y : {53, 56}) painter.drawLine(10, y, 53, y);
  } else if (kind != "drive") {
    QLinearGradient back(0, 7, 0, 52); back.setColorAt(0, QColor("#fff4a7")); back.setColorAt(1, QColor("#d49b28"));
    painter.setPen(QPen(QColor("#b78a2d"), 1)); painter.setBrush(back);
    painter.drawPath(path({{5, 13}, {23, 13}, {29, 19}, {56, 19}, {56, 54}, {5, 54}}));
    painter.setBrush(QColor("#fff9df")); painter.drawRect(QRectF(10, 23, 42, 27));
    QLinearGradient front(0, 28, 0, 57); front.setColorAt(0, QColor("#ffe58b")); front.setColorAt(1, QColor("#efc252"));
    painter.setBrush(front); painter.drawPath(path({{5, 29}, {61, 29}, {56, 57}, {5, 57}}));
    if (kind != "folder") {
      painter.setPen(QPen(QColor("#177cb3"), 4, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
      if (kind == "Downloads") {
        painter.drawLine(40, 25, 40, 48); painter.drawLine(31, 40, 40, 49); painter.drawLine(49, 40, 40, 49);
      } else if (kind == "Desktop") {
        painter.setBrush(QColor("#b9e6fa")); painter.drawRect(QRectF(24, 28, 31, 21)); painter.drawLine(39, 50, 39, 56);
      } else if (kind == "Documents") {
        painter.setBrush(QColor("#f7fcff")); painter.setPen(QPen(QColor("#2b83b3"), 2)); painter.drawRect(QRectF(30, 25, 22, 31));
        for (int y : {33, 39, 45, 51}) painter.drawLine(34, y, 47, y);
      } else {
        painter.setFont(QFont("Sans", 27, QFont::Bold));
        painter.drawText(QRectF(24, 21, 36, 39), Qt::AlignCenter,
                         kind == "Music" ? "♫" : kind == "Pictures" ? "▧" : kind == "Videos" ? "▶" : kind == "Home" ? "⌂" : "↗");
      }
    }
  } else {
    const bool flat = mode == "win11";
    QLinearGradient metal(0, 21, 0, 52); metal.setColorAt(0, QColor("#f9faf8")); metal.setColorAt(.55, QColor("#cfd5d4")); metal.setColorAt(1, QColor("#929b9d"));
    painter.setPen(QPen(QColor("#727b7d"), 1)); painter.setBrush(metal);
    painter.drawPath(path({{5, 40}, {14, 23}, {51, 23}, {60, 40}, {60, 51}, {5, 51}}));
    painter.setBrush(QColor(flat ? "#42474b" : "#c3c9c6")); painter.drawRoundedRect(QRectF(5, 40, 55, 13), 2, 2);
    painter.setPen(QColor("#f7faf6")); painter.drawLine(8, 40, 56, 40);
    painter.setPen(Qt::NoPen); painter.setBrush(QColor("#69c427")); painter.drawRoundedRect(QRectF(10, 45, 6, 3), 1, 1);
    painter.setBrush(QColor("#5e696b")); painter.drawRect(QRectF(44, 45, 10, 2));
    if (volume.optical()) {
      QConicalGradient disc(39, 22, 0); disc.setColorAt(0, QColor("#e7f3ff")); disc.setColorAt(.2, QColor("#b5cbf0")); disc.setColorAt(.4, QColor("#fff7d9")); disc.setColorAt(.6, QColor("#badcc3")); disc.setColorAt(.8, QColor("#f4e8f7")); disc.setColorAt(1, QColor("#e7f3ff"));
      painter.setPen(QPen(QColor("#8a949c"), 1)); painter.setBrush(disc); painter.drawEllipse(QRectF(19, 2, 40, 40));
      painter.setBrush(QColor("#f8f9fa")); painter.drawEllipse(QRectF(34, 17, 10, 10));
    } else if (volume.usb()) {
      painter.setPen(QPen(QColor("#788d95"), 1)); painter.setBrush(QColor("#dce6e8")); painter.drawRoundedRect(QRectF(39, 10, 17, 35), 3, 3);
      painter.setBrush(QColor("#7ea8bd")); painter.drawRect(QRectF(39, 24, 17, 21));
      painter.setBrush(QColor("#66757c")); painter.drawRect(QRectF(42, 14, 3, 5)); painter.drawRect(QRectF(50, 14, 3, 5));
    } else if (volume.mount == "/") {
      // A small Linux penguin identifies the host disk in every presentation.
      painter.setPen(Qt::NoPen); painter.setBrush(QColor("#22282a")); painter.drawEllipse(QRectF(6, 8, 22, 30)); painter.drawEllipse(QRectF(10, 3, 14, 17));
      painter.setBrush(QColor("#fffef4")); painter.drawEllipse(QRectF(10, 17, 14, 18)); painter.drawEllipse(QRectF(13, 8, 3, 5)); painter.drawEllipse(QRectF(19, 8, 3, 5));
      painter.setBrush(QColor("#e9b623")); painter.drawEllipse(QRectF(5, 33, 11, 5)); painter.drawEllipse(QRectF(20, 33, 11, 5)); painter.drawPath(path({{13, 13}, {23, 13}, {18, 18}}));
    } else if (volume.prefix()) {
      painter.setPen(Qt::NoPen); painter.setBrush(QColor("#447eac")); painter.drawRoundedRect(QRectF(36, 11, 22, 23), 4, 4);
      painter.setPen(Qt::white); painter.setFont(QFont("Sans", 13, QFont::Bold)); painter.drawText(QRectF(36, 11, 22, 23), Qt::AlignCenter, "C:");
    }
    if (volume.locked()) {
      painter.setPen(QPen(QColor("#8f7024"), 2)); painter.setBrush(Qt::NoBrush); painter.drawRoundedRect(QRectF(43, 35, 12, 13), 5, 5);
      painter.setBrush(QColor("#edc75c")); painter.drawRoundedRect(QRectF(39, 43, 20, 15), 2, 2);
    }
  }
  painter.restore();
}

class ExplorerHeading : public QAbstractButton {
public:
  explicit ExplorerHeading(QWidget *parent) : QAbstractButton(parent) {
    setCheckable(true); setChecked(true); setFocusPolicy(Qt::StrongFocus); setFixedHeight(29);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  }
protected:
  void paintEvent(QPaintEvent *) override {
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing); p.setFont(explorerFont("win7", 10));
    p.setPen(QPen(QColor("#777777"), 1.2)); p.setBrush(Qt::NoBrush);
    QPainterPath arrow; arrow.moveTo(4, isChecked() ? 11 : 9); arrow.lineTo(isChecked() ? 8 : 8, 15); arrow.lineTo(isChecked() ? 12 : 4, isChecked() ? 11 : 21); p.drawPath(arrow);
    p.setPen(QColor("#1b4b86")); p.drawText(QRect(19, 0, width() - 22, height()), Qt::AlignVCenter, text());
    const int left = 28 + p.fontMetrics().horizontalAdvance(text());
    p.setPen(QColor("#dedede")); if (left < width()) p.drawLine(left, 15, width(), 15);
    if (hasFocus()) { p.setPen(QPen(QColor("#999999"), 1, Qt::DotLine)); p.drawRect(rect().adjusted(1, 1, -2, -2)); }
  }
};
}

class ComputerItem : public QAbstractButton {
public:
  Volume volume;
  QUrl location;
  QString key, title, kind, mode;
  int category = 0;
  std::function<void()> chosen, opened;
  std::function<void(int)> moved;
  explicit ComputerItem(QWidget *parent) : QAbstractButton(parent) {
    setObjectName("windowsComputerItem"); setCheckable(true); setFocusPolicy(Qt::StrongFocus);
    setContextMenuPolicy(Qt::CustomContextMenu); setMouseTracking(true);
  }
  void updateItem() {
    setProperty("device", volume.device); setProperty("location", location); setProperty("category", category);
    setAccessibleName(title + (volume.device.isEmpty() ? QString() : " · " + detail()));
    setToolTip(title + "\n" + (volume.device.isEmpty() ? location.toDisplayString(QUrl::RemovePassword)
        : volume.driveModel + "\n" + volume.device + "\n" + detail()));
    setMinimumWidth(0); setMaximumWidth(QWIDGETSIZE_MAX);
    setFixedHeight(mode == "winme" ? 96 : kind != "drive" ? 70 : mode == "win11" ? 92 : 78);
    update();
  }
  QString detail() const {
    if (volume.prefix()) return volume.type == "steam-prefix" ? "Steam prefix" : "Wine / Proton prefix";
    if (volume.mounted() && volume.spaceKnown && volume.total)
      return bytes(volume.available) + " free of " + bytes(volume.total);
    if (volume.optical() && !volume.size) return "No disc inserted";
    return (volume.filesystem.isEmpty() ? QString() : volume.filesystem.toUpper() + " · ") + (volume.size ? bytes(volume.size) : QString("Capacity unavailable"));
  }
protected:
  void paintEvent(QPaintEvent *) override {
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing); p.setFont(explorerFont(mode));
    const bool classic = mode == "winme";
    if (!classic && (isChecked() || underMouse())) {
      QLinearGradient shade(0, 0, 0, height()); shade.setColorAt(0, QColor(isChecked() ? "#e5f2ff" : "#f5faff")); shade.setColorAt(1, QColor(isChecked() ? "#cfe4fa" : "#e9f3fc"));
      p.setPen(QColor(isChecked() ? "#7da6cf" : "#b9d5ef")); p.setBrush(shade);
      p.drawRoundedRect(QRectF(rect()).adjusted(.5, .5, -.5, -.5), mode == "win11" ? 5 : 2, mode == "win11" ? 5 : 2);
    }
    const auto icon = classic ? QRectF((width() - 34) / 2., 4, 34, 34) : QRectF(8, (height() - 52) / 2., 52, 52);
    artwork(p, icon, kind, mode, volume);
    if (classic) {
      auto textRect = QRect(3, 42, width() - 6, 48);
      const auto caption = p.fontMetrics().elidedText(title, Qt::ElideRight, 2 * textRect.width());
      QTextLayout text(caption, p.font()); QTextOption option; option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere); option.setAlignment(Qt::AlignHCenter); text.setTextOption(option);
      text.beginLayout(); qreal height = 0;
      for (int row = 0; row < 2; ++row) {
        auto line = text.createLine(); if (!line.isValid()) break;
        line.setLineWidth(textRect.width()); line.setPosition(QPointF(0, height)); height += line.height();
      }
      text.endLayout(); textRect.setHeight(qCeil(height));
      if (isChecked()) p.fillRect(textRect, QColor("#0a246a"));
      p.setPen(isChecked() ? Qt::white : Qt::black);
      text.draw(&p, textRect.topLeft());
      if (hasFocus()) { p.setPen(QPen(isChecked() ? Qt::white : Qt::black, 1, Qt::DotLine)); p.setBrush(Qt::NoBrush); p.drawRect(textRect.adjusted(0, 0, -1, -1)); }
      return;
    }
    const int x = 68, available = qMax(1, width() - x - 10);
    p.setPen(mode == "win11" && kind == "drive" ? QColor("#0067c0") : QColor("#111111"));
    p.drawText(QRect(x, kind == "drive" ? 8 : (height() - 22) / 2, available, 22), Qt::AlignVCenter,
               p.fontMetrics().elidedText(title, Qt::ElideRight, available));
    if (kind != "drive") return;
    const bool known = volume.mounted() && volume.spaceKnown && volume.total && !volume.prefix();
    if (known) {
      const QRectF bar(x, mode == "win11" ? 33 : 31, available, 13);
      p.setPen(QColor("#b3b7bb")); p.setBrush(QColor("#e7e7e7")); p.drawRect(bar);
      const qreal used = qBound(0., 1. - double(volume.available) / volume.total, 1.);
      QLinearGradient fill(bar.topLeft(), bar.bottomLeft());
      fill.setColorAt(0, QColor(used > .9 ? "#ed6964" : mode == "win7" ? "#8ed5f1" : "#58bce8"));
      fill.setColorAt(1, QColor(used > .9 ? "#cc241c" : "#1596c8"));
      p.fillRect(QRectF(bar.x() + 1, bar.y() + 1, qMax(0., (bar.width() - 2) * used), bar.height() - 2), fill);
    }
    p.setPen(QColor("#5c6369"));
    p.drawText(QRect(x, known ? 49 : 30, available, 20), Qt::AlignVCenter,
               p.fontMetrics().elidedText(detail(), Qt::ElideRight, available));
    if (!known && !volume.prefix() && !(volume.optical() && !volume.size)) {
      p.setPen(QColor("#777777"));
      p.drawText(QRect(x, 50, available, 19), Qt::AlignVCenter,
                 volume.locked() ? "Encrypted" : volume.filesystem == "swap" ? "Swap" : volume.mounted() ? "Mounted" : "Not mounted");
    }
    if (hasFocus()) { p.setPen(QPen(QColor("#7c9bba"), 1, Qt::DotLine)); p.setBrush(Qt::NoBrush); p.drawRect(rect().adjusted(2, 2, -3, -3)); }
  }
  void mousePressEvent(QMouseEvent *event) override {
    if (event->button() == Qt::LeftButton || event->button() == Qt::RightButton) { setFocus(Qt::MouseFocusReason); if (chosen) chosen(); event->accept(); }
    else QAbstractButton::mousePressEvent(event);
  }
  void mouseDoubleClickEvent(QMouseEvent *event) override {
    if (event->button() == Qt::LeftButton) { if (chosen) chosen(); if (opened) opened(); event->accept(); }
    else QAbstractButton::mouseDoubleClickEvent(event);
  }
  void keyPressEvent(QKeyEvent *event) override {
    if (event->modifiers() == Qt::NoModifier) {
      if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) { if (opened) opened(); event->accept(); return; }
      if (event->key() == Qt::Key_Space) { if (chosen) chosen(); event->accept(); return; }
      if (event->key() >= Qt::Key_Left && event->key() <= Qt::Key_Down) { if (moved) moved(event->key()); event->accept(); return; }
    }
    QAbstractButton::keyPressEvent(event);
  }
  void focusInEvent(QFocusEvent *event) override { QAbstractButton::focusInEvent(event); if (chosen) chosen(); update(); }
  void enterEvent(QEnterEvent *event) override { QAbstractButton::enterEvent(event); update(); }
  void leaveEvent(QEvent *event) override { QAbstractButton::leaveEvent(event); update(); }
};

WindowsComputerView::WindowsComputerView(Fusion::Preferences *settings, QWidget *parent)
    : QScrollArea(parent), preferences(settings) {
  setObjectName("windowsComputerView"); setFrameShape(QFrame::NoFrame); setWidgetResizable(true);
  setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff); viewport()->installEventFilter(this);
  setStyleSheet("QScrollArea#windowsComputerView, QWidget#explorerBody, QWidget#explorerContent, QWidget#explorerSection, QWidget#explorerItems {background:white; color:#111; border:none;}"
                "QWidget#explorerInformation {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #eef6fa,stop:.3 #fff,stop:1 #fff); color:#111;}"
                "QWidget#explorerInformation QLabel {background:transparent; color:#111; font-family:Tahoma; font-size:12px; border:none;}"
                "QWidget#explorerInformation QLabel#explorerInfoName {font-weight:bold; font-size:19px; padding-bottom:7px; border-bottom:2px solid #739bd1;}"
                "QWidget#explorerInformation QLabel#explorerInfoDetails {padding:6px 0;}"
                "QLabel#explorerEmpty {background:transparent; color:#626c76; padding:12px;}"
                "QWidget#explorerInformation QToolButton {background:transparent; color:#0000c0; border:none; text-align:left; text-decoration:underline; padding:2px 0;}"
                "QWidget#explorerInformation QToolButton:focus {border:1px dotted #555;}"
                "QAbstractButton#windowsComputerItem {background:transparent; border:none; padding:0;}");
  body = new QWidget; body->setObjectName("explorerBody");
  auto *layout = new QHBoxLayout(body); layout->setContentsMargins(10, 8, 10, 16); layout->setSpacing(18);
  information = new QWidget; information->setObjectName("explorerInformation"); information->setFixedWidth(180);
  auto *info = new QVBoxLayout(information); info->setContentsMargins(4, 4, 8, 4); info->setSpacing(7);
  auto *computer = new QLabel; QPixmap picture(64, 64); picture.fill(Qt::transparent); QPainter painter(&picture); artwork(painter, picture.rect(), "computer", "winme"); painter.end(); computer->setPixmap(picture);
  info->addWidget(computer);
  infoName = new QLabel("My Computer"); infoName->setObjectName("explorerInfoName"); infoName->setTextFormat(Qt::PlainText); infoName->setWordWrap(true); info->addWidget(infoName);
  infoDetails = new QLabel; infoDetails->setObjectName("explorerInfoDetails"); infoDetails->setTextFormat(Qt::PlainText); infoDetails->setWordWrap(true); info->addWidget(infoDetails);
  info->addWidget(new QLabel("See also:"));
  auto link = [&](const QString &title, const QUrl &url) {
    auto *button = new QToolButton; button->setText(title); button->setCursor(Qt::PointingHandCursor); info->addWidget(button, 0, Qt::AlignLeft);
    connect(button, &QToolButton::clicked, this, [this, url] { emit locationRequested(url); });
  };
  link("Home", QUrl::fromLocalFile(QDir::homePath())); link("Network", QUrl("remote:/"));
  auto *panel = new QToolButton; panel->setText("Control Panel"); panel->setCursor(Qt::PointingHandCursor); info->addWidget(panel, 0, Qt::AlignLeft);
  connect(panel, &QToolButton::clicked, this, &WindowsComputerView::controlPanelRequested);
  info->addStretch(); layout->addWidget(information);
  content = new QWidget; content->setObjectName("explorerContent");
  auto *groups = new QVBoxLayout(content); groups->setContentsMargins(0, 0, 0, 0); groups->setSpacing(14);
  for (int category = 0; category <= 5; ++category) {
    Section section; section.body = new QWidget; section.body->setObjectName("explorerSection"); section.body->setProperty("category", category);
    auto *group = new QVBoxLayout(section.body); group->setContentsMargins(0, 0, 0, 0); group->setSpacing(2);
    section.heading = new ExplorerHeading(section.body); section.heading->setObjectName("explorerSectionHeading"); group->addWidget(section.heading);
    section.items = new QWidget; section.items->setObjectName("explorerItems");
    section.grid = new QGridLayout(section.items); section.grid->setContentsMargins(0, 0, 0, 0); section.grid->setHorizontalSpacing(12); section.grid->setVerticalSpacing(4); section.grid->setAlignment(Qt::AlignTop | Qt::AlignLeft);
    group->addWidget(section.items); groups->addWidget(section.body);
    connect(section.heading, &QAbstractButton::toggled, this, [this, category](bool expanded) {
      sections[category].items->setVisible(expanded);
      preferences->settings.setValue("computer/groups/" + mode + '/' + QString::number(category), expanded);
      if (!expanded && sections[category].keys.contains(selected)) choose({}, true);
    });
    sections.insert(category, section);
  }
  emptyMessage = new QLabel("Nothing to show. Connect a drive or enable Show unmounted drives.");
  emptyMessage->setObjectName("explorerEmpty"); emptyMessage->setWordWrap(true); groups->addWidget(emptyMessage);
  groups->addStretch(); layout->addWidget(content, 1); setWidget(body);
  content->setContextMenuPolicy(Qt::CustomContextMenu);
  connect(content, &QWidget::customContextMenuRequested, this, [this](const QPoint &point) { emit backgroundContextRequested(content->mapToGlobal(point)); });
}

void WindowsComputerView::refresh(const QString &nextMode, const QList<Volume> &volumes,
                                  const QMap<QString, int> &categories) {
  const bool modeChanged = mode != nextMode; mode = nextMode;
  const auto focused = QPointer<QWidget>(QApplication::focusWidget());
  QSet<QString> dataDisks;
  for (const auto &volume : volumes) if (!volume.compactCard()) dataDisks.insert(volume.driveKey());
  for (auto &section : sections) section.keys.clear();
  QStringList nextOrder;
  auto add = [&](const QString &key, const QString &title, const QString &kind, int category, const Volume &volume, const QUrl &url) {
    auto *item = items.value(key);
    if (!item) {
      item = new ComputerItem(content); items.insert(key, item); item->key = key;
      item->chosen = [this, key] { choose(key, true); };
      item->opened = [this, key] { activate(key); };
      item->moved = [this, key](int direction) { step(key, direction); };
      connect(item, &QAbstractButton::clicked, this, [this, key] { choose(key, true); });
      connect(item, &QWidget::customContextMenuRequested, this, [this, item](const QPoint &point) {
        choose(item->key, true);
        if (!item->volume.device.isEmpty()) emit volumeContextRequested(item->volume, item->mapToGlobal(point.x() < 0 ? item->rect().center() : point));
      });
    }
    item->title = title; item->kind = kind; item->mode = mode; item->volume = volume; item->location = url; item->category = category; item->updateItem();
    nextOrder << key; sections[category].keys << key;
  };
  if (mode == "win10") for (const auto &place : Fusion::defaultPlaces())
    add("folder:" + place["url"].toString(), place["name"].toString(), place["name"].toString(), 0, {}, QUrl(place["url"].toString()));
  for (const auto &volume : volumes) {
    if (volume.compactCard() && dataDisks.contains(volume.driveKey())) continue;
    const int source = categories.value(volume.driveKey(), 5);
    const int category = source <= 1 ? 1 : source == 2 ? (mode == "win7" ? 2 : 1) : source <= 4 ? 3 : 5;
    add(volume.device, volume.name, "drive", category, volume, {});
  }
  if (mode == "winme") add("control-panel", "Control Panel", "folder", 1, {}, {});
  if (mode == "win10") for (const auto &place : preferences->places()) {
    const QUrl url(place["url"].toString());
    if (QStringList{"smb", "sftp", "ftp", "ftps", "nfs", "afp", "dav", "davs"}.contains(url.scheme()))
      add("network:" + url.toString(), place["name"].toString(), "Network", 4, {}, url);
  }
  for (const auto &key : items.keys()) if (!nextOrder.contains(key)) delete items.take(key);
  emptyMessage->setVisible(nextOrder.isEmpty());
  const QMap<int, QString> titles{{0, "Folders"}, {1, mode == "win7" ? "Hard Disk Drives" : "Devices and drives"},
      {2, "Devices with Removable Storage"}, {3, "Wine, Proton & Steam prefixes"}, {4, "Network locations"}, {5, "Unmounted devices"}};
  for (auto it = sections.begin(); it != sections.end(); ++it) {
    auto &section = it.value();
    section.heading->setText(titles[it.key()] + QString(" (%1)").arg(section.keys.size()));
    section.heading->setVisible(!(mode == "winme" && it.key() == 1));
    const bool expanded = mode == "winme" && it.key() == 1 ? true : preferences->settings.value("computer/groups/" + mode + '/' + QString::number(it.key()), true).toBool();
    { QSignalBlocker block(section.heading); section.heading->setChecked(expanded); }
    section.items->setVisible(expanded); section.body->setVisible(!section.keys.isEmpty());
  }
  relayout(); choose(selected, false);
  if (!modeChanged && focused && isAncestorOf(focused) && focused->isVisible()) focused->setFocus(Qt::OtherFocusReason);
}

bool WindowsComputerView::containsDevice(const QString &device) const {
  return items.contains(device) && !items[device]->volume.device.isEmpty();
}
void WindowsComputerView::selectDevice(const QString &device, bool focus) {
  // Keep folder selection when the owning drive shelf clears its volume selection.
  if (device.isEmpty() && items.contains(selected) && items[selected]->volume.device.isEmpty()) return;
  choose(device, false);
  if (auto *item = items.value(selected); item) {
    sections[item->category].heading->setChecked(true);
    if (focus) { item->setFocus(Qt::OtherFocusReason); ensureWidgetVisible(item, 0, 12); }
  }
}
void WindowsComputerView::choose(const QString &key, bool notify) {
  selected = items.contains(key) ? key : QString();
  for (auto *item : items) item->setChecked(item->key == selected);
  auto *item = items.value(selected);
  infoName->setText(item ? item->title : "My Computer");
  infoDetails->setText(item ? (item->volume.device.isEmpty() ? "Double-click to open." : item->detail() + "\n\n" + item->volume.driveModel)
                           : "Select an item to view its description.\n\nDisplays the files and folders on your computer.");
  if (notify) emit volumeSelected(item ? item->volume.device : QString());
}
void WindowsComputerView::activate(const QString &key) {
  auto *item = items.value(key); if (!item) return;
  choose(key, true);
  if (!item->volume.device.isEmpty()) emit operationRequested(item->volume, "open");
  else if (key == "control-panel") emit controlPanelRequested();
  else if (item->location.isValid()) emit locationRequested(item->location);
}
void WindowsComputerView::step(const QString &key, int direction) {
  QStringList visible;
  for (const auto &section : sections) if (section.heading->isChecked()) visible << section.keys;
  auto *item = items.value(key); if (!item) return;
  const int columns = sections[item->category].columns;
  const int delta = direction == Qt::Key_Up ? -columns : direction == Qt::Key_Down ? columns : direction == Qt::Key_Left ? -1 : 1;
  const int next = visible.indexOf(key) + delta;
  if (next >= 0 && next < visible.size()) {
    choose(visible[next], true); items[visible[next]]->setFocus(Qt::OtherFocusReason); ensureWidgetVisible(items[visible[next]], 0, 12);
  }
}
void WindowsComputerView::relayout() {
  information->setVisible(mode == "winme" && viewport()->width() >= 490);
  const int width = qMax(80, viewport()->width() - 20 - (information->isHidden() ? 0 : 198));
  const int ideal = mode == "winme" ? 100 : mode == "win11" ? 330 : 310;
  const int columns = qMax(1, (width + 12) / (ideal + 12));
  const int itemWidth = qMin(ideal, width);
  for (auto &section : sections) {
    if (section.columns == columns && section.grid->count() == section.keys.size()) {
      bool same = true;
      for (int i = 0; i < section.keys.size(); ++i) {
        const auto *at = section.grid->itemAtPosition(i / columns, i % columns);
        if (!at || at->widget() != items[section.keys[i]]) { same = false; break; }
      }
      if (same) { for (const auto &key : section.keys) items[key]->setFixedWidth(itemWidth); continue; }
    }
    while (auto *entry = section.grid->takeAt(0)) delete entry;
    for (int i = 0; i < section.keys.size(); ++i) {
      auto *item = items[section.keys[i]]; item->setFixedWidth(itemWidth);
      section.grid->addWidget(item, i / columns, i % columns, Qt::AlignTop | Qt::AlignLeft); item->show();
    }
    section.columns = columns;
  }
}
bool WindowsComputerView::eventFilter(QObject *object, QEvent *event) {
  if (object == viewport() && (event->type() == QEvent::Resize || event->type() == QEvent::Show)) relayout();
  return QScrollArea::eventFilter(object, event);
}
