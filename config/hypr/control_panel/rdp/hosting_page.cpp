#include "hosting_page.h"
#include <QtWidgets>
#include <utility>

namespace FusionRdp {
namespace {
QLabel *label(const QString &value, const char *name, QWidget *parent) {
    auto *item = new QLabel(value, parent);
    item->setObjectName(name); item->setTextFormat(Qt::PlainText); item->setWordWrap(true);
    item->setTextInteractionFlags(Qt::TextSelectableByMouse);
    item->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    return item;
}
void choose(QComboBox *combo, const QString &value, const QString &suffix) {
    if (combo->findData(value) < 0) combo->addItem(value + suffix, value);
    combo->setCurrentIndex(combo->findData(value));
}
}

HostingPage::HostingPage(const QString &root, QWidget *parent) : QWidget(parent), root(root) {
    setObjectName("rdpHostingPage");
    auto *body = new QVBoxLayout(this); body->setContentsMargins(0, 12, 0, 0); body->setSpacing(12);
    auto *heading = new QHBoxLayout;
    state = label("Sharing is off", "rdpHostState", this); state->setStyleSheet("font-weight:600;font-size:18px;");
    heading->addWidget(state, 1);
    refresh = new QPushButton("Refresh devices", this); refresh->setObjectName("rdpHostRefresh"); heading->addWidget(refresh);
    body->addLayout(heading);
    body->addWidget(label("Share a monitor from your active Hyper Fusion session. Choose RDP for Windows Remote Desktop or VNC for encrypted desktop sharing.", "muted", this));

    auto *row = new QHBoxLayout; row->setSpacing(16);
    setup = new QGroupBox("Sharing settings", this);
    auto *form = new QFormLayout(setup); form->setSpacing(10); form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    auto combo = [&](const char *name) {
        auto *field = new QComboBox(setup); field->setObjectName(name);
        field->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon); field->setMinimumContentsLength(12);
        return field;
    };
    protocol = combo("rdpHostProtocol");
    protocol->addItem("RDP · Windows Remote Desktop", "rdp"); protocol->addItem("VNC · encrypted desktop sharing", "vnc");
    output = combo("rdpHostOutput"); address = combo("rdpHostAddress");
    port = new QSpinBox(setup); port->setObjectName("rdpHostPort"); port->setRange(1024, 65535);
    username = new QLineEdit(setup); username->setObjectName("rdpHostUsername"); username->setMaxLength(64);
    password = new QLineEdit(setup); password->setObjectName("rdpHostPassword"); password->setEchoMode(QLineEdit::Password); password->setMaxLength(256);
    password->setPlaceholderText("12+ characters · blank keeps saved password");
    fps = new QSpinBox(setup); fps->setObjectName("rdpHostFps"); fps->setRange(5, 60); fps->setSuffix(" fps");
    control = new QCheckBox("Allow keyboard and mouse control", setup); control->setObjectName("rdpHostControl");
    automatic = new QCheckBox("Start sharing after I sign in", setup); automatic->setObjectName("rdpHostAutostart");
    form->addRow("Protocol", protocol); form->addRow("Monitor", output);
    auto *endpoint = new QHBoxLayout; endpoint->addWidget(address, 1); endpoint->addWidget(new QLabel("Port", setup)); endpoint->addWidget(port);
    form->addRow("Listen on", endpoint); form->addRow("Username", username); form->addRow("Password", password);
    form->addRow("Frame limit", fps); form->addRow({}, control); form->addRow({}, automatic);
    row->addWidget(setup, 3);

    auto *details = new QGroupBox("Connect from another computer", this); auto *info = new QVBoxLayout(details); info->setSpacing(12);
    connection = label("Choose a network address to share with devices on your network.", "rdpHostConnection", details);
    connection->setStyleSheet("font-weight:600;"); info->addWidget(connection);
    info->addWidget(label("Local computer only works through an SSH tunnel. Select your LAN address for other computers on that network.", "muted", details));
    info->addWidget(label("Use the sharing username and password. Verify this certificate fingerprint when your client asks to trust the computer.", "muted", details));
    fingerprint = label("A certificate is created when you first start sharing.", "rdpHostFingerprint", details);
    info->addWidget(fingerprint); info->addStretch();
    hint = label({}, "rdpHostHint", details); info->addWidget(hint); row->addWidget(details, 2); body->addLayout(row);

    log = new QPlainTextEdit(this); log->setObjectName("rdpHostLog"); log->setReadOnly(true);
    log->setPlaceholderText("Connection details and component errors appear here."); log->setMinimumHeight(75); log->setMaximumHeight(140);
    body->addWidget(log);
    message = label({}, "rdpHostMessage", this); body->addWidget(message);
    body->addStretch(); auto *actions = new QHBoxLayout;
    install = new QPushButton("Install component", this); install->setObjectName("rdpHostInstall"); actions->addWidget(install); actions->addStretch();
    save = new QPushButton("Save settings", this); save->setObjectName("rdpHostSave"); actions->addWidget(save);
    stop = new QPushButton("Stop sharing", this); stop->setObjectName("rdpHostStop"); actions->addWidget(stop);
    start = new QPushButton("Start sharing", this); start->setObjectName("rdpHostStart"); actions->addWidget(start); body->addLayout(actions);
    start->setStyleSheet("QPushButton:enabled {background:palette(highlight);color:palette(highlighted-text);font-weight:600;}");

    process = new QProcess(this); process->setObjectName("rdpHostProcess");
    poll = new QTimer(this); poll->setObjectName("rdpHostPoll"); poll->setInterval(2500);
    deadline = new QTimer(this); deadline->setSingleShot(true);
    connect(poll, &QTimer::timeout, this, [this] { if (isVisible() && !busy) request(loaded ? "status" : "refresh"); });
    connect(refresh, &QPushButton::clicked, this, [this] { request("refresh"); });
    connect(save, &QPushButton::clicked, this, [this] { request("save"); });
    connect(start, &QPushButton::clicked, this, [this] { request("start"); });
    connect(stop, &QPushButton::clicked, this, [this] { request("stop"); });
    connect(install, &QPushButton::clicked, this, [this] { request("install"); });
    connect(protocol, &QComboBox::currentIndexChanged, this, [this] { protocolChanged(); });
    connect(address, &QComboBox::currentIndexChanged, this, &HostingPage::addressChanged);
    connect(port, &QSpinBox::valueChanged, this, &HostingPage::addressChanged);
    connect(password, &QLineEdit::textChanged, this, [this] { updateActions(); });
    connect(process, &QProcess::readyReadStandardOutput, this, [this] {
        const auto bytes = process->readAllStandardOutput();
        if (response.size() + bytes.size() <= 262144) response += bytes;
        else responseTooLarge = true;
    });
    // Only the structured reply reaches the UI; never render a helper traceback.
    connect(process, &QProcess::readyReadStandardError, this, [this] { process->readAllStandardError(); });
    connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) { finished(code); });
    connect(process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) { if (error == QProcess::FailedToStart) finished(-1); });
    connect(deadline, &QTimer::timeout, this, [this] {
        if (action == "refresh" || action == "status") process->kill();
        else message->setText("Waiting for authentication or the remote desktop component to finish…");
    });
    updateActions();
}

HostingPage::~HostingPage() {
    if (process->state() == QProcess::NotRunning) return;
    process->disconnect(this);
    if (action == "refresh" || action == "status") {
        process->kill(); process->waitForFinished(1000);
    } else {
        // A page change must not interrupt an authenticated install or server start.
        process->setParent(QCoreApplication::instance());
        connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), process, &QObject::deleteLater);
    }
}

QJsonObject HostingPage::values() const {
    return {{"version", 1}, {"protocol", protocol->currentData().toString()}, {"output", output->currentData().toString()},
            {"address", address->currentData().toString()}, {"port", port->value()}, {"username", username->text().trimmed()},
            {"fps", fps->value()}, {"control", control->isChecked()}, {"autostart", automatic->isChecked()}};
}

void HostingPage::request(const QString &operation) {
    if (busy) {
        // Polling is invisible to interaction. Queue a user action behind the
        // read, rather than flashing disabled controls or dropping the click.
        if ((action == "status" || action == "refresh") && operation != "status" && operation != "refresh" && pendingAction.isEmpty()) {
            pendingAction = operation; operationMessage(operation); updateActions();
        }
        return;
    }
    if ((operation == "start" || operation == "save") && !passwordValid()) {
        failed = true; message->setStyleSheet("color:#e6a16c;font-weight:600;");
        message->setText("Enter a sharing password of 12–256 characters, with no line breaks or spaces at the beginning or end.");
        password->setFocus(); updateActions(); return;
    }
    action = operation; busy = true; response.clear(); responseTooLarge = false;
    QJsonObject payload;
    if (action == "start" || action == "save") payload = {{"values", values()}, {"password", password->text()}};
    if (action == "install") payload = {{"protocol", protocol->currentData().toString()}};
    operationMessage(action);
    updateActions();
    process->start("/usr/bin/python3", {"-I", root + "/desktop_services/remote_cli.py", action});
    process->write(QJsonDocument(payload).toJson(QJsonDocument::Compact)); process->closeWriteChannel();
    deadline->start(action == "install" ? 60000 : 30000);
}

void HostingPage::finished(int code) {
    if (!busy) return;
    deadline->stop(); busy = false;
    // Always run a queued user action after this read completes, even if the
    // read failed. Do not let another timer callback take its place.
    const auto queued = std::exchange(pendingAction, QString());
    if (!queued.isEmpty()) QTimer::singleShot(0, this, [this, queued] { request(queued); });
    QJsonParseError error; const auto document = QJsonDocument::fromJson(response, &error);
    if (responseTooLarge || error.error != QJsonParseError::NoError || !document.isObject()) {
        message->setText("Unable to read remote desktop status. Check that the desktop components are installed, then refresh.");
        message->setStyleSheet("color:#e6a16c;font-weight:600;");
        updateActions(); return;
    }
    const auto result = document.object();
    if (result.contains("has_password")) hasPassword = result["has_password"].toBool();
    if (result.contains("status")) display(result);
    if (code != 0 || !result["ok"].toBool()) {
        failed = true; message->setStyleSheet("color:#e6a16c;font-weight:600;");
        if (action == "start") state->setText("Sharing failed to start");
        message->setText(result["error"].toString("The remote desktop operation could not finish.")); updateActions(); return;
    }
    if (action == "refresh") { populate(result); if (message->text().startsWith("Unable to read")) message->clear(); }
    if (action == "save" || action == "start") password->clear();
    if (action == "save") message->setText("Saved. Active sharing keeps its current settings until you stop and start it again.");
    if (action == "start") message->setText("Sharing started. Waiting for a remote connection. Stop sharing disconnects viewers.");
    if (action == "stop") message->setText("Sharing stopped.");
    if (action == "install") message->setText("Component ready. Sharing stays off until you start it.");
    updateActions();
}

void HostingPage::populate(const QJsonObject &result) {
    const auto saved = result["preferences"].toObject();
    const QString selectedOutput = loaded ? output->currentData().toString() : saved["output"].toString();
    const QString selectedAddress = loaded ? address->currentData().toString() : saved["address"].toString();
    const QSignalBlocker outputGuard(output), addressGuard(address), protocolGuard(protocol);
    output->clear(); output->addItem("Current monitor", "");
    for (const auto &item : result["monitors"].toArray()) {
        const auto screen = item.toObject(); const auto name = screen["name"].toString();
        output->addItem(name + " · " + screen["description"].toString(), name);
    }
    choose(output, selectedOutput, " · disconnected");
    address->clear();
    for (const auto &item : result["addresses"].toArray()) {
        const auto value = item.toString(); address->addItem(value == "127.0.0.1" ? "Local computer only" : value, value);
    }
    choose(address, selectedAddress, " · unavailable");
    if (!loaded) {
        protocol->setCurrentIndex(protocol->findData(saved["protocol"].toString()));
        port->setValue(saved["port"].toInt()); username->setText(saved["username"].toString()); fps->setValue(saved["fps"].toInt(30));
        control->setChecked(saved["control"].toBool()); automatic->setChecked(saved["autostart"].toBool()); loaded = true;
    }
    protocolChanged(false);
}

void HostingPage::display(const QJsonObject &result) {
    components = result["components"].toObject();
    const bool wasRunning = running;
    const auto snapshot = result["status"].toObject(); running = snapshot["running"].toBool();
    const auto current = snapshot["process"].toObject();
    if (running && !current.isEmpty()) {
        const int clients = snapshot["connections"].toInt();
        const auto phase = clients > 0 ? QString("%1 remote connection%2").arg(clients).arg(clients == 1 ? "" : "s")
                         : snapshot["listening"].toBool() ? QString("Listening · waiting for a connection") : QString("Starting listener…");
        state->setText(current["protocol"].toString().toUpper() + " · " + phase);
        state->setStyleSheet("font-weight:600;font-size:18px;color:#7ac89a;");
        const auto host = current["address"].toString();
        connection->setText((host.contains(':') ? "[" + host + "]" : host) + ":" + QString::number(current["port"].toInt()) +
                            "\n" + current["output"].toString() + " · " + (current["control"].toBool() ? "Remote control" : "View only"));
        // Allow long SHA-256 fingerprints to wrap at a byte boundary.
        fingerprint->setText(QString(current["fingerprint"].toString()).replace(":", ":\u200b"));
    } else {
        if (wasRunning && action != "stop") {
            failed = true; message->setText("Sharing stopped unexpectedly. Check the connection log, then start sharing again.");
            message->setStyleSheet("color:#e6a16c;font-weight:600;");
        }
        state->setText(failed ? "Sharing is off · check the message below" : "Sharing is off");
        state->setStyleSheet("font-weight:600;font-size:18px;"); addressChanged();
    }
    const auto output = snapshot["log"].toString(); if (log->toPlainText() != output) log->setPlainText(output);
    updateActions();
}

void HostingPage::updateActions() {
    const bool installed = components[protocol->currentData().toString()].toBool();
    const bool changing = !pendingAction.isEmpty() || (busy && action != "status" && action != "refresh");
    setup->setEnabled(loaded && !changing); refresh->setEnabled(!changing);
    save->setEnabled(loaded && !changing); start->setEnabled(loaded && !changing && installed && !running && passwordValid());
    start->setToolTip(passwordValid() ? "Start listening for remote connections" : "Enter a sharing password of at least 12 characters first");
    stop->setEnabled(!changing && running); install->setEnabled(loaded && !changing); install->setVisible(loaded && !installed);
    if (loaded && !busy && !failed && !hasPassword && password->text().isEmpty())
        message->setText("Set a sharing password (12+ characters), then choose Start sharing.");
    control->setEnabled(protocol->currentData().toString() != "rdp");
}

void HostingPage::protocolChanged(bool resetPort) {
    const bool rdp = protocol->currentData().toString() == "rdp";
    if (resetPort) port->setValue(rdp ? 3389 : 5900);
    if (rdp) control->setChecked(true);
    hint->setText(rdp ? "RDP shares keyboard, mouse, text/image clipboard and desktop audio. Sharing ends at logout; the login screen is not shared."
                      : "VNC can share a view-only desktop or allow keyboard and mouse control. Use a TLS-capable viewer such as TigerVNC. Sharing ends at logout.");
    install->setText(rdp ? "Build RDP component" : "Install VNC component");
    addressChanged(); updateActions();
}

void HostingPage::addressChanged() {
    if (running) return; // The connection card always describes the active listener.
    const auto host = address->currentData().toString();
    connection->setText((host.contains(':') ? "[" + host + "]" : host) + ":" + QString::number(port->value()) + "\n" +
                        (protocol->currentData().toString() == "rdp" ? "Windows Remote Desktop · RDP" : "Encrypted VNC · TigerVNC"));
}

bool HostingPage::passwordValid() const {
    const auto text = password->text();
    return text.isEmpty() ? hasPassword : text.size() >= 12 && text.size() <= 256 && text == text.trimmed()
        && !text.contains('\n') && !text.contains('\r') && !text.contains(QChar::Null);
}
void HostingPage::operationMessage(const QString &operation) {
    if (operation == "status" || operation == "refresh") return;
    failed = false; message->setStyleSheet({});
    if (operation == "start") { state->setText("Starting sharing…"); message->setText("Opening the listener and checking that it is ready…"); }
    else if (operation == "stop") { state->setText("Stopping sharing…"); message->setText("Disconnecting viewers and stopping sharing…"); }
    else if (operation == "save") message->setText("Saving sharing settings…");
    else if (operation == "install") message->setText("Preparing the component. Administrator authentication may appear; an RDP build can take several minutes.");
}

void HostingPage::showEvent(QShowEvent *event) {
    QWidget::showEvent(event); poll->start(); request(loaded ? "status" : "refresh");
}
void HostingPage::hideEvent(QHideEvent *event) {
    poll->stop(); QWidget::hideEvent(event);
}
}
