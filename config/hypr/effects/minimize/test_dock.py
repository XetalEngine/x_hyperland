import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent.parent))
from effects.minimize import model,controller


class DockTests(unittest.TestCase):
    def test_layout_animation_and_idle_deadlines(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'dock'
            subprocess.run(['g++','-std=c++23','-I'+str(ROOT/'native'),str(ROOT/'native/test_dock.cpp'),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,timeout=10)

    def test_native_design_selection_and_legacy_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'settings.cpp';binary=root/'settings';config=root/'settings.conf';palette=root/'current.colors'
            source.write_text('''#include "settings.hpp"
#include <iostream>
int main(int argc,char** argv){auto s=Minimize::readSettings(argv[1],argv[2]);
std::cout<<s.dock<<" "<<s.dockStyle<<" "<<s.effect<<" "<<s.rgb[0]<<" "<<s.background[0];}''')
            subprocess.run(['g++','-std=c++23','-I'+str(ROOT/'native'),str(source),'-o',str(binary)],check=True,capture_output=True)
            def read():return subprocess.check_output([str(binary),str(config),str(palette)],text=True).split()
            config.write_text(model.encode(model.DEFAULTS))
            for i,name in enumerate(k for k in model.DOCK_STYLES if k!='follow'):
                palette.write_text('[General]\nColorScheme=Xetal'+name.title()+'Light\n[Colors:Window]\nDecorationFocus=80,180,240\nBackgroundNormal=128,128,128\n')
                value=read();self.assertEqual(value[:3],['1',str(i),'fireball'])
                self.assertAlmostEqual(float(value[3]),80/255,places=5);self.assertAlmostEqual(float(value[4]),128/255,places=5)
            config.write_text(model.encode(dict(model.DEFAULTS,dock_style='breakpoint',follow_theme=False,color='#abcdef')))
            value=read();self.assertEqual(value[1],'2');self.assertAlmostEqual(float(value[3]),171/255,places=5)
            old={k:v for k,v in model.DEFAULTS.items() if k in model.PRE_DOCK}
            old.update(effect='splat',edge='right',order='top-to-bottom')
            config.write_text(''.join(f'{k}={int(v) if type(v) is bool else v}\n' for k,v in old.items()))
            self.assertEqual(read()[:3],['0','9','fireball'])
            self.assertEqual(model.load(config)[0]['presentation'],'stack')

    def test_live_upgrade_unloads_only_recorded_build_before_loading_new(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.so';old.touch();new=root/'new.so';new.touch()
            (root/'xetal-minimize.json').write_text(json.dumps({'path':str(old)}))
            calls=[]
            def hypr(*args):
                calls.append(args)
                if args==('-j','plugin','list'):return '[{"name":"Xetal Minimize","version":"1.2"}]'
                if args==('-j','version'):return json.dumps({'commit':controller.build.SUPPORTED_COMMIT})
                if args==('xetal-minimize',):return '{"enabled":true}'
                return 'ok'
            with patch.object(controller,'instance_dir',return_value=root),patch.object(controller,'hypr',side_effect=hypr):
                controller.activate(model.DEFAULTS,new)
            self.assertLess(calls.index(('plugin','unload',str(old))),calls.index(('plugin','load',str(new))))
            self.assertEqual(controller.loaded_path(root/'xetal-minimize.json'),new)

    def test_failed_upgrade_recovers_previous_config_and_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.so';old.touch();new=root/'new.so';new.touch();config=root/'settings.conf'
            config.write_text('enabled=1\neffect=fireball\nduration=420\nsize=76\n')
            before=config.read_bytes();previous,token=model.load(config)
            (root/'xetal-minimize.json').write_text(json.dumps({'path':str(old)}))
            loaded=[True];recovered=[]
            def hypr(*args):
                if args==('-j','plugin','list'):return '[{"name":"Xetal Minimize","version":"1.2"}]' if loaded[0] else '[]'
                if args==('-j','version'):return json.dumps({'commit':controller.build.SUPPORTED_COMMIT})
                if args==('plugin','unload',str(old)):loaded[0]=False
                if args==('plugin','load',str(new)):raise RuntimeError('Test load failure')
                if args==('plugin','load',str(old)):
                    self.assertEqual(config.read_bytes(),before);loaded[0]=True;recovered.append(True)
                if args==('xetal-minimize',):return '{"enabled":true}'
                return 'ok'
            with patch.object(controller,'instance_dir',return_value=root),patch.object(controller,'hypr',side_effect=hypr),patch.object(controller.build,'build',return_value=new):
                with self.assertRaisesRegex(RuntimeError,'Test load failure'):
                    controller.save(dict(previous,presentation='dock'),token,config)
            self.assertTrue(recovered);self.assertEqual(config.read_bytes(),before)
