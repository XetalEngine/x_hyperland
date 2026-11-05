"""Dock scenarios shared by the disposable compositor integration check."""
import json
from pathlib import Path
import time


def check(root, env, ctl, dispatch, status, clients, client, wait, app, run, spawn,
          pointer, output, model, config, palette):
    from PIL import Image, ImageDraw
    output_name=output['name']
    values=dict(model.DEFAULTS,auto_hide=False)
    def settings(**changes):
        values.update(changes);config.write_text(model.encode(values));dispatch('xetalminimize:reload')
    def monitors():return json.loads(ctl('-j','monitors'))
    def monitor(name=output_name):return next(m for m in monitors() if m['name']==name)
    def dock(name=output_name):return next(d for d in status()['docks'] if d['monitor']==monitor(name)['id'])
    def pointer_at(x,y,kind='move'):
        outputs=monitors();left=min(m['x'] for m in outputs);top=min(m['y'] for m in outputs)
        right=max(m['x']+m['width']/m['scale'] for m in outputs)
        bottom=max(m['y']+m['height']/m['scale'] for m in outputs)
        run(str(pointer),str(int(x-left)),str(int(y-top)),str(int(right-left)),str(int(bottom-top)),kind)
    def center():
        m=monitor();pointer_at(m['x']+m['width']/m['scale']/2,m['y']+m['height']/m['scale']/2)
    def near_edge(name=output_name):
        d=dock(name);m=monitor(name);x,y,w,h=d['sensor']
        pointer_at(m['x']+x+w/2,m['y']+y+h/2)
    def ready():wait(lambda: dock()['reveal']==1)
    def add(name):
        app('add',name);wait(lambda:any(c['title']==name for c in clients()));time.sleep(.08)
        before=status()['active'];app('min',name);wait(lambda:status()['active']==before+1)
    def slot_click(item):
        m=monitor();x,y,w,h=item['box'];pointer_at(m['x']+x+w/2,m['y']+y+h/2,'click')
    def close_all():
        dispatch('xetalminimize:restoreall');wait(lambda:status()['active']==0)
        for c in clients():app('close',c['title'])
        wait(lambda:not clients())

    # Regression: finishing the last restore used to stop the frame timer
    # before the dock could notice its slot count had reached zero.
    settings(auto_hide=False,hide_delay=10000);center()
    for operation in ('click','close','activate','restoreall'):
        name='Last dock window '+operation;add(name);ready();time.sleep(.4)
        if operation=='click':slot_click(status()['windows'][0])
        elif operation=='close':app('close',name)
        elif operation=='activate':dispatch('focuswindow','address:'+client(name)['address'])
        else:dispatch('xetalminimize:restoreall')
        wait(lambda:status()['active']==0);start=time.monotonic()
        wait(lambda:dock()['reveal']==0)
        wait(lambda:dock()['box'][2]<1)
        assert time.monotonic()-start<.7,'Empty dock waited for the hide delay'
        near_edge();time.sleep(.2);assert dock()['reveal']==0,'Empty dock reappeared on hover'
        draws=status()['draws'];time.sleep(.15);assert status()['draws']==draws
        if operation!='close':app('close',name)
        center()
    print('Last-slot click, close, external restore and restore-all promptly hide the empty dock: passed',flush=True)

    settings(hide_delay=1200);center();add('Dock Alpha');ready();time.sleep(.3)
    initial=dock()['box'][2]
    add('Dock Beta');add('Dock Gamma');ready();time.sleep(.3)
    assert dock()['box'][2]>initial*2
    assert status()['presentation']=='dock' and status()['effect']=='fireball'
    run('grim','-o',output_name,str(root/'dock-three.png'))
    # Hover magnifies an actual slot, and clicking restores only that window.
    first=status()['windows'][0];width=first['box'][2];x,y,w,h=first['box']
    pointer_at(x+w/2,y+h/2);time.sleep(.3)
    assert status()['windows'][0]['box'][2]>width*1.1
    slot_click(status()['windows'][0]);wait(lambda:status()['active']==2)
    time.sleep(.4);assert dock()['box'][2]<initial*3
    assert not client('Dock Alpha')['workspace']['name'].startswith('special:')
    app('close','Dock Alpha');app('close','Dock Beta');wait(lambda:status()['active']==1)
    time.sleep(.4);assert abs(dock()['box'][2]-initial)<1
    add('Dock Delta');add('Dock Epsilon');ready();center()
    print('Dock slots grow, hover-zoom, restore and collapse after close: passed',flush=True)

    # Theme geometry/materials follow the palette, or can be selected separately.
    accents=['5bd5d1','88aacc','ef3347','37beff','53d8e7','a63536','ef9d41','eba1d0','97b9c6','adc49c']
    shots=[]
    for i,name in enumerate(k for k in model.DOCK_STYLES if k!='follow'):
        rgb=','.join(str(int(accents[i][j:j+2],16)) for j in (0,2,4))
        background='227,223,209' if name=='porcelainink' else '17,23,29'
        foreground='36,40,46' if name=='porcelainink' else '224,232,237'
        palette.write_text(f'[General]\nColorScheme=Xetal{name.title()}Dark\n[Colors:Window]\nDecorationFocus={rgb}\nBackgroundNormal={background}\nForegroundNormal={foreground}\n')
        settings(dock_style='follow',dock_edge='bottom');ready();time.sleep(.18)
        assert status()['dock_style']==i
        path=root/('dock-'+name+'.png');run('grim','-o',output_name,str(path))
        x,y,w,h=dock()['box'];picture=Image.open(path)
        shots.append((model.DOCK_STYLES[name],picture.crop((int(x-12),int(y-24),int(x+w+12),int(y+h+14))).convert('RGB')))
    canvas=Image.new('RGB',(1000,5*180),'#101820');draw=ImageDraw.Draw(canvas)
    for i,(title,picture) in enumerate(shots):
        x=(i%2)*500;y=(i//2)*180;canvas.paste(picture,(x+(500-picture.width)//2,y+34));draw.text((x+20,y+10),title,fill='white')
    canvas.save(root/'dock-gallery.png')
    settings(dock_style='binaryknife');assert status()['dock_style']==3
    print('Ten live theme designs and independent design selection: passed',flush=True)

    # Test real mapped Waybar layers at both edges, not only reserved margins.
    bar_config=root/'dock-waybar.json';bar_css=root/'dock-waybar.css'
    bar_css.write_text('window#waybar { background: #263442; color: #ffffff; }')
    for position,opposite in (('top','bottom'),('bottom','top')):
        bar_config.write_text(json.dumps({'layer':'top','position':position,'height':30,'output':output_name,'modules-center':['clock']}))
        with (root/('waybar-'+position+'.log')).open('w') as stream:
            bar=spawn(['waybar','-c',str(bar_config),'-s',str(bar_css)],env=env,stdout=stream,stderr=stream)
            try:
                settings(dock_edge='auto');wait(lambda: dock()['edge']==opposite and any(any(m['reserved']) for m in monitors()))
                assert bar.poll() is None
            finally:
                bar.terminate();bar.wait(timeout=5)
        time.sleep(.2)
    print('Automatic dock position opposite real top/bottom Waybars: passed',flush=True)

    app('add','Dock Underlay');wait(lambda:any(c['title']=='Dock Underlay' for c in clients()))
    dispatch('fullscreen','1')
    for edge in ('bottom','top','left','right'):
        settings(dock_edge=edge,auto_hide=True,hide_delay=400,dock_duration=180,proximity=20)
        center();ready();shown=dock();m=monitor();screenw=m['width']/m['scale'];screenh=m['height']/m['scale']
        x,y,w,h=shown['box'];assert x>=0 and y>=0 and x+w<=screenw and y+h<=screenh
        if edge in ('top','bottom'):assert (y<screenh/2)==(edge=='top')
        else:assert (x<screenw/2)==(edge=='left')
        wait(lambda:dock()['reveal']==0)
        hidden=status();assert all(not w['visible'] for w in hidden['windows'])
        time.sleep(.2);assert status()['draws']==hidden['draws'], 'Hidden dock kept rendering'
        if edge=='bottom':
            pointer_at(x+w/2,y+h/2,'click');time.sleep(.08)
            assert status()['active']==3 and dock()['reveal']==0,'Hidden dock intercepted input'
            assert json.loads(ctl('-j','activewindow'))['title']=='Dock Underlay'
        near_edge();ready();time.sleep(.2)
        assert status()['windows'][0]['visible']
        run('grim','-o',output_name,str(root/('dock-edge-'+edge+'.png')))
        # The exact edge keeps it open until the pointer leaves.
        time.sleep(.5);assert dock()['reveal']==1
        center();started=time.monotonic();wait(lambda:dock()['reveal']==0)
        assert time.monotonic()-started>=.30,'Hide delay was ignored'
    settings(auto_hide=False,dock_edge='bottom');ready()
    ctl('keyword','animations:enabled','false');settings(auto_hide=True,hide_delay=250)
    center();wait(lambda:dock()['reveal']==0);near_edge();wait(lambda:dock()['reveal']==1)
    ctl('keyword','animations:enabled','true')
    app('close','Dock Underlay')
    print('Four edges, proximity, adjustable delay, idle rendering and reduced motion: passed',flush=True)

    # A shared boundary reveals only the monitor containing the cursor.
    ctl('output','create','wayland','DOCK-SECOND');wait(lambda:len(monitors())==2)
    second=next(m for m in monitors() if m['name']!=output_name)
    dispatch('focusmonitor',second['name']);dispatch('workspace','9');add('Dock Other Output')
    settings(dock_edge='left',hide_delay=250,proximity=24,auto_hide=True)
    # Move away from both sensors, then approach the second monitor from inside.
    center();wait(lambda: all(d['reveal']==0 for d in status()['docks']))
    near_edge(second['name']);wait(lambda:dock(second['name'])['reveal']==1)
    assert dock()['reveal']==0
    m=monitor(second['name']);d=dock(second['name']);sx,sy,sw,sh=d['sensor']
    # One logical pixel across the shared edge belongs to the adjacent output.
    pointer_at(m['x']-2,m['y']+sy+sh/2)
    wait(lambda:dock(second['name'])['reveal']==0)
    near_edge();ready();assert dock(second['name'])['reveal']==0
    ctl('output','remove',second['name']);wait(lambda:status()['active']==0)
    wait(lambda:len(monitors())==1)
    assert client('Dock Other Output')['monitor']==monitor()['id'] and not client('Dock Other Output')['hidden']
    close_all();dispatch('workspace','1')
    print('Independent monitor docks and shared-boundary proximity: passed',flush=True)

    # Overflow first reduces slot size, then pages with the wheel.
    settings(auto_hide=False,size=160,dock_edge='bottom');center()
    for i in range(25):add(f'Dock overflow {i}')
    ready();time.sleep(.3);d=dock()
    assert 0<d['capacity']<25 and d['offset']==25-d['capacity']
    assert status()['windows'][-1]['box'][2]<160
    for _ in range(25):
        item=next(w for w in status()['windows'] if w['visible']);x,y,w,h=item['box'];pointer_at(x+w/2,y+h/2,'-1')
    time.sleep(.3);assert dock()['offset']==0 and status()['windows'][0]['visible']
    slot_click(status()['windows'][0]);wait(lambda:status()['active']==24)
    close_all();wait(lambda:dock()['reveal']==0)
    before=status()['draws'];time.sleep(.25);assert status()['draws']==before
    print('Dock overflow, scrolling, final-slot removal and render sleep: passed',flush=True)
