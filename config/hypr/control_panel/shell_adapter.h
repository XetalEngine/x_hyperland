// Adapt only the shell/shortcut integration; system operations remain C++.
#include <QJsonArray>
void MainWindow::hyperLoadAliases() {
  auto result = HyperPanel::request("aliases");
  if (result.contains("error")) {
    ui->shellLabel->setText(result["error"].toString());
    return;
  }
  hyperAliasSnapshot = result;
  detectedShell = result["shell"].toString();
  detectedConfigFile = result["config"].toString();
  aliasList.clear();
  for (auto value : result["entries"].toArray()) {
    auto entry = value.toObject();
    aliasList.append({entry["name"].toString(), entry["command"].toString()});
  }
  ui->shellLabel->setText(
      tr("Shell: %1\nConfig: %2\nTerminal: Kitty · shortcuts are saved to Apps")
          .arg(detectedShell, detectedConfigFile));
}
void MainWindow::hyperSaveAliases() {
  QJsonArray entries;
  for (const auto &entry : aliasList)
    entries.append(
        QJsonObject{{"name", entry.name}, {"command", entry.command}});
  auto request = hyperAliasSnapshot;
  request["entries"] = entries;
  auto result = HyperPanel::request("save-aliases", request);
  if (result.contains("error"))
    QMessageBox::warning(this, tr("Aliases were not saved"),
                         result["error"].toString());
  hyperLoadAliases();
  populateAliasTable();
}
void MainWindow::hyperShortcut(const AliasEntry &entry) {
  HyperPanel::shortcut({{"name", entry.name},
                        {"command", entry.command},
                        {"shell", detectedShell},
                        {"config", detectedConfigFile}});
}
