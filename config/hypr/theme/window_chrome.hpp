// Shared, native Qt window actions for Fusion's C++ application headers.
#pragma once
#include <QtWidgets>

namespace FusionChrome {
inline void toggleMaximized(QWidget *window) {
  if (window->isMaximized() || window->isFullScreen()) window->showNormal();
  else window->showMaximized();
}

class Button final : public QToolButton {
public:
  enum Symbol { Minimize, Maximize, Restore, Close } symbol;
  explicit Button(Symbol symbol, QWidget *parent) : QToolButton(parent), symbol(symbol) {
    setFixedSize(32,32);setCursor(Qt::PointingHandCursor);setFocusPolicy(Qt::NoFocus);
  }
protected:
  void paintEvent(QPaintEvent *event) override {
    QToolButton::paintEvent(event);
    QStyleOptionToolButton option;initStyleOption(&option);
    QPainter p(this);p.setRenderHint(QPainter::Antialiasing);p.translate(width()/2.,height()/2.);
    // Our glyph is painted separately from QToolButton's label. Match the
    // local highlight hover surface explicitly; initStyleOption retains the
    // normal ButtonText even when a stylesheet supplies a hover text color.
    const bool highlighted=(option.state&QStyle::State_Enabled) &&
                           (option.state&QStyle::State_MouseOver) && !(option.state&QStyle::State_Sunken);
    p.setPen(QPen(option.palette.color(highlighted?QPalette::HighlightedText:QPalette::ButtonText),1.5,Qt::SolidLine,Qt::SquareCap));
    if(symbol==Minimize)p.drawLine(QPointF(-5,3),QPointF(5,3));
    else if(symbol==Maximize)p.drawRect(QRectF(-5,-5,10,10));
    else if(symbol==Restore){
      p.drawPolyline(QPolygonF{QPointF(-2,-4),QPointF(-2,-6),QPointF(6,-6),QPointF(6,2),QPointF(4,2)});
      p.drawRect(QRectF(-5,-2,8,8));
    }else{
      p.drawLine(QPointF(-4.5,-4.5),QPointF(4.5,4.5));p.drawLine(QPointF(-4.5,4.5),QPointF(4.5,-4.5));
    }
  }
};

class Controls final : public QWidget {
  QWidget *owner;
  Button *maximize;
  void sync(){
    const bool restore=owner->isMaximized()||owner->isFullScreen();
    maximize->symbol=restore?Button::Restore:Button::Maximize;
    const auto caption=restore?tr("Restore"):tr("Maximize");
    maximize->setToolTip(caption);maximize->setAccessibleName(caption);maximize->update();
  }
public:
  explicit Controls(QWidget *window) : QWidget(window),owner(window) {
    setObjectName("windowControls");setSizePolicy(QSizePolicy::Fixed,QSizePolicy::Fixed);
    setStyleSheet("QWidget#windowControls {background:transparent;} "
                  "QToolButton {background:transparent; border:1px solid transparent; border-radius:6px; padding:0;} "
                  "QToolButton:hover {background:palette(highlight); border-color:palette(link);} "
                  "QToolButton:pressed {background:palette(mid);} QToolButton:focus {border-color:palette(highlight);}");
    auto *row=new QHBoxLayout(this);row->setContentsMargins(0,0,0,0);row->setSpacing(2);
    auto *minimize=new Button(Button::Minimize,this);minimize->setObjectName("windowMinimize");
    minimize->setToolTip(tr("Minimize"));minimize->setAccessibleName(tr("Minimize"));row->addWidget(minimize);
    maximize=new Button(Button::Maximize,this);maximize->setObjectName("windowMaximize");row->addWidget(maximize);
    auto *close=new Button(Button::Close,this);close->setObjectName("windowClose");
    close->setToolTip(tr("Close"));close->setAccessibleName(tr("Close"));row->addWidget(close);
    connect(minimize,&QToolButton::clicked,owner,&QWidget::showMinimized);
    connect(maximize,&QToolButton::clicked,owner,[this]{toggleMaximized(owner);});
    connect(close,&QToolButton::clicked,owner,&QWidget::close);
    owner->installEventFilter(this);sync();
  }
protected:
  bool eventFilter(QObject *,QEvent *event) override {
    if(event->type()==QEvent::WindowStateChange||event->type()==QEvent::Show)sync();
    return false;
  }
};
}
