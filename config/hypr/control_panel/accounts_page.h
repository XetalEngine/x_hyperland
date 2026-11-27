#pragma once
#include "account_avatar.h"
#include <QtWidgets>
#include <unistd.h>

namespace FusionAccounts {
// Presentation only. Existing account actions still operate on the selected
// row of the backing table; no account is modified by selecting or searching.
class Page final : public QWidget {
public:
  explicit Page(const QString &profileRoot, QWidget *parent=nullptr) : QWidget(parent), root(profileRoot) {
    setObjectName("fusionAccountsPage");
    setAutoFillBackground(true);
    setStyleSheet("QFrame[accountCard=true] { background:palette(alternate-base); border:1px solid palette(mid); border-radius:14px; }"
      "QFrame[accountCard=true] QLabel { background:transparent; border:none; }"
      "QLabel[accountMuted=true] { color:palette(placeholder-text); }"
      "QListWidget#accountsList { border:none; background:transparent; }"
      "QListWidget#accountsList::item { padding:12px 10px; margin:3px 0; border-radius:10px; }"
      "QListWidget#accountsList::item:selected { background:palette(highlight); color:palette(highlighted-text); }");
    auto *layout=new QVBoxLayout(this); layout->setContentsMargins(18,18,18,18);layout->setSpacing(18);
    auto *top=new QHBoxLayout;auto *heading=new QVBoxLayout;
    heading->addWidget(label(tr("People on this computer"),true));
    heading->addWidget(label(tr("Give each account its own identity and access."),false,true));top->addLayout(heading,1);
    refresh=button(tr("Refresh"),"view-refresh");add=button(tr("Add account…"),"list-add");top->addWidget(refresh);top->addWidget(add);layout->addLayout(top);
    summary=label(QString(),false,true);summary->setObjectName("accountsSummary");layout->addWidget(summary);
    auto *split=new QSplitter;split->setChildrenCollapsible(false);layout->addWidget(split,1);
    auto *left=card();left->setMinimumWidth(240);auto *leftBox=new QVBoxLayout(left);leftBox->setContentsMargins(12,12,12,12);
    search=new QLineEdit;search->setPlaceholderText(tr("Find an account…"));search->setClearButtonEnabled(true);search->setAccessibleName(tr("Find an account"));leftBox->addWidget(search);
    list=new QListWidget;list->setObjectName("accountsList");list->setIconSize(QSize(52,52));list->setSpacing(3);leftBox->addWidget(list,1);
    empty=label(tr("No matching accounts"),false,true);empty->hide();leftBox->addWidget(empty);
    split->addWidget(left);
    auto *scroll=new QScrollArea;scroll->setWidgetResizable(true);scroll->setFrameShape(QFrame::NoFrame);split->addWidget(scroll);
    auto *content=new QWidget;scroll->setWidget(content);auto *details=new QVBoxLayout(content);details->setContentsMargins(12,0,0,0);details->setSpacing(16);
    auto *profile=card();auto *profileBox=new QHBoxLayout(profile);profileBox->setContentsMargins(24,24,24,24);
    avatar=new Avatar(profile,104);profileBox->addWidget(avatar);
    auto *identity=new QVBoxLayout;name=label(QString(),true);name->setObjectName("usersSelectedName");identity->addWidget(name);
    role=label(QString(),false,true);identity->addWidget(role);identity->addSpacing(8);
    icon=button(tr("Change picture…"),"avatar-default");icon->setObjectName("changeAccountPicture");icon->setToolTip(tr("Choose from all bundled account pictures"));identity->addWidget(icon,0,Qt::AlignLeft);
    profileBox->addSpacing(16);profileBox->addLayout(identity,1);details->addWidget(profile);
    auto *access=card();auto *accessBox=new QVBoxLayout(access);accessBox->setContentsMargins(22,20,22,20);accessBox->setSpacing(12);
    accessBox->addWidget(label(tr("Access & security"),true));
    accessHint=label(QString(),false,true);accessHint->setWordWrap(true);accessBox->addWidget(accessHint);
    groupNames=label(QString());groupNames->setWordWrap(true);groupNames->setTextInteractionFlags(Qt::TextSelectableByMouse);groupNames->setObjectName("accountGroups");accessBox->addWidget(groupNames);
    auto *actions=new QHBoxLayout;password=button(tr("Change password…"),"dialog-password");groups=button(tr("Edit groups…"),"system-users");actions->addWidget(password);actions->addWidget(groups);actions->addStretch();accessBox->addLayout(actions);details->addWidget(access);
    auto *location=card();auto *locationBox=new QVBoxLayout(location);locationBox->setContentsMargins(22,20,22,20);locationBox->setSpacing(12);
    locationBox->addWidget(label(tr("Account details"),true));
    home=label(QString());home->setWordWrap(true);home->setTextInteractionFlags(Qt::TextSelectableByMouse);locationBox->addWidget(home);
    shellText=label(QString(),false,true);shellText->setWordWrap(true);locationBox->addWidget(shellText);
    auto *advanced=new QHBoxLayout;shell=button(tr("Change login shell…"),"utilities-terminal");remove=button(tr("Delete account…"),"edit-delete");advanced->addWidget(shell);advanced->addStretch();advanced->addWidget(remove);locationBox->addLayout(advanced);details->addWidget(location);
    details->addStretch();status=label(QString(),false,true);status->setWordWrap(true);status->setObjectName("accountStatus");layout->addWidget(status);
    split->setStretchFactor(0,0);split->setStretchFactor(1,1);split->setSizes({290,760});
    table=new QTableWidget(this);table->setColumnCount(5);table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setSelectionMode(QAbstractItemView::SingleSelection);table->setEditTriggers(QAbstractItemView::NoEditTriggers);table->hide();
    connect(list,&QListWidget::currentItemChanged,this,[this](QListWidgetItem *item){if(item)table->selectRow(item->data(Qt::UserRole).toInt());selected();});
    connect(table,&QTableWidget::itemSelectionChanged,this,[this]{selected();});
    connect(search,&QLineEdit::textChanged,this,[this]{filter();});selected();
  }
  void rebuilt() {
    const auto selectedName=cell(table->currentRow(),0);QSignalBlocker block(list);list->clear();int administrators=0;QListWidgetItem *chosen=nullptr;
    for(int row=0;row<table->rowCount();++row){const auto uid=cell(row,1).toUInt();const bool admin=uid==0||cell(row,4).split(' ').contains("wheel");administrators+=admin;
      auto *item=new QListWidgetItem(table->item(row,0)->icon(),cell(row,0)+"\n"+
        (uid==getuid()?tr("Signed in · "):QString())+(uid==0?tr("System administrator"):admin?tr("Administrator"):tr("Standard account")),list);
      item->setData(Qt::UserRole,row);item->setData(Qt::UserRole+1,cell(row,0));item->setToolTip(cell(row,0));
      if(cell(row,0)==selectedName)chosen=item;
    }
    if(chosen)list->setCurrentItem(chosen);else if(list->count())list->setCurrentRow(0);
    summary->setText(tr("%1 accounts  ·  %2 administrators").arg(table->rowCount()).arg(administrators));
    if(list->currentItem())table->selectRow(list->currentItem()->data(Qt::UserRole).toInt());
    filter();selected();
  }
  QTableWidget *table;QPushButton *refresh,*add,*remove,*password,*shell,*groups,*icon;QLabel *status;
private:
  QString cell(int row,int column) const {auto *item=table->item(row,column);return item?item->text():QString();}
  QLabel *label(const QString &text,bool heading=false,bool muted=false){auto *value=new QLabel(text);value->setTextFormat(Qt::PlainText);
    if(heading){auto f=value->font();f.setPointSize(f.pointSize()+3);f.setBold(true);value->setFont(f);}
    value->setProperty("accountMuted",muted);return value;}
  QFrame *card(){auto *frame=new QFrame;frame->setProperty("accountCard",true);return frame;}
  QPushButton *button(const QString &title,const QString &image){return new QPushButton(QIcon::fromTheme(image),title);}
  void filter(){int visible=0;for(int i=0;i<list->count();++i){auto *item=list->item(i);bool show=item->text().contains(search->text().trimmed(),Qt::CaseInsensitive);item->setHidden(!show);visible+=show;}empty->setVisible(!visible);}
  void selected(){int row=table->currentRow();const bool valid=row>=0&&!cell(row,0).isEmpty();
    for(auto *action:{remove,password,shell,groups,icon})action->setEnabled(valid);
    if(!valid){name->setText(tr("Select an account"));role->clear();home->clear();shellText->clear();groupNames->clear();avatar->setSource({});return;}
    const auto user=cell(row,0),directory=cell(row,2);const auto uid=cell(row,1).toUInt();const bool current=uid==getuid();
    const bool admin=uid==0||cell(row,4).split(' ').contains("wheel");name->setText(user);
    role->setText((current?tr("Signed in · "):QString())+(uid==0?tr("System administrator"):admin?tr("Administrator"):tr("Standard account")));
    avatar->setProperty("initial",user.left(1).toUpper());avatar->setSource(avatarPath(user,directory,root,current));avatar->update();
    accessHint->setText(admin?tr("This account can administer the computer."):tr("This account uses the permissions granted by its groups."));
    groupNames->setText(tr("Groups  ·  %1").arg(cell(row,4).split(' ',Qt::SkipEmptyParts).join("   ·   ")));
    home->setText(tr("Home folder  ·  %1").arg(directory));shellText->setText(tr("Login shell  ·  %1\nAccount ID  ·  %2").arg(cell(row,3),cell(row,1)));
    remove->setEnabled(!current&&uid!=0);remove->setToolTip(current?tr("You cannot delete your signed-in account."):uid==0?tr("The system administrator account is protected."):QString());
  }
  QString root;QListWidget *list;QLineEdit *search;Avatar *avatar;QLabel *name,*role,*home,*shellText,*groupNames,*accessHint,*summary,*empty;
};
}
