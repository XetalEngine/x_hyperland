"""Share native protocol roles without occupying the theme's `runtime` module name."""


def window_metadata(hypr):
    """An unavailable/older adapter must never make a popup look like a main window."""
    try:
        metadata = hypr.query('xetal-windows')
    except (OSError, ValueError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def geometry_managed(client, metadata):
    # clients and xetal-windows are separate snapshots. Stable IDs prevent an
    # address reused between queries from borrowing the previous window's role.
    stable_id = client.get('stableId')
    return (isinstance(metadata, dict) and metadata.get('geometry_managed') is True
            and isinstance(stable_id, str) and bool(stable_id)
            and metadata.get('stableId') == stable_id)
