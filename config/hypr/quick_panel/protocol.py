"""One bounded request per local connection, including fragmented delivery."""
import json


class Request:
    def __init__(self):self.pending=bytearray();self.done=False
    def feed(self,data):
        if self.done:return None
        self.pending.extend(data)
        if len(self.pending)>4096:self.done=True;raise ValueError('Popup request is too large.')
        if b'\n' not in self.pending:return None
        self.done=True
        value=json.loads(self.pending.split(b'\n',1)[0])
        if not isinstance(value,dict) or value.get('kind') not in ('clock','power'):raise ValueError('Invalid popup request.')
        return value
