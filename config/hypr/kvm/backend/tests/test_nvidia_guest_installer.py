"""Exercise the real shell wrapper against mock macOS commands in a temporary tree.

Every /Library path and absolute platform tool is replaced before execution.
The upstream/root installer is a recording stub; no driver or firmware runs.
"""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "macos/nvidia-installer/install-driver.sh"


def executable(path, text):
    path.write_text("#!/bin/bash\n" + text + "\n")
    path.chmod(0o755)


@pytest.fixture
def guest(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    runtime = tmp_path / "disc/Runtime"
    runtime.mkdir(parents=True)
    library = tmp_path / "Library"
    (library / "LaunchDaemons").mkdir(parents=True)
    base = library / "Application Support/vmstart2/NVIDIA-2.5.3"
    script = SOURCE.read_text().replace("/Library/", str(library) + "/")
    script = script.replace("PATH=/usr/bin:/bin:/usr/sbin:/sbin;", f"PATH={shlex.quote(str(commands))}:/usr/bin:/bin;")
    for tool in ("sandbox-exec", "kmutil"):
        script = script.replace("/usr/bin/" + tool, str(commands / tool))
    assert not any(line.startswith("BASE=/Library") or line.startswith("JOB=/Library") for line in script.splitlines())
    (runtime / "install-driver.sh").write_text(script)
    executable(commands / "uname", 'case "$1" in -s) echo Darwin;; -m) echo x86_64;; esac')
    executable(commands / "id", "echo 0")
    executable(commands / "stat", 'case "$2" in %u) echo 0;; %Lp) echo 700;; *) exit 9;; esac')
    executable(commands / "chown", "exit 0")
    executable(commands / "shasum", '[ "$1" = -a ] && [ "$2" = 256 ] || exit 9; shift 2; exec sha256sum "$@"')
    executable(commands / "ditto", 'cp -R "$1" "$2"')
    executable(commands / "sw_vers", 'case "$1" in -productVersion) echo "${TEST_OS:-26.7.1}";; *) echo TESTBUILD;; esac')
    executable(commands / "sysctl", 'echo "${TEST_BOOT:-boot1}"')
    executable(commands / "csrutil", 'echo "System Integrity Protection status: ${TEST_SIP:-disabled}."')
    executable(commands / "ioreg", '''
for ((i=0; i<${TEST_GPUS:-1}; i++)); do
cat <<EOF
+-o display$i
  "device-id" = <${TEST_PCI:-84260000}>
  "vendor-id" = <de100000>
  "class-code" = <${TEST_CLASS:-00000300}>
EOF
done''')
    executable(commands / "kmutil", '''
[ "${TEST_READY:-0}" = 1 ] || exit 1
for k in NVRM NVAccel NVRMFB NVRMAGDC; do echo "  123 com.nullmoth.$k (2.5.3)"; done''')
    executable(runtime / "nullmoth-metal-devices", 'echo "${TEST_METAL:-NVIDIA GeForce RTX 4090}"')
    executable(commands / "sandbox-exec", '''
[ "$1" = -p ] && [ "$2" = '(version 1) (allow default) (deny network*)' ] || exit 90
shift 2
exec "$@"''')
    executable(runtime / "nullmoth-setup.offline.sh", '''
echo "$*" >> "$TEST_CALLS"
[ "${TEST_INSTALL_FAIL:-0}" != 1 ] || exit 9
echo 'CHANGE mock OpenCore edits and driver install'
''')
    (runtime / "supported-ids.txt").write_text("2684\n1F02\n2182\n")
    (runtime / "NullMothSafe.efi").write_bytes(b"never executed")
    (runtime / "Kexts").mkdir()
    (runtime / "nullmoth-nvidia-2.5.3.tar.gz").write_bytes(b"never unpacked")
    (runtime / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(runtime.iterdir()) if p.is_file()))
    calls = tmp_path / "calls.txt"
    def run(mode="--start", input="INSTALL\n", **overrides):
        env = dict(os.environ, TEST_CALLS=str(calls), **overrides)
        source = base / "Runtime/install-driver.sh" if mode == "--resume" else runtime / "install-driver.sh"
        result = subprocess.run(["bash", str(source), mode], input=input, text=True,
                                capture_output=True, env=env, timeout=10)
        return result
    return run, base, runtime, calls, library


def test_driver_install_progress_and_actual_metal_check(guest):
    run, base, _, calls, _ = guest
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (base / "State/phase").read_text().strip() == "installed-restart-required"
    entries = calls.read_text().splitlines()
    assert len(entries) == 2 and entries[0].endswith("--dry")
    assert "NVMTL_NO_NVENC=1" in entries[1] and "NVMTL_NO_NVENC_HEVC=1" in entries[1]
    assert not (base / "install.lock").exists()
    assert "FILES INSTALLED" in result.stdout and "READY:" not in result.stdout
    assert "NOT VERIFIED" in run("--status").stdout
    assert "READY:" in run("--status", TEST_READY="1").stdout
    assert "NOT VERIFIED" in run("--status", TEST_READY="1", TEST_METAL="Intel UHD").stdout


def test_security_restart_resumes_once_and_never_on_later_boots(guest):
    run, base, _, calls, library = guest
    result = run(TEST_SIP="enabled")
    assert result.returncode == 0, result.stdout + result.stderr
    job = library / "LaunchDaemons/net.xetal.vmstart2.nvidia-resume.plist"
    assert job.exists() and "waiting-security-restart" in (base / "State/phase").read_text()
    initial_calls = calls.read_text()
    assert run("--resume", TEST_BOOT="boot1").returncode == 0
    assert calls.read_text() == initial_calls and job.exists()
    assert run("--resume", TEST_BOOT="boot2").returncode == 0
    assert not job.exists()
    assert len(calls.read_text().splitlines()) == 4
    assert "installed-restart-required" in (base / "State/phase").read_text()
    assert run("--resume", TEST_BOOT="boot3").returncode == 0
    assert len(calls.read_text().splitlines()) == 4


def test_failed_resume_is_consumed_without_reinstall_loop(guest):
    run, base, _, calls, library = guest
    assert run(TEST_SIP="enabled").returncode == 0
    assert run("--resume", TEST_BOOT="boot2", TEST_INSTALL_FAIL="1").returncode != 0
    recorded = calls.read_text()
    assert (base / "State/phase").read_text().strip() == "failed"
    assert not (library / "LaunchDaemons/net.xetal.vmstart2.nvidia-resume.plist").exists()
    assert run("--resume", TEST_BOOT="boot3").returncode == 0
    assert calls.read_text() == recorded


def test_resume_with_corrupted_staged_files_does_not_repeat(guest):
    run, base, _, calls, library = guest
    assert run(TEST_SIP="enabled").returncode == 0
    (base / "Runtime/NullMothSafe.efi").write_bytes(b"corrupt")
    recorded = calls.read_text()
    assert run("--resume", TEST_BOOT="boot2").returncode == 2
    assert (base / "State/phase").read_text().strip() == "resume-started"
    assert not (library / "LaunchDaemons/net.xetal.vmstart2.nvidia-resume.plist").exists()
    assert run("--resume", TEST_BOOT="boot3").returncode == 0
    assert calls.read_text() == recorded


@pytest.mark.parametrize("env", [{"TEST_OS": "14.7"}, {"TEST_OS": "15.4"}, {"TEST_OS": "27.1"},
                                  {"TEST_GPUS": "0"}, {"TEST_GPUS": "2"}, {"TEST_PCI": "801b0000"}])
def test_unsupported_guest_or_gpu_stops_before_installer(guest, env):
    run, base, _, calls, _ = guest
    assert run(**env).returncode == 2
    assert not calls.exists() and not base.exists()


def test_3d_pci_class_and_turing_rules(guest):
    run, _, _, calls, _ = guest
    assert run(TEST_CLASS="00020300", TEST_PCI="021f0000").returncode == 0
    assert "NVK_CMDPOOL_GPU_UNCACHED=1" in calls.read_text()
    assert "NVMTL_NO_NVENC" not in calls.read_text()


def test_checksum_failure_cannot_execute_helper(guest):
    run, base, runtime, calls, _ = guest
    (runtime / "nullmoth-setup.offline.sh").write_text("exit 0\n")
    assert run().returncode == 2
    assert not calls.exists() and not base.exists()


def test_cancelling_preview_never_installs(guest):
    run, base, _, calls, _ = guest
    assert run(input="no\n").returncode == 0
    assert len(calls.read_text().splitlines()) == 1
    assert calls.read_text().strip().endswith("--dry")
    assert (base / "State/phase").read_text().strip() == "cancelled"


def test_working_same_version_does_not_reinstall(guest):
    run, base, _, calls, library = guest
    (library / "NullMoth").mkdir()
    (library / "NullMoth/driver-version").write_text("2.5.3\n")
    result = run(TEST_READY="1")
    assert result.returncode == 0 and "already working" in result.stdout
    assert not calls.exists() and not base.exists()


def test_real_script_refuses_linux_host_and_has_no_write_in_plan_mode():
    if os.uname().sysname != "Linux":
        pytest.skip("Linux host guard")
    for mode in ("--start", "--resume", "--status"):
        result = subprocess.run(["bash", str(SOURCE), mode], capture_output=True, text=True, timeout=5)
        assert result.returncode == 2 and "run inside" in result.stdout
    result = subprocess.run(["bash", str(SOURCE), "--plan"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and "No automatic reboot" in result.stdout
