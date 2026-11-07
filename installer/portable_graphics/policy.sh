#!/bin/sh
# Select only among already installed drivers, before udev's GPU coldplug.
# Optional path arguments are used by fixture tests; systemd supplies none.
set -eu
gpu_sysfs=${1:-/sys/bus/pci/devices}
gpu_config=${2:-/etc/hyperfusion/graphics}
gpu_run=${3:-/run}
gpu_seen=0
gpu_unknown=0
gpu_mode=nvidia

for gpu_device in "$gpu_sysfs"/*; do
    [ -r "$gpu_device/class" ] && [ -r "$gpu_device/vendor" ] && [ -r "$gpu_device/device" ] || continue
    read -r gpu_class < "$gpu_device/class"
    case "$gpu_class" in 0x03*) ;; *) continue ;; esac
    read -r gpu_vendor < "$gpu_device/vendor"
    [ "$gpu_vendor" = 0x10de ] || continue
    gpu_seen=$((gpu_seen + 1))
    read -r gpu_id < "$gpu_device/device"
    if ! grep -Fqx "$gpu_id" "$gpu_config/nvidia-supported.txt"; then
        gpu_unknown=$((gpu_unknown + 1))
    fi
done

# With no NVIDIA card, leave the current driver ready for modern hotplug.
# Mixed current/legacy NVIDIA systems use one Nouveau stack for all NVIDIA GPUs.
if [ "$gpu_unknown" -gt 0 ] && [ -f "$gpu_config/nouveau-enabled" ]; then
    gpu_mode=nouveau
fi
mkdir -p "$gpu_run/modprobe.d"
gpu_temporary="$gpu_run/modprobe.d/.hyperfusion-gpu-$$"
trap 'rm -f "$gpu_temporary"' EXIT HUP INT TERM
{
    printf '# Hyper Fusion: %s; NVIDIA display devices=%s, unsupported=%s\n' "$gpu_mode" "$gpu_seen" "$gpu_unknown"
    printf 'blacklist nova_core\nblacklist nova_drm\n'
    if [ "$gpu_mode" = nouveau ]; then
        printf 'blacklist nvidia\nblacklist nvidia_modeset\nblacklist nvidia_uvm\nblacklist nvidia_drm\n'
    else
        printf 'blacklist nouveau\nsoftdep nvidia post: nvidia-uvm nvidia-drm\n'
        printf 'options nvidia NVreg_TemporaryFilePath=/var/tmp\noptions nvidia_drm modeset=1 fbdev=1\n'
    fi
} > "$gpu_temporary"
# /run takes precedence over the same package-owned filename in /usr/lib.
# Administrators' /etc/modprobe.d overrides retain their higher priority.
mv -f "$gpu_temporary" "$gpu_run/modprobe.d/nvidia-utils.conf"
printf '%s\n' "$gpu_mode" > "$gpu_run/hyperfusion-gpu-selection"
printf 'Hyper Fusion graphics: %s (NVIDIA devices: %s, unlisted: %s). No packages changed.\n' "$gpu_mode" "$gpu_seen" "$gpu_unknown"
