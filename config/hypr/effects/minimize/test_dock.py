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
    def test_existing_dock_preferences_keep_slide_and_new_burn_settings_roundtrip(self):
        previous=dict(model.DEFAULTS,hide_delay=2400,dock_style='gildedhollow',dock_edge='left',dock_zoom=140,
                      hide_animation='slide',fire_indicator=False)
        legacy=''.join(f'{k}={int(v) if type(v) is bool else v}\n' for k,v in previous.items() if k not in model.HIDE_KEYS)
        self.assertEqual(model.decode(legacy),previous)
        burn=dict(previous,hide_animation='burn',fire_indicator=True)
        self.assertEqual(model.decode(model.encode(burn)),burn)
        for invalid in ({'hide_animation':'unknown'},{'fire_indicator':'yes'},{'fire_indicator':1}):
            with self.assertRaises(ValueError):model.validate(dict(burn,**invalid))

    def test_new_design_survives_an_older_library_loaded_in_the_same_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);legacy=root/'legacy.cpp';current=root/'current.cpp'
            # This is the public inline table layout used by older adapters.
            # GNU-unique binding keeps it alive even after dlclose.
            legacy.write_text('''#include <map>
#include <string>
namespace Minimize { inline const std::map<std::string,int> dockStyles{{"raw",0}}; }
extern "C" int initialize(){return Minimize::dockStyles.at("raw");}''')
            current.write_text('''#include "settings.hpp"
extern "C" __attribute__((visibility("default")))
int readStyle(const char* config,const char* palette){
try{return Minimize::readSettings(config,palette).dockStyle;}catch(...){return -1;}}''')
            old=root/'legacy.so';new=root/'current.so'
            subprocess.run(['g++','-std=c++23','-shared','-fPIC',str(legacy),'-o',str(old)],check=True,capture_output=True)
            subprocess.run(['g++',*controller.build.COMPILE_FLAGS,'-I'+str(ROOT/'native'),str(current),'-o',str(new)],check=True,capture_output=True)
            config=root/'settings.conf';palette=root/'current.colors'
            config.write_text(model.encode(dict(model.DEFAULTS,dock_style='gildedhollow')))
            palette.write_text('[General]\nColorScheme=XetalGildedHollowDark\n')
            # Isolate the dynamic loader state from other unit tests.
            probe='''import ctypes,sys
from _ctypes import dlclose
old=ctypes.CDLL(sys.argv[1]); assert old.initialize()==0
dlclose(old._handle)
new=ctypes.CDLL(sys.argv[2]);new.readStyle.argtypes=[ctypes.c_char_p,ctypes.c_char_p]
print(new.readStyle(sys.argv[3].encode(),sys.argv[4].encode()))'''
            def read():
                return subprocess.check_output([sys.executable,'-c',probe,str(old),str(new),str(config),str(palette)],text=True).strip()
            self.assertEqual(read(),'10')
            config.write_text(model.encode(model.DEFAULTS))
            self.assertEqual(read(),'10')

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
            self.assertEqual(read()[:3],['0',str(i),'fireball'])
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
