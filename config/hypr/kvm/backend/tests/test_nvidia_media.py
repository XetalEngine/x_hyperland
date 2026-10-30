"""Build tooling must preserve upstream behavior except the documented offline patch."""
import importlib.util
from pathlib import Path
import re
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_nvidia_offline", ROOT / "scripts/build_nvidia_offline.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def payload():
    path = ROOT / "macos/NVIDIA-Offline/Payloads/2.5.3"
    if not (path / "nullmoth-setup.sh").exists():
        pytest.skip("Local third-party payload archive is not present in this checkout")
    return path


def test_offline_patch_preserves_upstream_setup_outside_two_documented_changes(payload, tmp_path):
    source = (payload / "nullmoth-setup.sh").read_text()
    result = builder.offline_setup(source)
    pattern = r"fetch_kext\(\) \{.*?\n\}\n"
    original_fetch = re.search(pattern, source, re.S).group()
    local_fetch = re.search(pattern, result, re.S).group()
    assert "curl" not in local_fetch and "NULLMOTH_OFFLINE_KEXTS" in local_fetch
    assert "shasum -a 256" in local_fetch and '"$s"' in local_fetch
    restored = result.replace("# vmstart2: support kexts come from the verified local payload. No download fallback.\n", "")
    restored = restored.replace(local_fetch, original_fetch).replace(' -nvaccelnoheadless"', '"', 1)
    assert restored == source
    path = tmp_path / "offline.sh"
    path.write_text(result)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_support_archives_have_the_layout_expected_by_the_offline_helper(payload):
    names = ["Lilu.kext", "AMFIPass.kext", "USBToolBox.kext", "RestrictEvents.kext"]
    for name in names:
        with zipfile.ZipFile(payload / "Kexts" / (name + ".zip")) as archive:
            assert name + "/Contents/Info.plist" in archive.namelist()


def test_upstream_drift_stops_building_until_reviewed(payload):
    source = (payload / "nullmoth-setup.sh").read_text()
    with pytest.raises(ValueError, match="defaults"):
        builder.offline_setup(source.replace('WANT_ARGS="nvfb=1', 'WANT_ARGS="-nvaccelnoheadless nvfb=1', 1))
