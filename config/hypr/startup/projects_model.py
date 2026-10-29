"""Bundled project catalog and read-only community page navigation."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
WORKSPACE = 'special:xetal-startup'


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    icon: Path
    accent: str
    url: str


def catalog(root=ROOT):
    result = []
    for item in json.loads((root/'projects.json').read_text()):
        url = urlsplit(item['url'])
        if (not re.fullmatch(r'[a-z0-9]+', item['id']) or
            url.scheme != 'https' or url.netloc != 'www.xetal.net' or
            url.path != '/community/site/' or parse_qs(url.query) != {'p': [item['id']]} or
            Path(item['icon']).name != item['icon'] or not re.fullmatch(r'#[0-9a-fA-F]{6}', item['accent'])):
            raise ValueError('Invalid project catalog entry')
        result.append(Project(item['id'], item['name'], item['description'],
                              root/'assets/projects'/item['icon'], item['accent'], item['url']))
    if not result or len({p.id for p in result}) != len(result):
        raise ValueError('The project catalog is empty or contains duplicate entries')
    return result


def hide_dashboard():
    """Hide only this special workspace; never toggle it open by accident."""
    response = subprocess.run(['hyprctl', '-j', 'monitors'], capture_output=True, text=True, timeout=3)
    if response.returncode:
        raise RuntimeError('The Hyprland session is unavailable.')
    monitors = json.loads(response.stdout)
    if any(m.get('focused') and m.get('specialWorkspace', {}).get('name') == WORKSPACE for m in monitors):
        response = subprocess.run(['hyprctl', 'dispatch', 'togglespecialworkspace', 'xetal-startup'],
                                  capture_output=True, text=True, timeout=3)
        if response.returncode or response.stdout.strip() != 'ok':
            raise RuntimeError('Could not hide the dashboard.')


def open_project(project, environment):
    # Hide first so a newly opened browser belongs to the ordinary workspace.
    if environment.get('HYPRLAND_INSTANCE_SIGNATURE'):
        hide_dashboard()
    subprocess.Popen(['xdg-open', project.url], env=environment,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
