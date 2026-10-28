"""Read-only image loading and natural folder order."""
import os
from pathlib import Path
import re
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColorSpace, QImageReader


def local_path(value):
    value = str(value)
    if value.startswith('file:'):
        url = QUrl(value)
        if not url.isLocalFile() or url.host() not in ('', 'localhost'):
            raise ValueError('Choose an image on this computer.')
        value = url.toLocalFile()
    elif '://' in value:
        raise ValueError('Choose an image on this computer.')
    # Preserve symlink names so navigation stays in the folder that was opened.
    return Path(os.path.abspath(os.path.expanduser(value)))


def extensions():
    return {bytes(x).decode().lower() for x in QImageReader.supportedImageFormats()} - {'pdf'}


def natural_key(path):
    return [int(s) if s.isdigit() else s.casefold() for s in re.split(r'(\d+)', path.name)]


def folder_images(current):
    supported = extensions()
    try:
        files = [p for p in current.parent.iterdir() if p.suffix[1:].lower() in supported and p.is_file()]
    except OSError:
        files = []
    if current not in files:
        files.append(current)
    return sorted(files, key=lambda p: (natural_key(p), p.name))


def load(path):
    if not path.is_file():
        raise ValueError('This image was moved, deleted, or is no longer accessible.')
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image_format = bytes(reader.format()).decode(errors='replace').upper()
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or 'This image format could not be opened.')
    if image.colorSpace().isValid():
        image = image.convertedToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    image.setDevicePixelRatio(1)
    return {'image': image, 'format': image_format,
            'animated': reader.supportsAnimation() and reader.imageCount() != 1,
            'bytes': path.stat().st_size, 'files': folder_images(path)}
