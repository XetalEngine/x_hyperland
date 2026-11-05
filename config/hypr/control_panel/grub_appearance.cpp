#include "grub_appearance.h"
#include <QtWidgets>
#include <QProcess>

namespace {
QLabel *note(const QString &text, QWidget *parent, const char *name = "") {
  auto *label = new QLabel(text, parent); label->setObjectName(name);
  label->setTextFormat(Qt::PlainText); label->setWordWrap(true); return label;
}
QWidget *sliderRow(QSlider *slider, QWidget *parent) {
  auto *row = new QWidget(parent); auto *layout = new QHBoxLayout(row);
  layout->setContentsMargins(0, 0, 0, 0); auto *value = new QLabel(row);
  value->setMinimumWidth(38); value->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
  layout->addWidget(slider, 1); layout->addWidget(value);
  QObject::connect(slider, &QSlider::valueChanged, value, [value](int n) { value->setText(QString::number(n)+"%"); });
  return row;
}
}

class GrubDesignPreview final : public QWidget {
public:
  QPixmap image;
  explicit GrubDesignPreview(QWidget *parent) : QWidget(parent) {
    setObjectName("grubDesignPreview"); setMinimumSize(340, 250);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setAccessibleName("Boot menu design preview");
  }
  void paintEvent(QPaintEvent *) override {
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing);
    QRectF bounds = rect().adjusted(2, 2, -2, -2);
    p.setPen(QPen(palette().color(QPalette::Mid), 1)); p.setBrush(palette().color(QPalette::Base));
    p.drawRoundedRect(bounds, 14, 14);
    if (image.isNull()) {
      p.setPen(palette().color(QPalette::PlaceholderText));
      p.drawText(rect(), Qt::AlignCenter, "Choose a theme to preview your boot screen"); return;
    }
    QSizeF size = image.size(); size.scale(bounds.size()-QSizeF(16, 16), Qt::KeepAspectRatio);
    QRectF target(QPointF(), size); target.moveCenter(bounds.center());
    p.setRenderHint(QPainter::SmoothPixmapTransform);
    QPainterPath clip; clip.addRoundedRect(target, 9, 9); p.setClipPath(clip);
    p.drawPixmap(target, image, image.rect());
  }
};

GrubAppearance::GrubAppearance(const QString &helper, QWidget *parent) : QWidget(parent), helper(helper) {
  setObjectName("grubAppearanceTab");
  auto *layout = new QVBoxLayout(this); layout->setSpacing(12);
  layout->addWidget(note("Make the first screen yours. Start with a Fusion theme, then choose its picture, colors and menu layout.", this));
  auto *scroll = new QScrollArea(this); scroll->setWidgetResizable(true); scroll->setFrameShape(QFrame::NoFrame);
  content = new QWidget(scroll); auto *canvas = new QVBoxLayout(content); canvas->setContentsMargins(0, 0, 4, 0); canvas->setSpacing(14);
  themes = new QListWidget(content); themes->setObjectName("grubAppearanceThemes");
  themes->setViewMode(QListView::IconMode); themes->setFlow(QListView::LeftToRight);
  themes->setWrapping(false); themes->setMovement(QListView::Static); themes->setResizeMode(QListView::Adjust);
  themes->setSelectionMode(QAbstractItemView::SingleSelection); themes->setIconSize(QSize(154, 80));
  themes->setGridSize(QSize(174, 116)); themes->setFixedHeight(142);
  themes->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
  themes->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  themes->setAccessibleName("Boot screen themes"); canvas->addWidget(themes);
  body = new QBoxLayout(QBoxLayout::LeftToRight); body->setSpacing(18); canvas->addLayout(body, 1);
  auto *previewColumn = new QWidget(content); auto *previewLayout = new QVBoxLayout(previewColumn);
  previewLayout->setContentsMargins(0, 0, 0, 0);
  selection = note("BOOT SCREEN PREVIEW", previewColumn, "muted"); previewLayout->addWidget(selection);
  preview = new GrubDesignPreview(previewColumn); previewLayout->addWidget(preview, 1);
  caption = note("Preview only · Changes are applied when you choose Apply for next boot.", previewColumn, "grubPreviewStatus");
  previewLayout->addWidget(caption); body->addWidget(previewColumn, 1);
  controls = new QScrollArea(content); controls->setWidgetResizable(true); controls->setFrameShape(QFrame::NoFrame);
  controls->setMinimumWidth(310); controls->setMaximumWidth(360); controls->setMinimumHeight(310);
  auto *formWidget = new QWidget(controls); auto *form = new QVBoxLayout(formWidget); form->setContentsMargins(4, 0, 10, 4); form->setSpacing(10);
  form->addWidget(note("Picture", formWidget, "panelTitle"));
  pictures = new QComboBox(formWidget); pictures->setObjectName("grubAppearancePicture");
  pictures->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); pictures->setMinimumContentsLength(22);
  form->addWidget(pictures);
  browse = new QPushButton(QIcon::fromTheme("folder-pictures"), "Choose picture…", formWidget);
  browse->setObjectName("grubAppearanceBrowse"); form->addWidget(browse);
  dimming = new QSlider(Qt::Horizontal, formWidget); dimming->setRange(0, 95); dimming->setObjectName("grubAppearanceDimming");
  form->addWidget(note("Picture dimming", formWidget)); form->addWidget(sliderRow(dimming, formWidget));
  contrast = new QSlider(Qt::Horizontal, formWidget); contrast->setRange(0, 95); contrast->setObjectName("grubAppearanceContrast");
  form->addWidget(note("Menu shading", formWidget)); form->addWidget(sliderRow(contrast, formWidget));
  form->addWidget(note("Menu & lettering", formWidget, "panelTitle"));
  position = new QComboBox(formWidget); position->setObjectName("grubAppearancePosition");
  position->addItem("Menu on the left", "left"); position->addItem("Centered menu", "center"); position->addItem("Menu on the right", "right"); form->addWidget(position);
  heading = new QLineEdit(formWidget); heading->setObjectName("grubAppearanceHeading"); heading->setMaxLength(64);
  subtitle = new QLineEdit(formWidget); subtitle->setObjectName("grubAppearanceSubtitle"); subtitle->setMaxLength(100);
  form->addWidget(note("Heading", formWidget)); form->addWidget(heading);
  form->addWidget(note("Subtitle", formWidget)); form->addWidget(subtitle);
  textSize = new QComboBox(formWidget); textSize->setObjectName("grubAppearanceTextSize");
  textSize->addItem("Small menu text", 18); textSize->addItem("Regular menu text", 22); textSize->addItem("Large menu text", 28); form->addWidget(textSize);
  auto *colors = new QHBoxLayout;
  accent = new QPushButton("Accent", formWidget); textColor = new QPushButton("Text", formWidget); base = new QPushButton("Shade", formWidget);
  accent->setObjectName("grubAppearanceAccent"); textColor->setObjectName("grubAppearanceTextColor"); base->setObjectName("grubAppearanceBase");
  colors->addWidget(accent); colors->addWidget(textColor); colors->addWidget(base); form->addLayout(colors);
  hints = new QCheckBox("Show navigation hints", formWidget); hints->setObjectName("grubAppearanceHints"); form->addWidget(hints);
  auto *reset = new QPushButton("Reset this theme", formWidget); reset->setObjectName("grubAppearanceReset"); form->addWidget(reset); form->addStretch();
  controls->setWidget(formWidget); body->addWidget(controls); scroll->setWidget(content); layout->addWidget(scroll, 1);
  auto *actions = new QHBoxLayout;
  reload = new QPushButton("Reload applied design", this); reload->setObjectName("grubAppearanceReload");
  restore = new QPushButton("Use system appearance", this); restore->setObjectName("grubAppearanceSystem");
  undo = new QPushButton("Undo appearance", this); undo->setObjectName("grubAppearanceUndo");
  apply = new QPushButton("Apply for next boot", this); apply->setProperty("primary", true); apply->setObjectName("grubAppearanceApply");
  actions->addWidget(reload); actions->addWidget(restore); actions->addWidget(undo); actions->addStretch(); actions->addWidget(apply); layout->addLayout(actions);

  catalog = new QProcess(this); renderer = new QProcess(this); debounce = new QTimer(this);
  debounce->setSingleShot(true); debounce->setInterval(220);
  connect(debounce, &QTimer::timeout, this, &GrubAppearance::renderPreview);
  connect(reload, &QPushButton::clicked, this, &GrubAppearance::loadCatalog);
  connect(themes, &QListWidget::currentItemChanged, this, [this] {
    if (!syncing && themes->currentItem()) loadOptions(themes->currentItem()->data(Qt::UserRole).toJsonObject()["options"].toObject());
  });
  connect(reset, &QPushButton::clicked, this, [this] {
    if (themes->currentItem()) loadOptions(themes->currentItem()->data(Qt::UserRole).toJsonObject()["options"].toObject());
  });
  for (auto *combo : {pictures, position, textSize}) connect(combo, qOverload<int>(&QComboBox::currentIndexChanged), this, &GrubAppearance::changed);
  for (auto *edit : {heading, subtitle}) connect(edit, &QLineEdit::textChanged, this, &GrubAppearance::changed);
  for (auto *slider : {dimming, contrast}) connect(slider, &QSlider::valueChanged, this, &GrubAppearance::changed);
  connect(hints, &QCheckBox::toggled, this, &GrubAppearance::changed);
  connect(accent, &QPushButton::clicked, this, [this] { chooseColor("accent", accent); });
  connect(textColor, &QPushButton::clicked, this, [this] { chooseColor("text", textColor); });
  connect(base, &QPushButton::clicked, this, [this] { chooseColor("base", base); });
  connect(browse, &QPushButton::clicked, this, [this] {
    const QString path = QFileDialog::getOpenFileName(this, "Choose a boot screen picture", QStandardPaths::writableLocation(QStandardPaths::PicturesLocation), "Pictures (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)");
    if (path.isEmpty()) return;
    int index = pictures->findData(path);
    if (index < 0) { pictures->addItem(QFileInfo(path).fileName(), path); index = pictures->count()-1; }
    pictures->setCurrentIndex(index);
  });
  connect(apply, &QPushButton::clicked, this, [this] {
    if (previewReady) emit requested({{"action", "appearance-apply"}, {"options", settings},
      {"appearance_revision", revision}, {"background_sha", backgroundHash}});
  });
  connect(restore, &QPushButton::clicked, this, [this] { emit requested({{"action", "appearance-system"}, {"appearance_revision", revision}}); });
  connect(undo, &QPushButton::clicked, this, [this] { emit requested({{"action", "appearance-undo"}, {"appearance_revision", revision}}); });
  connect(catalog, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus exit) {
    const auto data = QJsonDocument::fromJson(catalog->readAllStandardOutput()).object();
    if (code || exit != QProcess::NormalExit || !data.contains("presets")) {
      caption->setText(data["error"].toString("Could not load the boot screen themes. Use Reload applied design to retry."));
      previewReady = false; updateActions(); return;
    }
    syncing = true; themes->clear(); pictures->clear(); pictures->addItem("Solid color", "");
    for (const auto &value : data["pictures"].toArray()) {
      const auto picture = value.toObject(); pictures->addItem(picture["name"].toString(), picture["path"].toString());
    }
    for (const auto &value : data["presets"].toArray()) {
      const auto preset = value.toObject();
      QPixmap art(preset["options"].toObject()["background"].toString());
      auto *item = new QListWidgetItem(QIcon(art.scaled(308, 160, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation)), preset["name"].toString(), themes);
      item->setData(Qt::UserRole, preset); item->setToolTip(preset["name"].toString());
    }
    active = data["active"].toBool(); canUndo = data["can_undo"].toBool() || active;
    revision = data["revision"].toString(); syncing = false;
    auto options = data["options"].toObject();
    if (options.isEmpty() && themes->count()) options = themes->item(0)->data(Qt::UserRole).toJsonObject()["options"].toObject();
    loadOptions(options);
  });
  connect(catalog, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { caption->setText("Could not start the theme reader."); updateActions(); }
  });
  connect(renderer, &QProcess::started, this, [this] {
    renderer->write(QJsonDocument(rendering).toJson(QJsonDocument::Compact)); renderer->closeWriteChannel();
  });
  connect(renderer, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus exit) {
    const auto data = QJsonDocument::fromJson(renderer->readAllStandardOutput()).object();
    if (renderingGeneration != generation) { debounce->start(); return; }
    QPixmap picture;
    previewReady = !code && exit == QProcess::NormalExit && picture.loadFromData(QByteArray::fromBase64(data["image"].toString().toLatin1()), "PNG");
    if (previewReady) {
      preview->image = picture; preview->update(); backgroundHash = data["background_sha"].toString();
      caption->setText("Preview · "+QString(menu.isEmpty() ? "Sample boot entries" : "Your current boot entries")+" · Firmware resolution can affect text spacing.");
    } else caption->setText(data["error"].toString("Could not preview this picture. Choose another image."));
    updateActions();
  });
  connect(renderer, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { caption->setText("Could not start the design preview."); previewReady = false; updateActions(); }
  });
  updateActions();
}

GrubAppearance::~GrubAppearance() {
  for (auto *process : {catalog, renderer}) if (process->state() != QProcess::NotRunning) { process->kill(); process->waitForFinished(1500); }
}
void GrubAppearance::showEvent(QShowEvent *event) {
  QWidget::showEvent(event); if (!loaded) { loaded = true; loadCatalog(); }
}
void GrubAppearance::resizeEvent(QResizeEvent *event) {
  QWidget::resizeEvent(event); const bool narrow = width() < 1050;
  body->setDirection(narrow ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
  controls->setMaximumWidth(narrow ? QWIDGETSIZE_MAX : 360); controls->setMaximumHeight(narrow ? 300 : QWIDGETSIZE_MAX);
  controls->setMinimumHeight(narrow ? 260 : 310);
}
void GrubAppearance::loadCatalog() {
  if (busy || catalog->state() != QProcess::NotRunning) return;
  previewReady = false; ++generation; caption->setText("Loading boot screen themes…"); updateActions();
  catalog->start("python3", {helper, "catalog"});
}
void GrubAppearance::loadOptions(const QJsonObject &value) {
  if (value.isEmpty()) return;
  syncing = true; settings = value;
  for (int i=0; i<themes->count(); ++i)
    if (themes->item(i)->data(Qt::UserRole).toJsonObject()["id"] == settings["preset"]) { themes->setCurrentRow(i); break; }
  const auto path = settings["background"].toString(); int picture = pictures->findData(path);
  if (picture < 0) { pictures->addItem("Applied picture · "+QFileInfo(path).fileName(), path); picture = pictures->count()-1; }
  pictures->setCurrentIndex(picture); position->setCurrentIndex(qMax(0, position->findData(settings["layout"].toString())));
  textSize->setCurrentIndex(qMax(0, textSize->findData(settings["size"].toInt(22))));
  heading->setText(settings["heading"].toString()); subtitle->setText(settings["subtitle"].toString());
  dimming->setValue(settings["dimming"].toInt()); contrast->setValue(settings["contrast"].toInt()); hints->setChecked(settings["hints"].toBool());
  colorButtons(); syncing = false; changed();
}
void GrubAppearance::changed() {
  if (syncing || settings.isEmpty()) return;
  settings["background"] = pictures->currentData().toString(); settings["layout"] = position->currentData().toString();
  settings["size"] = textSize->currentData().toInt(); settings["heading"] = heading->text(); settings["subtitle"] = subtitle->text();
  settings["dimming"] = dimming->value(); settings["contrast"] = contrast->value(); settings["hints"] = hints->isChecked();
  selection->setText((themes->currentItem() ? themes->currentItem()->text().toUpper() : "BOOT SCREEN")+"  /  PREVIEW");
  previewReady = false; ++generation; caption->setText("Updating preview…"); updateActions(); debounce->start();
}
void GrubAppearance::renderPreview() {
  if (settings.isEmpty() || renderer->state() != QProcess::NotRunning) return;
  rendering = {{"options", settings}, {"entries", menu}}; renderingGeneration = generation;
  renderer->start("python3", {helper, "preview"});
}
void GrubAppearance::chooseColor(const QString &key, QPushButton *) {
  const QColor color = QColorDialog::getColor(QColor(settings[key].toString()), this, "Choose "+key+" color");
  if (color.isValid()) { settings[key] = color.name(); colorButtons(); changed(); }
}
void GrubAppearance::colorButtons() {
  for (const auto &item : {qMakePair(accent, QString("accent")), qMakePair(textColor, QString("text")), qMakePair(base, QString("base"))}) {
    QPixmap swatch(18, 18); swatch.fill(QColor(settings[item.second].toString()));
    item.first->setIcon(QIcon(swatch)); item.first->setToolTip(settings[item.second].toString());
  }
}
void GrubAppearance::setMenu(const QJsonArray &entries) {
  QJsonArray names;
  for (const auto &value : entries) { const auto entry = value.toObject(); if (entry["parent_id"].toString().isEmpty()) names.append(entry["name"]); }
  if (menu != names) { menu = names; if (loaded) changed(); }
}
void GrubAppearance::setAvailability(bool working, bool available, bool hasMenu) {
  busy = working; supported = available; readable = hasMenu; updateActions();
}
void GrubAppearance::updateActions() {
  content->setEnabled(!busy); reload->setEnabled(!busy && catalog->state() == QProcess::NotRunning);
  apply->setEnabled(!busy && supported && readable && previewReady);
  restore->setEnabled(!busy && supported && readable && active);
  undo->setEnabled(!busy && supported && readable && canUndo);
  apply->setToolTip(readable ? "Save this design for your next restart" : "Load the current GRUB menu first");
}
void GrubAppearance::acceptResult(const QJsonObject &data) {
  revision = data["revision"].toString(); active = data["active"].toBool(); canUndo = data["can_undo"].toBool();
  if (!data["options"].toObject().isEmpty()) loadOptions(data["options"].toObject());
  updateActions();
}
