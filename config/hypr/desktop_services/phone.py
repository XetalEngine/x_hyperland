"""KDE Connect actions and official WhatsApp linked-device links."""
from pathlib import Path
import re
import shutil
from urllib.parse import parse_qs, urlencode, urlparse
from .common import run


def devices():
    if not shutil.which('kdeconnect-cli'):return []
    available=set(run(['kdeconnect-cli','--list-available','--id-only']).splitlines())
    result=[]
    for line in run(['kdeconnect-cli','--list-devices','--id-name-only']).splitlines():
        ident,separator,name=line.partition(' ')
        if separator and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ident):
            result.append(dict(id=ident,name=name,available=ident in available))
    return result


def action(device, operation, value='', destination=''):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',device or ''):raise ValueError('Choose a phone first.')
    if operation not in ('pair','unpair','ring','share','share-text','send-sms'):raise ValueError('Unknown phone action.')
    argv=['kdeconnect-cli','--device',device,'--'+operation]
    if operation=='share':
        path=Path(value).expanduser().resolve(strict=True)
        if not path.is_file():raise ValueError('Choose a file to send.')
        argv.append(str(path))
    elif operation in ('share-text','send-sms'):
        if not value.strip() or len(value)>20000:raise ValueError('Enter a message of up to 20,000 characters.')
        argv.append(value)
    if operation=='send-sms':
        number=re.sub(r'[ ()-]','',destination)
        if not re.fullmatch(r'\+?[0-9]{3,20}',number):raise ValueError('Enter a phone number, including its country code when needed.')
        argv+=['--destination',number]
    return run(argv,timeout=30)


def whatsapp_url(value=''):
    """Map only the official messaging URI to WhatsApp Web; never execute URI text."""
    if not value:return 'https://web.whatsapp.com/'
    parsed=urlparse(value)
    if parsed.scheme!='whatsapp' or (parsed.netloc or parsed.path.strip('/'))!='send':
        raise ValueError('Only whatsapp://send links are supported.')
    query=parse_qs(parsed.query); parameters={}
    number=query.get('phone',[''])[0]
    if number:
        number=re.sub(r'[+ ()-]','',number)
        if not re.fullmatch('[0-9]{3,20}',number):raise ValueError('Invalid WhatsApp phone number.')
        parameters['phone']=number
    message=query.get('text',[''])[0]
    if len(message)>20000:raise ValueError('This WhatsApp message is too long.')
    if message:parameters['text']=message
    return 'https://web.whatsapp.com/send?'+urlencode(parameters)
