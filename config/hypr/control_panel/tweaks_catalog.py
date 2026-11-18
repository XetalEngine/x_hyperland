"""Presentation and strict value ranges for System Tweaks."""


def choice(value, label):
    return {'value': str(value), 'label': label}


def setting(id, category, title, description, *, choices=None, limits=None, details='', default='', restart=False):
    result = dict(id=id, category=category, title=title, description=description,
                  details=details, default=str(default), restart=restart)
    if choices is not None:
        result['choices'] = [choice(v, label) for v, label in choices]
    if limits:
        result.update(minimum=limits[0], maximum=limits[1], suffix=limits[2])
    return result


ON_OFF = [('on', 'Enabled'), ('off', 'Disabled')]
CATALOG = [
    setting('cpu_governor', 'Performance', 'CPU governor', 'Choose how your processor responds to load.',
            details='Only governors supported by every CPU policy are offered. A boot service restores your choice. Powersave with AMD/Intel p-state still scales up under load; it is not an error. Other power-management services can override manual choices.'),
    setting('cpu_energy', 'Performance', 'Energy preference', 'Balance performance, heat and battery life with your CPU driver.',
            details='Available on CPUs with energy-performance preferences. The performance governor owns this preference; use powersave to choose a balance.'),
    setting('cpu_boost', 'Performance', 'CPU turbo boost', 'Allow the processor to run above its base frequency.', choices=ON_OFF,
            details='Disabling boost can reduce heat and power draw. Saved for future boots; it does not change firmware voltage or overclock settings.'),
    setting('gaming', 'Performance', 'Game memory mappings', 'Maximum memory mappings a process may create.', limits=(65530, 2147483642, ''),
            details='Some games and development tools need a larger vm.max_map_count. This sets a limit; it does not reserve that much RAM.', default=1048576),
    setting('nmi_watchdog', 'Performance', 'NMI watchdog', 'Detect hard CPU lockups.', choices=ON_OFF,
            details='Disabling the watchdog removes one source of monitoring overhead and also removes its hard-lockup diagnostics.'),
    setting('zram', 'Memory & storage', 'Compressed swap', 'Set zram0 capacity as a share of installed RAM.', restart=True,
            choices=[('off', 'Disabled'), ('25', '25% of RAM'), ('50', '50% of RAM'), ('100', '100% of RAM')], default='50',
            details='Requires zram-generator. Saved for the next reboot so active swap is never torn down while applications are using it. Existing compression-algorithm settings and other swap devices are retained.'),
    setting('swappiness', 'Memory & storage', 'Swappiness', 'Choose the balance between swapping and reclaiming file cache.', limits=(0, 200, ''), default=60,
            details='The kernel accepts 0–200. Higher values can suit fast compressed swap; there is no single best value for every system.'),
    setting('cache_pressure', 'Memory & storage', 'Filesystem cache pressure', 'Control how eagerly directory and inode caches are reclaimed.', limits=(1, 1000, ''), default=100,
            details='100 is the conventional baseline. Lower values retain more metadata cache; they also leave less memory available for other work.'),
    setting('dirty_ratio', 'Memory & storage', 'Writeback threshold', 'Memory percentage at which writes wait for disk writeback.', limits=(1, 100, '%'), default=20,
            details='Must exceed the background threshold. Selecting a percentage clears the corresponding dirty_bytes override.'),
    setting('dirty_background', 'Memory & storage', 'Background writeback', 'Memory percentage at which background disk writeback starts.', limits=(0, 99, '%'), default=10,
            details='Must be below the writeback threshold. Selecting a percentage clears the corresponding dirty_background_bytes override.'),
    setting('thp', 'Memory & storage', 'Transparent huge pages', 'Choose when applications can use larger memory pages.',
            details='Always: kernel may use them broadly. Madvise: applications opt in. Never: disable transparent huge pages. Explicit huge-page allocations are separate.'),
    setting('io_scheduler', 'Memory & storage', 'Disk I/O scheduler', 'Choose a supported scheduler for your drives.',
            details='Auto selects none for NVMe, mq-deadline for SATA SSDs, and bfq for rotating disks when available. Other choices must be supported by every detected drive.'),
    setting('trim', 'Memory & storage', 'Scheduled SSD TRIM', 'Keep the system’s regular SSD discard schedule enabled.', choices=ON_OFF,
            details='Enables or disables fstrim.timer across boots. Enabling the timer does not immediately run a full manual TRIM.'),
    setting('tmpfs', 'Memory & storage', 'Temporary files in RAM', 'Choose whether /tmp uses RAM-backed temporary storage.', choices=ON_OFF, restart=True,
            details='RAM-backed /tmp can use swap and is cleared at reboot. Changes take effect at the next boot; current temporary files and mounts stay in use until then.'),
    setting('ptrace', 'Security', 'Debugging other processes', 'Set ptrace access for normal users and debuggers.', default='1',
            choices=[('0', '0 · Same-user debugging'), ('1', '1 · Child processes / explicitly allowed debuggers'),
                     ('2', '2 · Administrators only'), ('3', '3 · No tracing · next reboot')],
            details='Mode 0 still requires normal same-user and dumpability checks; it does not allow arbitrary cross-user access. Mode 3 cannot be undone during that boot, so it is saved for the next reboot. If mode 3 is already active, changing to another mode also requires a reboot.'),
    setting('hidepid', 'Security', 'Process visibility', 'Control what other users can see in /proc.', restart=True, default='0',
            choices=[('0', 'Normal process visibility'), ('1', 'Hide other users’ process details'), ('2', 'Hide other users’ process directories')],
            details='Saved in the /proc mount configuration for the next boot. Some monitoring and desktop tools expect normal visibility.'),
    setting('core_dumps', 'Security', 'Crash dump collection', 'Keep or discard crash memory collected by systemd.', choices=ON_OFF,
            details='Crash dumps help debugging and may contain private application data. Disabling collection does not delete existing dumps.'),
    setting('dmesg', 'Security', 'Kernel log access', 'Choose who can read kernel messages with dmesg.',
            choices=[('1', 'Administrators only'), ('0', 'All users')], default='1'),
    setting('ipv6', 'Network', 'IPv6', 'Enable or disable IPv6 on current and future interfaces.', choices=ON_OFF,
            details='Disabling IPv6 can interrupt connections that use it. The policy is saved across reboots.'),
    setting('tcp_congestion', 'Network', 'TCP congestion control', 'Choose an algorithm available in the running kernel.',
            details='Applies to new connections. The list uses algorithms currently available from the kernel, rather than assuming BBR is installed.'),
    setting('tcp_fastopen', 'Network', 'TCP Fast Open', 'Choose where TCP can send data during connection setup.', default='1',
            choices=[('0', 'Disabled'), ('1', 'Clients'), ('2', 'Servers'), ('3', 'Clients and servers')],
            details='Server applications must also opt in. Some network paths do not support Fast Open.'),
    setting('tcp_buffers', 'Network', 'TCP buffer ceiling', 'Upper memory limit for each TCP send/receive buffer.',
            choices=[(n, f'{n} MiB') for n in (16, 32, 64, 128)], default='64',
            details='Higher ceilings can help long, fast network paths, but allow more memory use. This changes TCP buffer limits and the system socket-buffer ceilings.'),
    setting('pacman_downloads', 'System', 'Parallel package downloads', 'Number of package downloads pacman can run together.', limits=(1, 20, ''), default=5),
    setting('pacman_appearance', 'System', 'Package manager appearance', 'Choose how pacman presents terminal output.', default='color',
            choices=[('plain', 'Plain'), ('color', 'Color'), ('candy', 'Color and animated progress')]),
    setting('journal_limit', 'System', 'System journal limit', 'Cap how much space persistent and runtime journals can use.',
            choices=[(n, f'{n} MiB') for n in (128, 256, 512, 1024, 2048)], default='512',
            details='Updates a dedicated journald drop-in and restarts the logging service. Existing archived files are not manually deleted.'),
    setting('inotify_watches', 'System', 'File watcher limit', 'Maximum watches per user for editors, sync tools and development.', limits=(8192, 2097152, ''), default=524288),
    setting('inotify_instances', 'System', 'File watcher instances', 'Maximum independent inotify instances per user.', limits=(128, 8192, ''), default=1024),
    setting('hidden_files', 'Desktop', 'Show hidden files by default', 'Choose the default for folders opened in Fusion Files.', choices=ON_OFF,
            details='Saved as a Fusion Files preference. Existing per-folder view choices keep their own setting. Reopen Fusion Files to pick up the new default.'),
]
BY_ID = {row['id']: row for row in CATALOG}
for key in ('tcp_buffers', 'journal_limit'):
    BY_ID[key]['unit'] = ' MiB'
