#!/usr/bin/env bash
#
# Build/load the ported native-MSR KVM modules for 7.2.11-arch1-1.
#
# Usage:
#   ./build-kvm.sh --build-only build + validate, also from an older running kernel
#   ./build-kvm.sh              build + load for this boot only (default)
#   ./build-kvm.sh --install    also overwrite the distro modules (persists across reboots)
#   ./build-kvm.sh --restore    put the distro modules back and reload them
#
# Differences from the original 6.18.5-zen script, all deliberate:
#   * SourceDir points at the prepared 7.2.11 tree in this directory.
#   * Build-only uses the target kernel's configuration and local build tools;
#     all load/install/restore operations require that exact running kernel.
#   * Loading no longer implies installing.  Overwriting the distro's kvm.ko is
#     opt-in via --install, and the originals are backed up first.
#   * KVM_CPUID_CLEAR_BUFFERS defaults to 1, keeping the VERW CPU-buffer clear
#     (MDS / AMD Transient Scheduler Attacks mitigation) on the burst re-entry
#     path.  The original defaulted to 0, which disables that mitigation.
#     Export KVM_CPUID_CLEAR_BUFFERS=0 to get the original behaviour.

set -euo pipefail

readonly ScriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TargetRelease="7.2.11-arch1-1"
readonly SourceDir="$ScriptDir/src/linux/src/linux-7.2.11"
readonly ToolchainDir="$ScriptDir/src/toolchain-7.2.11"
readonly RunningRelease="$(uname -r)"
readonly BuildDir="$ScriptDir"
readonly InstallDir="/usr/lib/modules/$RunningRelease/kernel/arch/x86/kvm"
readonly BackupDir="${XETAL_KVM_MODULE_BACKUPS:-$ScriptDir/distro-modules-backup}/$TargetRelease"
readonly BuildJobs="${KVM_BUILD_JOBS:-$(nproc)}"

readonly Avic="${KVM_AVIC:-0}"
readonly IpiVirtualization="${KVM_IPIV:-0}"
readonly PostedInterrupts="${KVM_POSTED_IRQS:-0}"
readonly CpuidBurstMax="${KVM_CPUID_BURST_MAX:-4096}"
readonly CpuidClearBuffers="${KVM_CPUID_CLEAR_BUFFERS:-1}"
readonly PrivateMsrBurst="${KVM_PRIVATE_MSR_BURST:-1}"
readonly PrivateMsrBurstMax="${KVM_PRIVATE_MSR_BURST_MAX:-4096}"
# 0 leaves VMMCALL un-intercepted, so it raises #UD in the guest as it does on
# bare metal.  This gives up KVM's paravirtual hypercall ABI for every guest on
# this host; set KVM_INTERCEPT_VMMCALL=1 if a guest needs KVM PV features.
readonly InterceptVmmcall="${KVM_INTERCEPT_VMMCALL:-0}"
# 1 keeps CPUID intercepted, which is REQUIRED at guest boot: Windows enumerates
# CPU topology from CPUID early in startup. Drop it only after the guest is up,
# via this folder's vmstealth75.sh after Windows reaches the desktop.
readonly InterceptCpuid="${KVM_INTERCEPT_CPUID:-1}"

if (($# > 1)); then
    printf 'expected at most one option; see %s --help\n' "$0" >&2
    exit 1
fi

Mode="load"
case "${1:-}" in
    --build-only) Mode="build" ;;
    --install) Mode="install" ;;
    --restore) Mode="restore" ;;
    --help|-h)
        printf 'Usage: %s [--build-only|--install|--restore]\n' "$0"
        printf 'Target: %s. Default: build and load for this boot.\n' "$TargetRelease"
        printf '%s\n' '--build-only builds and validates without loading or installing modules.'
        exit 0
        ;;
    "")        Mode="load" ;;
    *)         printf 'unknown argument: %s\n' "$1" >&2; exit 1 ;;
esac
readonly Mode

ModulePath() {
    if [[ "${XETAL_KVM_MEMORY_MODULES:-0}" == 1 ]]; then
        case "$1" in
            kvm.ko) printf '%s' "${XETAL_KVM_CORE_IMAGE:?}" ;;
            kvm-amd.ko) printf '%s' "${XETAL_KVM_AMD_IMAGE:?}" ;;
            *) return 1 ;;
        esac
    else
        printf '%s/%s' "$BuildDir" "$1"
    fi
}
if [[ "${XETAL_KVM_MEMORY_MODULES:-0}" == 1 && "$Mode" == install ]]; then
    printf 'This edition loads modules for the current boot only.\n' >&2
    exit 1
fi

declare -a KvmHolderModules=()

Info() { printf '[KVM] %s\n' "$*"; }
Fail() { printf '[KVM] ERROR: %s\n' "$*" >&2; exit 1; }

RequireTargetKernel() {
    [[ "$RunningRelease" == "$TargetRelease" ]] ||
        Fail "target is $TargetRelease, running kernel is $RunningRelease; use --build-only to compile without loading"
}

BuildModules() {
    if [[ "$Mode" == "build" ]]; then
        Fail "Use the matching sources-kvm package to rebuild; these are the published binaries."
    fi
    grep -q AuthenticAMD /proc/cpuinfo || Fail "This custom module is for AMD hosts only"
}

ValidateModules() {
    local Module Vermagic

    for Module in kvm.ko kvm-amd.ko; do
        if [[ "${XETAL_KVM_MEMORY_MODULES:-0}" == 1 ]]; then
            /usr/bin/python3 "${XETAL_KVM_IMAGE_HELPER:?}" check "$(ModulePath "$Module")" "$TargetRelease" || Fail "$Module has incompatible metadata"
            continue
        fi
        [[ -f "$(ModulePath "$Module")" ]] || Fail "$Module is unavailable"
        Vermagic="$(modinfo -F vermagic "$(ModulePath "$Module")")"
        [[ "$Vermagic" == "$TargetRelease "* ]] ||
            Fail "$Module has incompatible vermagic: $Vermagic"
    done
    Info "vermagic matches $TargetRelease"
}

LoadModule() {
    local Module="$1"
    shift
    if [[ "${XETAL_KVM_MEMORY_MODULES:-0}" == 1 ]]; then
        /usr/bin/python3 "${XETAL_KVM_IMAGE_HELPER:?}" load "$(ModulePath "$Module")" "$@"
    else
        sudo insmod "$(ModulePath "$Module")" "$@"
    fi
}

DescribeKvmUser() {
    # Print "PID (comm) [container NAME]" for a process holding /dev/kvm.
    local Pid="$1" Comm Container CgroupId

    Comm="$(tr -d '\0' < "/proc/$Pid/comm" 2>/dev/null || echo unknown)"
    CgroupId="$(sed -n 's/.*docker-\([0-9a-f]\{12\}\).*/\1/p' "/proc/$Pid/cgroup" 2>/dev/null | head -1)"
    if [[ -n "$CgroupId" ]] && command -v docker >/dev/null 2>&1; then
        Container="$(docker ps --no-trunc --format '{{.ID}} {{.Names}}' 2>/dev/null |
                     awk -v id="$CgroupId" 'index($1, id) == 1 { print $2; exit }')"
    fi
    printf '  PID %s (%s)%s\n' "$Pid" "$Comm" \
        "${Container:+ in container $Container}"
}

RequireIdleKvm() {
    # NOTE: fuser cannot see processes in other mount namespaces, so a VM
    # inside a container looks idle to it.  Scan /proc directly (host-wide)
    # and cross-check the module refcount, which counts VMs regardless of
    # namespace.
    local Pid Link RefCount
    local -a Users=()

    for Link in /proc/[0-9]*/fd/*; do
        [[ "$(readlink -f "$Link" 2>/dev/null)" == /dev/kvm ]] || continue
        Pid="${Link#/proc/}"
        Pid="${Pid%%/*}"
        [[ " ${Users[*]-} " == *" $Pid "* ]] || Users+=("$Pid")
    done

    RefCount="$(awk '$1 == "kvm_amd" { print $3 }' /proc/modules 2>/dev/null)"

    if ((${#Users[@]})); then
        printf '[KVM] ERROR: these processes still hold /dev/kvm:\n' >&2
        for Pid in "${Users[@]}"; do DescribeKvmUser "$Pid" >&2; done
        printf '[KVM] Stop them (for a container: docker stop <name>) and retry.\n' >&2
        exit 1
    fi

    if [[ -n "$RefCount" && "$RefCount" != "0" ]]; then
        Fail "kvm_amd refcount is $RefCount but no /dev/kvm holder was found; something is still using KVM"
    fi
}

ReleaseKvmHolders() {
    local Module
    local -a LoadedModules=()

    for Module in vboxnetadp vboxnetflt vboxdrv; do
        if [[ -d "/sys/module/$Module" ]]; then
            LoadedModules+=("$Module")
            KvmHolderModules=("$Module" "${KvmHolderModules[@]}")
        fi
    done

    ((${#LoadedModules[@]})) || return 0
    Info "Temporarily unloading idle VirtualBox KVM holders"
    sudo modprobe -r "${LoadedModules[@]}"
}

RestoreKvmHolders() {
    local Module

    for Module in "${KvmHolderModules[@]}"; do
        sudo modprobe "$Module" || Info "Warning: could not restore $Module"
    done
    KvmHolderModules=()
}

UnloadKvm() {
    [[ ! -d /sys/module/kvm_amd ]] || sudo modprobe -r kvm_amd
    [[ ! -d /sys/module/kvm ]] || sudo modprobe -r kvm
}

LoadModules() {
    UnloadKvm

    # insmod does not resolve dependencies; modprobe -r may have removed these.
    if ! sudo modprobe irqbypass ||
       ! LoadModule kvm.ko ignore_msrs=0 report_ignored_msrs=1; then
        sudo modprobe kvm_amd || true
        Fail "new kvm.ko did not load"
    fi

    sudo modprobe ccp || true
    if ! LoadModule kvm-amd.ko \
        avic="$Avic" \
        enable_ipiv="$IpiVirtualization" \
        enable_device_posted_irqs="$PostedInterrupts" \
        cpuid_leaf_0_burst_max="$CpuidBurstMax" \
        cpuid_leaf_0_burst_clear_buffers="$CpuidClearBuffers" \
        private_msr_gp_burst="$PrivateMsrBurst" \
        private_msr_gp_burst_max="$PrivateMsrBurstMax" \
        intercept_vmmcall="$InterceptVmmcall" \
        intercept_cpuid="$InterceptCpuid"; then
        sudo rmmod kvm || true
        sudo modprobe kvm_amd || true
        Fail "new kvm-amd.ko did not load"
    fi

    ReportActiveParameters
}

ReportActiveParameters() {
    local Param
    Info "Unknown MSR compatibility=$(</sys/module/kvm/parameters/ignore_msrs), reporting=$(</sys/module/kvm/parameters/report_ignored_msrs)"
    for Param in avic enable_ipiv enable_device_posted_irqs \
                 cpuid_leaf_0_burst cpuid_leaf_0_burst_max \
                 cpuid_leaf_0_burst_clear_buffers \
                 private_msr_gp_burst private_msr_gp_burst_max \
                 intercept_vmmcall intercept_cpuid; do
        [[ -r "/sys/module/kvm_amd/parameters/$Param" ]] &&
            Info "kvm_amd.$Param=$(<"/sys/module/kvm_amd/parameters/$Param")"
    done
    if [[ "$(</sys/module/kvm_amd/parameters/cpuid_leaf_0_burst_clear_buffers)" == "N" ]]; then
        Info "WARNING: CPU-buffer clearing is OFF on the burst re-entry path."
        Info "WARNING: this weakens MDS/TSA guest->host protection."
    fi
}

RestoreKvmDevice() {
    sudo udevadm trigger --action=add /sys/class/misc/kvm
    sudo udevadm settle
    [[ -c /dev/kvm ]] || Fail "/dev/kvm was not recreated"
}

BackupDistroModules() {
    local Module Source

    [[ ! -d "$BackupDir" ]] || { Info "Backup already exists at $BackupDir"; return 0; }

    mkdir -p "$BackupDir"
    for Module in kvm.ko kvm-amd.ko; do
        Source="$(find "$InstallDir" -name "$Module*" -print -quit 2>/dev/null || true)"
        [[ -n "$Source" ]] || Fail "could not find distro $Module under $InstallDir"
        cp -a "$Source" "$BackupDir/"
    done
    Info "Backed up distro modules to $BackupDir"
}

InstallModules() {
    BackupDistroModules
    sudo install -Dm644 "$BuildDir/kvm.ko" "$InstallDir/kvm.ko"
    sudo install -Dm644 "$BuildDir/kvm-amd.ko" "$InstallDir/kvm-amd.ko"
    # Remove distro-compressed variants so modprobe cannot pick the old ones.
    sudo rm -f "$InstallDir/kvm.ko.zst" "$InstallDir/kvm-amd.ko.zst"
    sudo depmod -a "$RunningRelease"
    Info "Installed modified modules into $InstallDir"
    Info "These now load at every boot until the linux package is updated."
    Info "Undo with: $0 --restore"
}

RestoreModules() {
    local Module

    RequireIdleKvm
    trap RestoreKvmHolders EXIT
    ReleaseKvmHolders
    UnloadKvm

    if [[ -d "$BackupDir" ]]; then
        # A previous --install overwrote the on-disk modules; put them back.
        sudo rm -f "$InstallDir/kvm.ko" "$InstallDir/kvm-amd.ko"
        for Module in "$BackupDir"/*; do
            sudo install -Dm644 "$Module" "$InstallDir/$(basename "$Module")"
        done
        sudo depmod -a "$RunningRelease"
        Info "Reinstalled distro modules from $BackupDir"
    else
        # Load-only session: the distro modules on disk were never touched,
        # so unloading and modprobing is all that is needed.
        Info "No backup needed; the on-disk distro modules were never modified"
    fi

    sudo modprobe kvm_amd
    RestoreKvmDevice
    RestoreKvmHolders
    trap - EXIT
    Info "Distro KVM modules are loaded again"
}

[[ "$Mode" == "build" ]] || RequireTargetKernel

if [[ "$Mode" == "restore" ]]; then
    RestoreModules
    exit 0
fi

BuildModules
ValidateModules
if [[ "$Mode" == "build" ]]; then
    Info "Built and validated modules in $BuildDir"
    exit 0
fi
RequireIdleKvm
trap RestoreKvmHolders EXIT
ReleaseKvmHolders
LoadModules
RestoreKvmDevice
[[ "$Mode" != "install" ]] || InstallModules
RestoreKvmHolders
trap - EXIT

if [[ "$Mode" == "install" ]]; then
    Info "Loaded and installed modified KVM modules for $RunningRelease"
else
    Info "Loaded modified KVM modules for $RunningRelease (this boot only)"
    Info "Reboot to go back to the distro modules, or run: $0 --restore"
fi
