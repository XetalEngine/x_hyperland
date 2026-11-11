#include "page.h"
#include "credentials.h"
#include "view.h"
#include <QFileDialog>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QMessageBox>
#include <QScrollArea>
#include <QSignalBlocker>
#include <QSplitter>
#include <QToolButton>
#include <QUuid>
#include <QVBoxLayout>

namespace FusionRdp {
Page::Page(const QString &root, QWidget *parent, SessionOpener openSession)
    : QWidget(parent), store(root + "/control_panel/state/rdp/connections.json"), opener(std::move(openSession)) {
    setObjectName("rdpTab");
    if (!opener) opener = [](const Profile &p, const QString &password) {
        auto *window = new SessionWindow(p, password); window->showSession();
    };
    auto *layout = new QVBoxLayout(this); layout->setContentsMargins(12, 12, 12, 12); layout->setSpacing(14);
    auto *heading = new QLabel("RDP · Remote Desktop", this); heading->setObjectName("panelTitle"); layout->addWidget(heading);
    auto *intro = new QLabel("Connect to your PCs. Save a connection and pick up where you left off.", this);
    intro->setWordWrap(true); layout->addWidget(intro);
    auto *splitter = new QSplitter(Qt::Horizontal, this); layout->addWidget(splitter, 1);
    auto *sidebar = new QWidget(splitter); sidebar->setMinimumWidth(200); sidebar->setMaximumWidth(360);
    auto *listLayout = new QVBoxLayout(sidebar); listLayout->setContentsMargins(0,0,12,0);
    filter = new QLineEdit(sidebar); filter->setObjectName("rdpSearch"); filter->setPlaceholderText("Find a saved PC…"); filter->setClearButtonEnabled(true);
    listLayout->addWidget(filter);
    connections = new QListWidget(sidebar); connections->setObjectName("rdpConnections"); connections->setMinimumHeight(260);
    connections->setSpacing(5); listLayout->addWidget(connections, 1);
    auto *listActions = new QHBoxLayout;
    create = new QPushButton("New connection", sidebar); create->setObjectName("rdpNew");
    remove = new QPushButton("Delete", sidebar); remove->setObjectName("rdpDelete");
    listActions->addWidget(create, 1); listActions->addWidget(remove); listLayout->addLayout(listActions);
    auto *editor = editorWidget = new QWidget(splitter); editor->setMinimumWidth(440);
    auto *editorLayout = new QVBoxLayout(editor); editorLayout->setContentsMargins(12,0,0,0); editorLayout->setSpacing(12);
    auto *form = new QFormLayout; form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    auto field = [&](const char *id, const QString &hint) {
        auto *input = new QLineEdit(editor); input->setObjectName(id); input->setPlaceholderText(hint);
        connect(input, &QLineEdit::textEdited, this, [this] { if (!loading) dirty = true; });
        return input;
    };
    name = field("rdpName", "Office PC"); form->addRow("Connection name", name);
    host = field("rdpHost", "Hostname or IP address");
    port = new QSpinBox(editor); port->setObjectName("rdpPort"); port->setRange(1,65535); port->setValue(3389);
    auto *address = new QHBoxLayout; address->addWidget(host, 1); address->addWidget(new QLabel("Port", editor)); address->addWidget(port);
    form->addRow("PC address", address);
    username = field("rdpUsername", "Username, DOMAIN\\user, or email"); form->addRow("Username", username);
    domain = field("rdpDomain", "Optional"); form->addRow("Domain", domain);
    password = field("rdpPassword", "Password"); password->setEchoMode(QLineEdit::Password);
    auto *reveal = new QToolButton(editor); reveal->setText("Show"); reveal->setCheckable(true); reveal->setObjectName("rdpShowPassword");
    connect(reveal, &QToolButton::toggled, this, [this, reveal](bool checked) {
        password->setEchoMode(checked ? QLineEdit::Normal : QLineEdit::Password); reveal->setText(checked ? "Hide" : "Show");
    });
    auto *passwordRow = new QHBoxLayout; passwordRow->addWidget(password, 1); passwordRow->addWidget(reveal);
    form->addRow("Password", passwordRow);
    remember = new QCheckBox("Remember password in the system wallet", editor); remember->setObjectName("rdpRemember"); remember->setChecked(true);
    form->addRow({}, remember); editorLayout->addLayout(form);

    auto *sharing = new QGroupBox("Shared folder", editor); auto *sharingLayout = new QVBoxLayout(sharing);
    shareFolder = new QCheckBox("Share a folder with the remote PC", sharing); shareFolder->setObjectName("rdpShareFolder");
    sharingLayout->addWidget(shareFolder);
    sharedFolder = field("rdpSharedPath", QDir::homePath());
    auto *browse = new QPushButton("Browse…", sharing); auto *folderRow = new QHBoxLayout;
    folderRow->addWidget(sharedFolder, 1); folderRow->addWidget(browse); sharingLayout->addLayout(folderRow);
    auto *folderNote = new QLabel("Your home folder is shared as Home on HyperFusion (\\\\tsclient\\Home). The remote PC can read and change its files.", sharing);
    folderNote->setWordWrap(true); folderNote->setObjectName("muted"); sharingLayout->addWidget(folderNote);
    connect(browse, &QPushButton::clicked, this, [this] {
        const auto path = QFileDialog::getExistingDirectory(this, "Shared folder", sharedFolder->text());
        if (!path.isEmpty()) { sharedFolder->setText(path); dirty = true; }
    });
    connect(shareFolder, &QCheckBox::toggled, this, [this, browse](bool enabled) { sharedFolder->setEnabled(enabled); browse->setEnabled(enabled); });
    editorLayout->addWidget(sharing);
    auto *options = new QGroupBox("Connection options", editor); auto *optionsLayout = new QGridLayout(options);
    auto check = [&](const char *id, const QString &title, int row, int col) {
        auto *box = new QCheckBox(title, options); box->setObjectName(id); optionsLayout->addWidget(box, row, col); return box;
    };
    clipboard = check("rdpClipboard", "Share clipboard (text and images)", 0, 0);
    sound = check("rdpSound", "Play remote audio", 0, 1);
    microphone = check("rdpMicrophone", "Share microphone", 1, 0);
    printers = check("rdpPrinters", "Share local printers", 1, 1);
    dynamicResolution = check("rdpDynamicResolution", "Resize desktop with window", 2, 0);
    reconnect = check("rdpReconnect", "Reconnect if interrupted", 2, 1);
    autoAcceptCertificate = check("rdpAutoCertificate", "Automatically accept certificates", 3, 0);
    autoAcceptCertificate->setToolTip("Accepts unverified or changed server certificates. Turn off to require a trusted certificate.");
    fullscreen = check("rdpStartFullscreen", "Start in full screen", 3, 1);
    adminSession = check("rdpAdminSession", "Administrative session", 4, 0);
    adminSession->setToolTip("Connect to the server's administration session when supported.");
    editorLayout->addWidget(options);
    auto *advancedToggle = new QToolButton(editor); advancedToggle->setText("Gateway and keyboard");
    advancedToggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); advancedToggle->setArrowType(Qt::RightArrow); advancedToggle->setCheckable(true);
    editorLayout->addWidget(advancedToggle);
    auto *advanced = new QWidget(editor); auto *advancedForm = new QFormLayout(advanced); advancedForm->setContentsMargins(0,0,0,0);
    gateway = field("rdpGateway", "Optional · gateway.example.com:443 (same account)"); advancedForm->addRow("RD Gateway", gateway);
    keyboard = new QComboBox(editor); keyboard->setObjectName("rdpKeyboard");
    for (const auto &entry : QList<QPair<QString, quint32>>{{"English (US)",0x409},{"English (UK)",0x809},
        {"Spanish",0x40a},{"Latin American",0x80a},{"French",0x40c},{"German",0x407},
        {"Portuguese (Brazil)",0x416},{"Portuguese",0x816},{"Italian",0x410},{"Japanese",0x411},{"Russian",0x419}})
        keyboard->addItem(entry.first, entry.second);
    advancedForm->addRow("Keyboard layout", keyboard); advanced->hide(); editorLayout->addWidget(advanced);
    connect(advancedToggle, &QToolButton::toggled, this, [advanced, advancedToggle](bool visible) {
        advanced->setVisible(visible); advancedToggle->setArrowType(visible ? Qt::DownArrow : Qt::RightArrow);
    });
    auto *hint = new QLabel("In a session, move to the top edge for controls. Ctrl+Alt+Shift+F switches full screen; Ctrl+Alt+Shift+Home reveals the toolbar.", editor);
    hint->setWordWrap(true); hint->setObjectName("muted"); editorLayout->addWidget(hint);
    status = new QLabel(editor); status->setObjectName("rdpStatus"); status->setTextFormat(Qt::PlainText); status->setWordWrap(true); editorLayout->addWidget(status);
    auto *actions = new QHBoxLayout; actions->addStretch();
    save = new QPushButton("Save connection", editor); save->setObjectName("rdpSave");
    connectButton = new QPushButton("Connect", editor); connectButton->setObjectName("rdpConnect");
    actions->addWidget(save); actions->addWidget(connectButton); editorLayout->addLayout(actions); editorLayout->addStretch();
    splitter->addWidget(sidebar); splitter->addWidget(editor); splitter->setStretchFactor(1,1); splitter->setSizes({240,800});
    connect(create, &QPushButton::clicked, this, &Page::newConnection);
    connect(save, &QPushButton::clicked, this, [this] { persist(false); });
    connect(connectButton, &QPushButton::clicked, this, [this] { persist(true); });
    connect(remove, &QPushButton::clicked, this, &Page::removeConnection);
    connect(filter, &QLineEdit::textChanged, this, [this](const QString &text) {
        for (int i=0; i<connections->count(); ++i) connections->item(i)->setHidden(!connections->item(i)->text().contains(text, Qt::CaseInsensitive));
    });
    connect(connections, &QListWidget::currentItemChanged, this, [this](QListWidgetItem *item, QListWidgetItem *previous) {
        if (loading || !item || busy) return;
        if (dirty && QMessageBox::question(this, "Unsaved connection", "Discard the unsaved changes to this connection?", QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Discard) {
            QSignalBlocker block(connections); connections->setCurrentItem(previous); return;
        }
        for (const auto &p : profiles) if (p.id == item->data(Qt::UserRole).toString()) { load(p); break; }
    });
    for (auto *field : {host, username, domain, gateway}) connect(field, &QLineEdit::textChanged, this, &Page::clearStalePassword);
    connect(port, &QSpinBox::valueChanged, this, [this] { clearStalePassword(); if (!loading) dirty = true; });
    connect(password, &QLineEdit::textEdited, this, [this] {
        passwordIdentity.clear(); ++lookupGeneration; lookupPending = false; updateActions();
    });
    connect(remember, &QCheckBox::toggled, this, [this](bool enabled) {
        if (!loading && !enabled) { ++lookupGeneration; lookupPending = false; updateActions(); }
    });
    for (auto *box : {remember, shareFolder, clipboard, sound, microphone, printers, dynamicResolution, autoAcceptCertificate, reconnect, fullscreen, adminSession})
        connect(box, &QCheckBox::toggled, this, [this] { if (!loading) dirty = true; });
    connect(keyboard, &QComboBox::currentIndexChanged, this, [this] { if (!loading) dirty = true; });
    refresh(); newConnection();
}
Profile Page::draft() const {
    Profile p; p.id = currentId; p.name = name->text().trimmed(); p.host = host->text().trimmed(); p.port = port->value();
    p.username = username->text().trimmed(); p.domain = domain->text().trimmed(); p.sharedFolder = sharedFolder->text();
    if (p.sharedFolder == "~") p.sharedFolder = QDir::homePath();
    else if (p.sharedFolder.startsWith("~/")) p.sharedFolder = QDir::homePath() + p.sharedFolder.mid(1);
    p.gateway = gateway->text().trimmed(); p.rememberPassword = remember->isChecked();
    p.shareFolder = shareFolder->isChecked(); p.clipboard = clipboard->isChecked(); p.sound = sound->isChecked();
    p.microphone = microphone->isChecked(); p.printers = printers->isChecked(); p.dynamicResolution = dynamicResolution->isChecked();
    p.autoAcceptCertificate = autoAcceptCertificate->isChecked(); p.reconnect = reconnect->isChecked();
    p.fullscreen = fullscreen->isChecked(); p.adminSession = adminSession->isChecked(); p.keyboardLayout = keyboard->currentData().toUInt();
    return p;
}
void Page::say(const QString &text, bool error) {
    status->setText(text); status->setProperty("error", error);
    status->setStyleSheet(error ? "color: #e6a16c;" : QString());
}
void Page::setBusy(bool value) {
    busy = value; editorWidget->setEnabled(!value); create->setEnabled(!value);
    connections->setEnabled(!value); updateActions();
}
void Page::updateActions() {
    save->setEnabled(!busy && !lookupPending); connectButton->setEnabled(!busy && !lookupPending);
    remove->setEnabled(!busy && connections->currentItem());
}
void Page::refresh(const QString &select) {
    QString error; auto next = store.load(&error);
    if (!error.isEmpty()) { say(error, true); return; }
    profiles = next; QSignalBlocker block(connections); connections->clear();
    for (const auto &p : profiles) {
        auto *item = new QListWidgetItem(QIcon::fromTheme("computer"), p.name + "\n" + p.username + " @ " + p.host, connections);
        item->setData(Qt::UserRole, p.id); item->setToolTip(p.host + ':' + QString::number(p.port));
        item->setHidden(!item->text().contains(filter->text(), Qt::CaseInsensitive));
        if (p.id == select) connections->setCurrentItem(item);
    }
    remove->setEnabled(!busy && connections->currentItem());
}
void Page::load(const Profile &p) {
    loading = true; ++lookupGeneration; lookupPending = false; currentId = p.id; passwordIdentity.clear(); password->clear();
    password->setEchoMode(QLineEdit::Password); findChild<QToolButton *>("rdpShowPassword")->setChecked(false);
    name->setText(p.name); host->setText(p.host); port->setValue(p.port); username->setText(p.username); domain->setText(p.domain);
    sharedFolder->setText(p.sharedFolder); gateway->setText(p.gateway); remember->setChecked(p.rememberPassword);
    shareFolder->setChecked(p.shareFolder); clipboard->setChecked(p.clipboard); sound->setChecked(p.sound);
    microphone->setChecked(p.microphone); printers->setChecked(p.printers); dynamicResolution->setChecked(p.dynamicResolution);
    autoAcceptCertificate->setChecked(p.autoAcceptCertificate); reconnect->setChecked(p.reconnect);
    fullscreen->setChecked(p.fullscreen); adminSession->setChecked(p.adminSession);
    keyboard->setCurrentIndex(qMax(0, keyboard->findData(p.keyboardLayout)));
    loading = false; dirty = false; say({}); updateActions();
    if (p.host.isEmpty() || !p.rememberPassword) return;
    const auto generation = lookupGeneration; const auto identity = p.credentialKey();
    lookupPending = true; updateActions(); say("Loading password from the system wallet…");
    auto *job = new CredentialJob(this);
    connect(job, &CredentialJob::completed, this, [this, job, generation, identity](bool ok, const QString &secret, const QString &error) {
        job->deleteLater();
        if (generation != lookupGeneration || draft().credentialKey() != identity || !remember->isChecked()) return;
        lookupPending = false; updateActions();
        if (ok) { password->setText(secret); passwordIdentity = identity; say(secret.isEmpty() ? "Enter the password to connect." : "Password loaded from the system wallet."); }
        else say(error, true);
    });
    job->start(CredentialJob::Lookup, p);
}
void Page::newConnection() {
    if (dirty && QMessageBox::question(this, "Unsaved connection", "Discard the unsaved changes and create a new connection?", QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Discard) return;
    { QSignalBlocker block(connections); connections->setCurrentRow(-1); }
    Profile p; p.id = QUuid::createUuid().toString(QUuid::WithoutBraces); load(p); name->setFocus();
}
void Page::clearStalePassword() {
    if (loading) return;
    ++lookupGeneration; lookupPending = false; updateActions();
    if (!passwordIdentity.isEmpty() && passwordIdentity != draft().credentialKey()) {
        password->clear(); passwordIdentity.clear(); say("The PC or account changed. Enter its password.");
    }
}
void Page::persist(bool connectNow) {
    if (busy || lookupPending) return;
    auto p = draft(); QString error;
    if (!store.save(p, &error)) { say(error, true); return; }
    const auto secret = password->text();
    const auto previous = std::find_if(profiles.begin(), profiles.end(), [&](const Profile &old) { return old.id == p.id; });
    const auto old = previous != profiles.end() ? *previous : p;
    ++lookupGeneration; dirty = false; refresh(p.id); setBusy(true); say("Saving connection…");
    auto finish = [this, p, old, secret, connectNow](bool ok, const QString &error) {
        setBusy(false); say(ok ? "Connection saved." : "Connection saved. " + error, !ok);
        if (ok && p.rememberPassword && !secret.isEmpty()) passwordIdentity = p.credentialKey();
        if (old.credentialKey() != p.credentialKey()) {
            auto *cleanup = new CredentialJob(this);
            connect(cleanup, &CredentialJob::completed, this, [this, cleanup](bool removed, const QString &, const QString &why) {
                cleanup->deleteLater(); if (!removed) say("The connection was saved, but its previous wallet entry could not be removed. " + why, true);
            });
            cleanup->start(CredentialJob::Forget, old);
        }
        if (connectNow) opener(p, secret);
    };
    auto *job = new CredentialJob(this);
    connect(job, &CredentialJob::completed, this, [job, finish](bool ok, const QString &, const QString &error) { job->deleteLater(); finish(ok, error); });
    job->start(p.rememberPassword && !secret.isEmpty() ? CredentialJob::Store : CredentialJob::Forget, p, secret);
}
void Page::removeConnection() {
    if (busy || !connections->currentItem()) return;
    auto item = std::find_if(profiles.begin(), profiles.end(), [&](const Profile &p) { return p.id == currentId; });
    if (item == profiles.end()) return;
    const auto p = *item;
    if (QMessageBox::question(this, "Delete saved connection", "Delete “" + p.name + "” and its saved password?", QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
    setBusy(true); auto *job = new CredentialJob(this);
    connect(job, &CredentialJob::completed, this, [this, job, p](bool ok, const QString &, const QString &why) {
        job->deleteLater(); setBusy(false);
        if (!ok) { say("The password could not be removed. The connection was kept so you can try again. " + why, true); return; }
        QString error; if (!store.remove(p.id, &error)) { say(error, true); return; }
        dirty = false; refresh(); newConnection(); say("Connection deleted.");
    });
    job->start(CredentialJob::Forget, p);
}
}
