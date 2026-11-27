#include "properties.h"
#include "appearance.h"
#include <KPropertiesDialog>
#include <KPageWidget>
#include <QApplication>
#include <QLayout>
#include <QTabBar>
#include <QScreen>

namespace Fusion {
namespace {
class PropertiesDialog final : public KPropertiesDialog {
public:
  PropertiesDialog(const KFileItemList &items, QWidget *parent) : KPropertiesDialog(items, parent) {
    auto *model = pageWidget()->model();
    connect(model, &QAbstractItemModel::rowsInserted, this, [this] { queueFit(); });
    connect(model, &QAbstractItemModel::modelReset, this, [this] { queueFit(); });
    connect(model, &QAbstractItemModel::dataChanged, this, [this] { queueFit(); });
  }
protected:
  void showEvent(QShowEvent *event) override {
    KPropertiesDialog::showEvent(event);
    queueFit();
  }
private:
  void queueFit() { QTimer::singleShot(0, this, [this] { fitTabs(); }); }
  void fitTabs() {
    if (!isVisible()) return;
    // Metadata plugins add Details asynchronously and KPageDialog rebuilds its
    // tab bar. Measure the current, laid-out bar rather than its old geometry.
    int missing = 0;
    for (auto *tabs : findChildren<QTabBar *>())
      if (tabs->isVisibleTo(this))
        missing = qMax(missing, tabs->sizeHint().width() - tabs->width());
    const int available = screen()->availableGeometry().width() - 40;
    if (missing > 0 && width() < available)
      resize(qMin(width() + missing, available), height());
  }
};
KFileItemList propertyItems(const QStringList &uris) {
  if (uris.isEmpty() || uris.size() > 10000) return {};
  KFileItemList items;
  QList<QUrl> seen;
  for (const auto &value : uris) {
    const QUrl url(value, QUrl::StrictMode);
    if (!url.isValid() || url.scheme().isEmpty() || value.contains(QChar::Null) ||
        (url.isLocalFile() && !QDir::isAbsolutePath(url.toLocalFile()))) return {};
    if (!seen.contains(url)) { seen << url; items << KFileItem(url); }
  }
  return items;
}
}
KPropertiesDialog *propertiesDialog(const KFileItemList &items, QWidget *parent) {
  auto *dialog = new PropertiesDialog(items, parent);
  dialog->setObjectName("fusionFileProperties");
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->ensurePolished();
  if (dialog->layout()) dialog->layout()->activate();
  dialog->adjustSize();
  return dialog;
}
bool openProperties(const QStringList &uris) {
  const auto items = propertyItems(uris);
  if (items.isEmpty()) return false;
  QStringList arguments{"--properties", "--"};
  for (const auto &item : items) arguments << item.url().toString(QUrl::FullyEncoded);
  return QProcess::startDetached(QCoreApplication::applicationFilePath(), arguments);
}
int runProperties(QApplication &app, const QStringList &uris) {
  const auto items = propertyItems(uris);
  if (items.isEmpty()) return 1;
  // A desktop dialog has no Files window as its transient parent. Give it a
  // distinct identity before mapping so it gets its own floating launch rule
  // and cannot inherit the file browser's saved geometry.
  app.setDesktopFileName("xetal-file-properties");
  Appearance appearance;
  QObject::connect(&appearance, &Appearance::initialized, &app, [&app, items] {
    auto *dialog = propertiesDialog(items);
    // This process contains only this dialog. Advertise its native dialog role
    // so the compositor keeps its title bar and its own dialog-size memory.
    dialog->setWindowModality(Qt::ApplicationModal);
    QObject::connect(dialog, &QObject::destroyed, &app, &QApplication::quit);
    dialog->show();
  });
  return app.exec();
}
}
