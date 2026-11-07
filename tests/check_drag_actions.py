"""Cross-toolkit drag fixtures used by check-desktop-icons.py's private session."""
import json
import time
from pathlib import Path


def check_drag_actions(root, build, desktop, positions, spawn, ctl, run, gesture, wait):
    source = desktop.parent/'Transfers'; source.mkdir()
    (source/'Target').mkdir()
    for name in ('Copy.txt', 'Move.txt', 'Link.txt', 'Local.txt'):
        (source/name).write_text('Native drag: '+name)
    (source/'Folder').mkdir(); (source/'Folder/child.txt').write_text('Folder shortcut contents')
    report = root/'files-positions.json'
    (root/'preferences.ini').write_text('[General]\nview=1\npreview=false\n')
    spawn([str(build/'files-drag-probe'), str(source), str(report), 'Transfer fixture'])

    def client(title):
        return next((c for c in json.loads(ctl('-j', 'clients')) if c['title']==title), None)

    def place(title, x, y):
        wait(lambda: client(title), title)
        address = 'address:'+client(title)['address']
        ctl('dispatch', 'setfloating', address)
        ctl('dispatch', 'resizewindowpixel', 'exact 760 650,'+address)
        ctl('dispatch', 'movewindowpixel', f'exact {x} {y},'+address)
        time.sleep(.25)

    def file_points():
        try: return json.loads(report.read_text())
        except (FileNotFoundError, ValueError): return {}

    def files(name):
        def point():
            wait(lambda: name in file_points(), 'Files item '+name)
            a, b = client('Transfer fixture')['at']; x, y = file_points()[name]
            return a+x, b+y
        return point

    def icon(name):
        def point():
            wait(lambda: name in positions(), 'Desktop icon '+name)
            x, y = positions()[name]; return x+40, y+26
        return point

    captures = []
    def drag(a, b, keys, label, held_before=False):
        monitor=json.loads(ctl('-j', 'monitors'))[0]
        if monitor['width']!=1280 or monitor['height']!=900:
            ctl('keyword','monitor',monitor['name']+',1280x900@60,0x0,1');time.sleep(.4)
        wait(lambda: json.loads((root/'state.json').read_text())['surfaces'][0]['area'][2:]==[1248,868], 'resized desktop layout')
        a=a() if callable(a) else a
        b=b() if callable(b) else b
        if held_before:
            gesture(f'move {a[0]} {a[1]}');gesture('button 1');gesture('button 0',.3)
            for key in keys: gesture(f'key {key} 1')
        gesture(f'move {a[0]} {a[1]}'); gesture('button 1')
        gesture(f'move {a[0]+18} {a[1]+14}')
        if not held_before:
            for key in keys: gesture(f'key {key} 1')
        gesture(f'move {b[0]} {b[1]}', .35)
        gesture(f'move {b[0]+1} {b[1]+1}', .35)
        run('grim', str(root/(label+'.png')))
        native=json.loads(ctl('-j','xetal-file-drag'))
        captures.append(dict(label=label, pointer=[b[0]+1,b[1]+1],feedback=native))
        (root/'drag-actions.json').write_text(json.dumps(dict(captures=captures),indent=2))
        expected='none' if 'denied' in label else 'link' if 'shortcut' in label or label.endswith('link') else 'copy' if label.endswith('copy') else 'move'
        assert native.get('active') and native.get('action')==expected, (label,native,expected)
        gesture('button 0', .25)
        for key in reversed(keys): gesture(f'key {key} 0')

    place('Transfer fixture', 500, 80)
    drag(icon('5 notes # café.txt'), icon('A folder'), [29,42], 'desktop-local-shortcut')
    wait(lambda: (desktop/'A folder/5 notes # café.txt').is_symlink(), 'Desktop local shortcut')
    for index, operation, keys in [(1,'copy',[29]), (2,'move',[42]), (3,'link',[29,42])]:
        name=f'{index} notes # café.txt'
        drag(icon(name), files('Target'), keys, 'desktop-to-files-'+operation)
        target=source/'Target'/name
        wait(lambda: target.exists(), 'Desktop to Files '+operation)
        assert target.is_symlink()==(operation=='link'), str(target)
        assert (desktop/name).exists()==(operation!='move'), str(desktop/name)
        if operation=='link': assert target.resolve()==desktop/name
    drag(icon('A folder'), files('_background'), [29,42], 'desktop-folder-shortcut')
    wait(lambda: (source/'A folder').is_symlink(), 'Desktop folder shortcut in Files')
    assert (source/'A folder').resolve()==desktop/'A folder'

    # Use background destinations as well as existing folder icons. New desktop
    # items must retain the drop position and shortcut arrow after refresh.
    for name, operation, keys, point in [('Copy.txt','copy',[29],(300,550)), ('Move.txt','move',[42],(300,670)), ('Link.txt','link',[29,42],(300,310))]:
        drag(files(name), point, keys, 'files-to-desktop-'+operation)
        wait(lambda: (desktop/name).exists(), 'Files to Desktop '+operation)
        assert (desktop/name).is_symlink()==(operation=='link')
        assert (source/name).exists()==(operation!='move')
        if operation=='link': assert (desktop/name).resolve()==source/name
    drag(files('Folder'), icon('A folder'), [29,42], 'files-folder-shortcut')
    wait(lambda: (desktop/'A folder/Folder').is_symlink(), 'Files folder shortcut on Desktop')
    assert (desktop/'A folder/Folder').resolve()==source/'Folder'
    drag(files('Local.txt'), files('Target'), [29,42], 'files-local-shortcut')
    wait(lambda: (source/'Target/Local.txt').is_symlink(), 'Files local shortcut')
    drag(icon('7 notes # café.txt'),files('Target'),[29],'desktop-preheld-copy',True)
    wait(lambda: (source/'Target/7 notes # café.txt').exists(),'Ctrl held before desktop drag')
    assert (desktop/'7 notes # café.txt').exists()
    drag(icon('7 notes # café.txt'),icon('A folder'),[29,42],'desktop-preheld-shortcut',True)
    wait(lambda: (desktop/'A folder/7 notes # café.txt').is_symlink(),'Ctrl+Shift held before desktop drag')

    computer_report = root/'computer-positions.json'
    spawn([str(build/'files-drag-probe'), 'computer:/', str(computer_report), 'Computer fixture'])
    place('Computer fixture', 500, 100)
    for name, origin in [('desktop', lambda: icon('4 notes # café.txt')), ('files', lambda: files('A folder'))]:
        if name=='files':
            # Leave an exposed strip of Files; cover its right side with Computer.
            place('Transfer fixture', 10, 80); place('Computer fixture', 500, 100)
        drag(origin(), (1150,500), [29], name+'-denied-computer')
    # A non-drop toolbar must reject the operation just like a taskbar.
    place('Transfer fixture', 500, 80)
    ctl('dispatch', 'closewindow', 'address:'+client('Computer fixture')['address'])
    drag(icon('4 notes # café.txt'), (850,100), [29,42], 'desktop-denied-toolbar')
    drag(files('Copy.txt'), (850,100), [29], 'files-denied-toolbar')
    # Change modifiers after crossing the application boundary. The final drop
    # must match the last badge, and modifier release must restore Move.
    for label, a, b, destination, original in [
        ('desktop-switch',icon('6 notes # café.txt'),files('Target'),source/'Target/6 notes # café.txt',desktop/'6 notes # café.txt'),
        ('files-switch',files('Local.txt'),(310,800),desktop/'Local.txt',source/'Local.txt')]:
        start=a(); end=b() if callable(b) else b
        gesture(f'move {start[0]} {start[1]}');gesture('button 1')
        gesture(f'move {start[0]+18} {start[1]+14}');gesture(f'move {end[0]} {end[1]}')
        held=[]
        for index, keys, expected in [(0,[29],'copy'),(1,[29,42],'link'),(2,[42],'move'),(3,[],'move'),(4,[29,42],'link')]:
            for key in held: gesture(f'key {key} 0',.02)
            for key in keys: gesture(f'key {key} 1',.02)
            held=keys
            gesture(f'move {end[0]+index} {end[1]}',.25)
            feedback=json.loads(ctl('-j','xetal-file-drag'))
            assert feedback.get('action')==expected and feedback.get('active'),(label,index,feedback)
            run('grim',str(root/f'{label}-{index}-{expected}.png'))
        gesture('button 0',.25)
        for key in held: gesture(f'key {key} 0')
        wait(lambda: destination.is_symlink(),'modifier change ends in shortcut')
        assert destination.resolve()==original and original.exists()
    assert (desktop/'4 notes # café.txt').exists()
    assert (source/'Copy.txt').exists()
    assert not (source/'4 notes # café.txt').exists()
    (root/'drag-actions.json').write_text(json.dumps(dict(result='passed', captures=captures), indent=2))
    print('PASS: copy/move/shortcuts in both directions, folder shortcuts, live modifier changes, and rejected Computer/toolbar drops.', flush=True)
