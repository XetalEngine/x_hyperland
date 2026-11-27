#pragma once
#include "account_avatar.h"
#include <QtWidgets>
#include <QCryptographicHash>

namespace FusionAccounts {
class Picker final : public QDialog {
public:
  explicit Picker(const QString &root, const QString &current, QWidget *parent=nullptr) : QDialog(parent), assets(root+"/account_avatars/assets") {
    setObjectName("accountAvatarPicker"); setWindowTitle(tr("Choose an account picture"));
    setModal(true); resize(900,720);
    auto *box=new QVBoxLayout(this); box->setContentsMargins(24,20,24,20); box->setSpacing(16);
    auto *heading=new QHBoxLayout; preview=new Avatar(this,96); heading->addWidget(preview);
    auto *words=new QVBoxLayout; title=new QLabel(tr("Make this account yours"));
    title->setObjectName("avatarChoiceName"); title->setTextFormat(Qt::PlainText);
    auto font=title->font();font.setPointSize(font.pointSize()+5);font.setBold(true);title->setFont(font);
    words->addWidget(title); count=new QLabel;count->setWordWrap(true);words->addWidget(count);
    words->addWidget(new QLabel(tr("Preview a picture, then choose Use this picture.")));
    heading->addLayout(words,1);box->addLayout(heading);
    auto *filters=new QHBoxLayout; search=new QLineEdit;search->setObjectName("avatarSearch");
    search->setPlaceholderText(tr("Search animals, space, music, hats…"));search->setClearButtonEnabled(true);
    search->setAccessibleName(tr("Search account pictures")); filters->addWidget(search,1);
    category=new QComboBox; category->setObjectName("avatarCategory");category->addItem(tr("All collections"),QString());
    category->setAccessibleName(tr("Avatar collection"));filters->addWidget(category);box->addLayout(filters);
    gallery=new QListWidget;gallery->setObjectName("avatarGallery");gallery->setViewMode(QListView::IconMode);
    gallery->setResizeMode(QListView::Adjust);gallery->setMovement(QListView::Static);
    gallery->setIconSize(QSize(76,76));gallery->setGridSize(QSize(122,116));gallery->setSpacing(5);
    gallery->setWordWrap(true);gallery->setSelectionMode(QAbstractItemView::SingleSelection);
    gallery->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);gallery->setAccessibleName(tr("Account pictures"));
    box->addWidget(gallery,1);
    empty=new QLabel(tr("No pictures match. Try another word or collection."));empty->setWordWrap(true);empty->hide();box->addWidget(empty);
    error=new QLabel;error->setTextFormat(Qt::PlainText);error->setWordWrap(true);error->hide();box->addWidget(error);
    auto *buttons=new QDialogButtonBox(QDialogButtonBox::Ok|QDialogButtonBox::Cancel);
    use=buttons->button(QDialogButtonBox::Ok);use->setText(tr("Use this picture"));use->setEnabled(false);
    box->addWidget(buttons);connect(buttons,&QDialogButtonBox::accepted,this,&Picker::confirm);
    connect(buttons,&QDialogButtonBox::rejected,this,&QDialog::reject);
    QFile catalog(assets+"/icons.json");
    const auto icons=catalog.open(QIODevice::ReadOnly)?QJsonDocument::fromJson(catalog.readAll()).object().value("icons").toArray():QJsonArray();
    QFile currentFile(current);const auto currentHash=currentFile.open(QIODevice::ReadOnly)
      ?QCryptographicHash::hash(currentFile.readAll(),QCryptographicHash::Sha256).toHex():QByteArray();
    QStringList collections; QListWidgetItem *selected=nullptr;
    for (const auto &value:icons) {
      const auto icon=value.toObject();const auto file=icon.value("file").toString();
      if (!QRegularExpression("^[a-z0-9-]+\\.(png|gif)$").match(file).hasMatch())continue;
      const auto path=assets+"/"+file; if (!QImageReader(path).canRead())continue;
      auto *item=new QListWidgetItem(QIcon(path),icon.value("name").toString(),gallery);
      item->setData(Qt::UserRole,icon);item->setToolTip(icon.value("name").toString()+" · "+icon.value("group").toString());
      collections<<icon.value("group").toString();
      if (QFileInfo(current).fileName()==file || (!currentHash.isEmpty()&&currentHash==icon.value("sha256").toString().toLatin1()) ||
          (selected==nullptr && icon.value("id")=="original"))selected=item;
    }
    collections.removeDuplicates();for(const auto &name:collections)category->addItem(name,name);
    count->setText(tr("%1 pictures · includes the original animated GIF").arg(gallery->count()));
    connect(gallery,&QListWidget::currentItemChanged,this,[this](QListWidgetItem *item){
      if(!item)return;const auto icon=item->data(Qt::UserRole).toJsonObject();
      title->setText(icon.value("name").toString());preview->setSource(assets+"/"+icon.value("file").toString());
      use->setEnabled(!item->isHidden());error->hide();
    });
    connect(gallery,&QListWidget::itemDoubleClicked,this,[this](QListWidgetItem *){confirm();});
    connect(search,&QLineEdit::textChanged,this,[this]{filter();});
    connect(category,&QComboBox::currentIndexChanged,this,[this]{filter();});
    if(selected)gallery->setCurrentItem(selected);
    if(!gallery->count()){error->setText(tr("The account-picture collection is unavailable."));error->show();}
    const auto area=screen()->availableGeometry(); resize(qMin(900,area.width()-60),qMin(720,area.height()-60));
  }
  QString selectedId() const {return choice;}
private:
  void filter() {
    const auto query=search->text().trimmed(); const auto group=category->currentData().toString();int visible=0;
    for(int i=0;i<gallery->count();++i){auto *item=gallery->item(i);const auto icon=item->data(Qt::UserRole).toJsonObject();
      const bool show=(group.isEmpty()||icon.value("group")==group)&&item->toolTip().contains(query,Qt::CaseInsensitive);
      item->setHidden(!show);visible+=show;
    }
    empty->setVisible(!visible);use->setEnabled(gallery->currentItem()&&!gallery->currentItem()->isHidden());
    count->setText(tr("%1 of %2 pictures").arg(visible).arg(gallery->count()));
  }
  void confirm() {
    auto *item=gallery->currentItem();if(!item||item->isHidden())return;
    const auto icon=item->data(Qt::UserRole).toJsonObject();QFile file(assets+"/"+icon.value("file").toString());
    if(QFileInfo(file).isSymLink()||!file.open(QIODevice::ReadOnly)||
       QCryptographicHash::hash(file.readAll(),QCryptographicHash::Sha256).toHex()!=icon.value("sha256").toString().toLatin1()){
      error->setText(tr("This picture could not be verified. Choose another picture."));error->show();return;
    }
    choice=icon.value("id").toString();accept();
  }
  QString assets,choice;Avatar *preview;QLabel *title,*count,*empty,*error;
  QLineEdit *search;QComboBox *category;QListWidget *gallery;QPushButton *use;
};
}
