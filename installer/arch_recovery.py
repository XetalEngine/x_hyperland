"""One dependency-checked libalpm transaction for full Arch package recovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess


def settings(base):
    result={}
    for line in base.splitlines():
        if line.startswith('[') and line != '[options]':break
        key, separator, value=line.partition('=')
        if separator:result.setdefault(key.strip(),[]).append(value.strip())
    return result


def reasons(database):
    result={}
    for path in (Path(database)/'local').glob('*/desc'):
        fields={}
        for block in path.read_text().split('\n\n'):
            lines=block.splitlines()
            if lines:fields[lines[0]]=lines[1:]
        if '%NAME%' in fields:
            result[fields['%NAME%'][0]]=int(fields.get('%REASON%',['0'])[0])
    return result


def replay(backup, base, additions, removals, inventory, *, database=None, root=None, database_only=False):
    """Use only verified local archives; require the inventory under alpm's lock."""
    options=settings(base)
    source=backup/'arch_recovery.c'
    if not source.exists():shutil.copyfile(Path(__file__).with_suffix('.c'),source)
    binary=backup/'arch-recovery'
    temporary=backup/'arch-recovery.build'
    environment={**os.environ,'LC_ALL':'C'}
    for key in ('LD_LIBRARY_PATH','LD_PRELOAD','LIBRARY_PATH','CPATH','C_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH'):
        environment.pop(key,None)
    # Rebuild against the currently installed libalpm, including after pacman
    # itself was upgraded. Recovery records retain their original helper source.
    subprocess.run(['/usr/bin/cc','-std=c11','-O2','-Wall','-Wextra',str(source),
                    '-o',str(temporary),'-lalpm','-ljson-c'],check=True,env=environment)
    os.replace(temporary,binary)
    plan=dict(root=str(root or options.get('RootDir',['/'])[0]),
              database=str(database or options.get('DBPath',['/var/lib/pacman'])[0]),
              logfile=str(backup/'recovery.log'),gpgdir=options.get('GPGDir',['/etc/pacman.d/gnupg'])[0],
              architectures=options.get('Architecture',['x86_64']),hookdirs=options.get('HookDir',[]),
              noupgrade=options.get('NoUpgrade',[]),noextract=options.get('NoExtract',[]),
              database_only=database_only,inventory=inventory,add=additions,remove=removals,
              reasons=json.loads((backup/'install-reasons.json').read_text()))
    config=backup/'recovery-plan.json'
    config.write_text(json.dumps(plan,indent=2)+'\n')
    # A cancellation waits for the package step to finish; do not kill it
    # halfway through replacing files or removing a compatibility package.
    with subprocess.Popen([str(binary),str(config)],env=environment,start_new_session=True) as process:
        try:
            code=process.wait()
        except BaseException:
            process.wait()
            raise
        if code:raise subprocess.CalledProcessError(code,[str(binary),str(config)])
