import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtGui import QImage, QColor, QIcon
from PyQt6.QtWidgets import QApplication
from gi.repository import Gio

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from effects.minimize import icons


class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_native_and_helper_share_safe_case_normalized_cache_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'keys.cpp'; binary = root/'keys'
            source.write_text('#include "icons.hpp"\n#include <iostream>\nint main(int n,char**v){for(int i=1;i<n;++i)std::cout<<Minimize::iconKey(v[i])<<"\\n";}\n')
            subprocess.run(['g++', '-std=c++23', '-I'+str(Path(icons.__file__).parent/'native'), str(source), '-o', str(binary)], check=True, capture_output=True)
            names = ['Org.KDE.Kate', 'org.kde.kate', '../../private', 'Unicode-π', 'app with spaces']
            result = subprocess.check_output([str(binary), *names], text=True).splitlines()
            self.assertEqual(result, [icons.key(name) for name in names])
            self.assertEqual(result[0], result[1])
            self.assertTrue(all('/' not in name for name in result))

    def test_installed_app_icon_and_missing_icon_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = QImage(400, 200, QImage.Format.Format_ARGB32); image.fill(QColor('#54ddaa'))
            self.assertTrue(image.save(str(root/'fixture.png')))
            desktop = root/'fusion-fixture-icon.desktop'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Icon fixture\nExec=/usr/bin/true\nStartupWMClass=FusionIconFixture\nIcon='+str(root/'fixture.png')+'\n')
            app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            icon = icons.resolve('FusionIconFixture', [app])
            self.assertFalse(icon.isNull())
            directory = root/'cache'
            self.assertTrue(icons.save(directory, 'FusionIconFixture', icon))
            cached = QImage(str(directory/icons.key('FusionIconFixture')))
            self.assertLessEqual(max(cached.width(), cached.height()), 256)
            self.assertTrue(icons.resolve('FusionFixtureWithNoInstalledIcon-83921', [app]).isNull())

    def test_offscreen_helper_finds_xdg_themed_icons(self):
        previous = QIcon.themeSearchPaths(), QIcon.fallbackSearchPaths(), QIcon.themeName()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); theme = root/'icons/fusion-fixture-theme'
                folder = theme/'64x64/apps'; folder.mkdir(parents=True)
                (theme/'index.theme').write_text('[Icon Theme]\nName=Fixture\nDirectories=64x64/apps\n[64x64/apps]\nSize=64\nType=Fixed\nContext=Applications\n')
                art = QImage(64, 64, QImage.Format.Format_ARGB32); art.fill(QColor('#54ddaa'))
                self.assertTrue(art.save(str(folder/'fusion-themed-app.png')))
                QIcon.setThemeSearchPaths([':/icons']); QIcon.setThemeName('fusion-fixture-theme')
                self.assertTrue(icons.resolve('fusion-themed-app', []).isNull())
                with patch.object(icons.QStandardPaths, 'standardLocations', return_value=[str(root)]):
                    icons.configure_icon_paths()
                icon = icons.resolve('fusion-themed-app', [])
                self.assertFalse(icon.isNull()); self.assertFalse(icon.pixmap(64, 64).isNull())
                self.assertIn(str(root/'pixmaps'), QIcon.fallbackSearchPaths())
        finally:
            QIcon.setThemeSearchPaths(previous[0]); QIcon.setFallbackSearchPaths(previous[1]); QIcon.setThemeName(previous[2])


if __name__ == '__main__':unittest.main()
