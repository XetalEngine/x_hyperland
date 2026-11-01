import sys

from PyQt6.QtGui import QFont, QIcon, QPalette, QColor
from PyQt6.QtWidgets import QApplication

from .theme import BACKGROUND, TEXT, STYLESHEET
from .window import CalculatorWindow, ASSET_DIR, ui_font_family


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("xetal-calculator")
    app.setApplicationDisplayName("Calculator")
    app.setDesktopFileName("xetal-calculator")
    app.setOrganizationName("HyperFusion")
    app.setStyle("Fusion")
    app.setFont(QFont(ui_font_family(), 10))
    app.setWindowIcon(QIcon(str(ASSET_DIR / "calculator.svg")))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BACKGROUND))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("#202328"))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor("#30343b"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#345346"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#c2f3de"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
    window = CalculatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
