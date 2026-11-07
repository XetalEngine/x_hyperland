#!/usr/bin/env python3
"""Compile original SVG shapes to Hyprcursor and XCursor, entirely in this profile."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import fcntl

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import art


def register_themes(data, directory=None):
    """Expose only our uniquely named assets; never select a shared desktop theme.

    Hyprcursor snapshots XDG_DATA_DIRS before the session plugin is loaded.
    Named links let it discover the profile's artwork even in a running session.
    """
    directory = directory or Path.home()/'.local/share/icons'
    directory.mkdir(parents=True, exist_ok=True)
    for style in art.STYLES:
        name = 'Xetal-Cursor-'+style
        source = (data/'icons'/name).absolute()
        target = directory/name
        if target.is_symlink() and target.resolve() == source.resolve():
            continue
        if target.exists() or target.is_symlink():
            raise RuntimeError('A different cursor theme already occupies '+str(target))
        target.symlink_to(source, target_is_directory=True)


def build(root=ROOT, register=False):
    cache=root/'.build';cache.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256((ROOT/'art.py').read_bytes()+(ROOT/'build.py').read_bytes()).hexdigest()
    with (cache/'build.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (cache/'version').exists() and (cache/'version').read_text()==fingerprint:
            if register:register_themes(cache/'data')
            return cache/'data'
        from PyQt6.QtCore import QByteArray, QRectF
        from PyQt6.QtGui import QImage,QPainter
        from PyQt6.QtSvg import QSvgRenderer
        # QSvgRenderer works without a display; no live session is touched here.
        with tempfile.TemporaryDirectory(dir=cache) as temp:
            tmp=Path(temp);icons=tmp/'data/icons';icons.mkdir(parents=True)
            for style in art.STYLES:
                name='Xetal-Cursor-'+style;source=tmp/name;source.mkdir()
                (source/'manifest.hl').write_text(f'name = {name}\ndescription = Xetal original cursor collection\nversion = 1\ncursors_directory = hyprcursors\n')
                target=icons/name;target.mkdir();(target/'cursors').mkdir()
                (target/'index.theme').write_text(f'[Icon Theme]\nName={art.STYLES[style][0]}\nInherits=Adwaita\n')
                for shape,aliases in art.ALIASES.items():
                    folder=source/'hyprcursors'/shape;folder.mkdir(parents=True)
                    drawing,hot=art.svg(style,shape)
                    meta=f'resize_algorithm = bilinear\nhotspot_x = {hot[0]/36}\nhotspot_y = {hot[1]/36}\n'
                    meta+=''.join('define_override = '+a+'\n' for a in aliases)
                    entries=[]
                    for frame in range(12 if shape in ('watch','left_ptr_watch') else 1):
                        drawing,_=art.svg(style,shape,frame);filename=f'frame{frame}.svg';(folder/filename).write_text(drawing)
                        meta+=f'define_size = 36, {filename}, 80\n'
                        renderer=QSvgRenderer(QByteArray(drawing.encode()))
                        for size in (24,32,48,64,96):
                            image=QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
                            painter=QPainter(image);renderer.render(painter,QRectF(0,0,size,size));painter.end()
                            png=folder/f'{size}-{frame}.png';image.save(str(png))
                            entries.append(f'{size} {round(hot[0]*size/36)} {round(hot[1]*size/36)} {png} 80')
                    (folder/'meta.hl').write_text(meta)
                    config=folder/'xcursor.conf';config.write_text('\n'.join(entries)+'\n')
                    subprocess.run(['xcursorgen',str(config),str(target/'cursors'/shape)],check=True,capture_output=True)
                    for alias in aliases:(target/'cursors'/alias).symlink_to(shape)
                subprocess.run(['hyprcursor-util','--create',str(source),'--output',str(tmp)],check=True,capture_output=True)
                compiled=tmp/('theme_'+name)
                if not compiled.exists():raise RuntimeError('Cursor compiler did not produce '+str(compiled))
                for item in compiled.iterdir():
                    if item.is_dir():shutil.copytree(item,target/item.name)
                    else:shutil.copy2(item,target/item.name)
            old=cache/'previous';shutil.rmtree(old,ignore_errors=True)
            if (cache/'data').exists():os.replace(cache/'data',old)
            os.replace(tmp/'data',cache/'data');shutil.rmtree(old,ignore_errors=True)
            (cache/'version').write_text(fingerprint)
        if register:register_themes(cache/'data')
    return cache/'data'

if __name__=='__main__':
    # This command only renders assets, even when launched by an X11/Wayland GUI.
    # Override inherited desktop backends for builds in a displayless chroot.
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PyQt6.QtGui import QGuiApplication
    app=QGuiApplication([])
    print(build(register='--register' in sys.argv))
