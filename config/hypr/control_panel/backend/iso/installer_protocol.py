"""Private, bounded messages between the restore shell and its graphical UI."""
import json
import socket

LIMIT = 1024 * 1024


def request(endpoint, page):
    payload = json.dumps(page, ensure_ascii=True).encode() + b'\n'
    if len(payload) > LIMIT:
        raise ValueError('Installer page is too large.')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(5)
        peer.connect(str(endpoint))
        peer.sendall(payload)
        peer.settimeout(None)  # The user may take as long as needed to decide.
        with peer.makefile('rb') as stream:
            data = stream.readline(LIMIT + 1)
    if not data.endswith(b'\n') or len(data) > LIMIT:
        raise RuntimeError('The graphical installer closed before answering.')
    value = json.loads(data)
    if (not isinstance(value, dict) or type(value.get('status')) is not int
            or value['status'] not in (0, 1, 10, 20)
            or not isinstance(value.get('result', ''), str)):
        raise ValueError('Invalid installer response.')
    return value
