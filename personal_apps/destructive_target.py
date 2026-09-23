"""Two independent gates for local tools that can destroy database state.

The connection URL is evidence of what is bound, never authorization to
modify it. Authorization comes from an explicit target string supplied by the
operator and from a separately provisioned registry file naming that target.
Neither value is inferred or written by this module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


TARGET_ENV = 'RADAR_DESTRUCTIVE_TEST_TARGET'
REGISTRY_ENV = 'RADAR_DESTRUCTIVE_TEST_REGISTRY'
REGISTRY_VERSION = 1
PROTECTED_DATABASES = frozenset({'personal_apps', 'coc_stats'})
SAFE_QUERY_OPTIONS = {'charset': 'utf8mb4'}


class DestructiveTargetRefused(RuntimeError):
    """The bound database has not passed both destructive-operation gates."""


def target_for(url) -> str:
    """Return the actual bound host/port/database tuple in operator syntax."""
    host = url.host or ''
    database = url.database or ''
    port = url.port
    if port is None and url.get_backend_name() in {'mysql', 'mariadb'}:
        port = 3306
    rendered_host = f'[{host}]' if ':' in host and not host.startswith('[') else host
    return f'{rendered_host}:{port or 0}/{database}'


def require(url, *, env=None, protected=PROTECTED_DATABASES) -> str:
    """Require exact opt-in and independent registration before any SQL.

    This function only examines the already-parsed URL, environment and a
    local registry file. Callers can and do invoke it before opening a
    database connection, including before DROP DATABASE on a schema that may
    not exist yet.
    """
    # MySQL dialects merge URL query values into the driver's connect kwargs;
    # `?database=...`, `?host=...` and `?unix_socket=...` can therefore route
    # somewhere other than the tuple rendered from URL attributes. The
    # application's one non-routing query option is exact and deliberately
    # allowlisted; everything else fails closed.
    refused_query = {
        name: value for name, value in url.query.items()
        if SAFE_QUERY_OPTIONS.get(name) != value
    }
    if refused_query:
        options = ', '.join(sorted(refused_query))
        raise DestructiveTargetRefused(
            f'connection URL query/socket options are unsupported for '
            f'destructive Radar work ({options}); use only an explicit '
            'host, port and database URL')

    values = os.environ if env is None else env
    actual = target_for(url)
    database = (url.database or '').lower()
    if database in {name.lower() for name in protected}:
        raise DestructiveTargetRefused(
            f'{actual} names a protected database; destructive Radar tools '
            'will not run there')

    opted = (values.get(TARGET_ENV) or '').strip()
    if not opted:
        raise DestructiveTargetRefused(
            f'destructive Radar work is not opted in for the actual bound '
            f'target; set {TARGET_ENV}={actual} explicitly')
    if opted != actual:
        raise DestructiveTargetRefused(
            f'{TARGET_ENV}={opted} does not match the actual bound target '
            f'{actual}; correct the explicit opt-in rather than deriving it '
            'from the connection string')

    raw_registry = (values.get(REGISTRY_ENV) or '').strip()
    if not raw_registry:
        raise DestructiveTargetRefused(
            f'{actual} passed the explicit opt-in but has no independent '
            f'registration; set {REGISTRY_ENV} to an absolute, provisioned '
            'JSON registry file')
    registry = Path(raw_registry)
    if not registry.is_absolute():
        raise DestructiveTargetRefused(
            f'{REGISTRY_ENV} must be an absolute path, got {raw_registry!r}')
    try:
        document = json.loads(registry.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DestructiveTargetRefused(
            f'cannot read the provisioned destructive-target registry '
            f'{registry}: {type(exc).__name__}') from exc
    if not isinstance(document, dict):
        raise DestructiveTargetRefused(
            f'{registry} is not a version {REGISTRY_VERSION} Radar '
            'destructive-target registry (top level must be an object)')
    targets = document.get('targets')
    if (document.get('version') != REGISTRY_VERSION
            or not isinstance(targets, list)):
        raise DestructiveTargetRefused(
            f'{registry} is not a version {REGISTRY_VERSION} Radar '
            'destructive-target registry')
    if actual not in targets:
        raise DestructiveTargetRefused(
            f'{actual} is not registered in the independently provisioned '
            f'file {registry}')
    return actual
