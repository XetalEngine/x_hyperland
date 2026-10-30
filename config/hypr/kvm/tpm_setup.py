"""Initialize a new private TPM without overwriting any existing guest keys."""
from pathlib import Path
import fcntl
import os
import subprocess
import shutil
import tempfile
import socket
import struct
import time
from functools import lru_cache
import portable


def packaged_binary(binary):
    import packages
    expected = portable.component_path('tpm')/'bin/swtpm'
    return bool(binary and packages.installed('tpm') and expected.is_file()
                and Path(binary).resolve() == expected.resolve())


@lru_cache(maxsize=4)
def inspect_state(binary, data, binary_stamp, identity=False):
    """Query public TPM capabilities on a disposable COPY, never the live state."""
    with tempfile.TemporaryDirectory(prefix='xetal-tpm-check-') as name:
        directory=Path(name);(directory/'tpm2-00.permall').write_bytes(data)
        address=str(directory/'socket')
        command=[binary,'socket','--tpm2','--tpmstate','dir='+name,
                 '--server','type=unixio,path='+address,
                 '--ctrl','type=unixio,path='+str(directory/'control'),
                 '--flags','not-need-init,startup-clear']
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+2
            while not Path(address).exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Could not inspect a temporary copy of the TPM state')
                time.sleep(.01)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(2);client.connect(address)
                def read(count):
                    result=b''
                    while len(result)<count:
                        chunk=client.recv(count-len(result))
                        if not chunk:raise RuntimeError('Incomplete TPM response')
                        result+=chunk
                    return result
                def capability(kind, first):
                    # TPM2_GetCapability, no sessions or authorization: public data only.
                    client.sendall(struct.pack('>HIIIII',0x8001,22,0x17a,kind,first,64))
                    header=read(10);_,size,status=struct.unpack('>HII',header)
                    if status or not 19<=size<=8192:raise RuntimeError('TPM capability query failed')
                    reply=read(size-10)
                    if struct.unpack('>I',reply[1:5])[0]!=kind:raise RuntimeError('Unexpected TPM capability')
                    return reply[5:]
                if identity:
                    properties=capability(6,0x100)
                    count=struct.unpack('>I',properties[:4])[0]
                    return dict(struct.unpack('>II',properties[4+8*i:12+8*i]) for i in range(count))
                pcrs=capability(5,0);count=struct.unpack('>I',pcrs[:4])[0]
                banks=[];offset=4;names={4:'sha1',11:'sha256',12:'sha384',13:'sha512'}
                for _ in range(count):
                    algorithm,length=struct.unpack('>HB',pcrs[offset:offset+3]);offset+=3
                    if any(pcrs[offset:offset+length]):banks.append(names.get(algorithm,hex(algorithm)))
                    offset+=length
                handles=capability(1,0x01000000);count=struct.unpack('>I',handles[:4])[0]
                indices=struct.unpack('>'+'I'*count,handles[4:4+4*count])
                return tuple(banks),bool({0x01c00002,0x01c0000a}.intersection(indices))
        except (struct.error,OSError) as error:
            raise RuntimeError('Could not read TPM capabilities: '+str(error)) from error
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait()


def initialize(state, binary, banks='sha1,sha256', ek='rsa2048', certificates=True, lock_nvram=False, setup_binary=None):
    state = Path(state).expanduser()
    root=portable.data_root().resolve()
    if not state.is_absolute() or not state.resolve().is_relative_to(root) or state.resolve()==root:
        raise ValueError('Select a private TPM state directory inside '+str(portable.data_root()))
    if any(p.is_symlink() for p in (state, *state.parents)):
        raise ValueError('The TPM state directory must not be a symbolic link')
    state=state.resolve()
    setup = Path(setup_binary) if setup_binary else Path(binary).parent/'swtpm_setup'
    if not setup.is_file(): raise RuntimeError('Install the Virtual TPM component first')
    if not banks or any(b not in ('sha1','sha256','sha384','sha512') for b in banks.split(',')):
        raise ValueError('Choose valid PCR banks, including sha256')
    if 'sha256' not in banks.split(','): raise ValueError('Include sha256 in the PCR banks')
    if ek not in ('rsa2048','rsa3072','rsa4096','ecc256','ecc384'):
        raise ValueError('Unsupported endorsement-key algorithm')
    state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (state.parent/('.'+state.name+'.initialize.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state.exists() and any(state.iterdir()):
            raise RuntimeError('Existing TPM state was preserved. Use Restore state to select a known-good backup, '
                               'or the explicit New EK + certificates action if you intend to replace its keys.')
        staging=Path(tempfile.mkdtemp(prefix='.tpm-initialize-',dir=state.parent))
        command = [str(setup),'--tpm2','--tpmstate',str(staging),'--tpm',str(binary)+' socket',
                   '--createek','--pcr-banks',banks]
        command += ['--ecc'] if ek.startswith('ecc') else ['--rsa-keysize',ek[3:]]
        if certificates: command += ['--create-ek-cert','--create-platform-cert']
        if lock_nvram: command += ['--lock-nvram']
        try:
            result = subprocess.run(command,env=dict(os.environ,XETAL_KVM_DATA=str(portable.data_root())),
                                    capture_output=True,text=True,timeout=180)
            if result.returncode or not (staging/'tpm2-00.permall').is_file():
                raise RuntimeError('TPM initialization failed; you can retry without replacing any guest keys.\n'+
                                   (result.stdout+result.stderr)[-6000:])
            for item in staging.iterdir():
                if item.is_file() and not item.is_symlink(): item.chmod(0o600)
            if state.exists():state.rmdir() # Fails if anything was added concurrently.
            staging.rename(state)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return 'Private TPM initialized with new guest keys and certificates.\n'+str(state)
