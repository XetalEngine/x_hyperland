"""Per-installation download credentials, created only when downloading KVM."""
from pathlib import Path
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

import portable


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an installation credential to a redirect destination.
        return None


def installation():
    path=portable.ROOT.parent/'.xetal-update.json'
    try:record=json.loads(path.read_text())
    except (OSError,ValueError):record={}
    if (record.get('repository')!='https://github.com/XetalEngine/x_hyperland.git'
            or not re.fullmatch('[a-f0-9]{40}',str(record.get('revision','')))):
        raise RuntimeError('Install x_hyperland with x_hyperinstall.sh before downloading KVM components.')
    return record['revision']


def credential(site, root, *, renew=False):
    from packages import atomic_json
    revision=installation();path=Path(root)/'download-access.json'
    try:saved=json.loads(path.read_text())
    except (OSError,ValueError):saved={}
    if not renew and saved.get('site')==site and re.fullmatch('[a-f0-9]{64}',str(saved.get('token',''))):
        return saved['token']
    identifier=saved.get('installation') or str(uuid.uuid4())
    body=json.dumps({'app':'x_hyperland','revision':revision,'installation':identifier}).encode()
    request=urllib.request.Request(site+'/api/kvm-access.php',data=body,
        headers={'Content-Type':'application/json','User-Agent':'XetalKVM/1'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=30) as response:
        result=json.loads(response.read(4096))
    token=result.get('token','')
    if not re.fullmatch('[a-f0-9]{64}',token):raise RuntimeError('KVM installation registration failed.')
    atomic_json(path,{'site':site,'installation':identifier,'token':token})
    path.chmod(0o600)
    return token


def open_component(site, root, filename):
    for retry in (False,True):
        token=credential(site,root,renew=retry)
        request=urllib.request.Request(site+'/api/kvm-download.php?file='+urllib.parse.quote(filename),
            headers={'X-Xetal-KVM-Token':token,'User-Agent':'XetalKVM/1'})
        try:return urllib.request.build_opener(NoRedirect).open(request,timeout=45)
        except urllib.error.HTTPError as error:
            if error.code!=401 or retry:raise
            error.close()
    raise RuntimeError('KVM download authorization failed.')
