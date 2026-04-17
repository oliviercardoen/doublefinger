"""Configuration loading and management for doublefinger.

Reads from ~/.config/doublefinger/config.toml (TOML format).
Creates the file with default values on first run if it does not exist.
Uses tomllib (Python 3.11+) or tomli as a backport for older versions.
"""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigError(Exception):
    """Raised when the config file cannot be parsed."""


# Written verbatim when no config file exists yet.
DEFAULT_CONFIG = """\
[output]
base_dir = "~/Downloads"

[crawl]
default_max_pages = 0
default_format = "markdown"
"""

DEFAULT_CONFIG_PATH = Path("~/.config/doublefinger/config.toml").expanduser()


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load configuration from a TOML file, creating it with defaults if absent.

    Args:
        config_path: Path to the TOML config file. Defaults to
            ~/.config/doublefinger/config.toml.

    Returns:
        A dict with at least the keys ``output`` and ``crawl``, each
        containing their respective settings. ``output.base_dir`` is
        always returned as an absolute path (tilde expanded).

    Raises:
        ConfigError: If the file exists but cannot be parsed as valid TOML.
    """
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)

    try:
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Malformed config file at {config_path}: {exc}") from exc

    # Fill in any keys that may be missing from a partial config file.
    cfg.setdefault("output", {})
    cfg.setdefault("crawl", {})
    cfg["output"].setdefault("base_dir", "~/Downloads")
    cfg["crawl"].setdefault("default_max_pages", 0)
    cfg["crawl"].setdefault("default_format", "markdown")

    # Always expose base_dir as an absolute path so callers never see a tilde.
    cfg["output"]["base_dir"] = str(Path(cfg["output"]["base_dir"]).expanduser())

    return cfg


def apply_overrides(cfg: dict, output_dir: str = None, max_pages: int = None) -> dict:
    """Return a new config dict with CLI flag values merged on top.

    Only non-None arguments override the corresponding config value, so
    callers can pass only the flags that were actually supplied by the user.

    Args:
        cfg: Base configuration dict as returned by :func:`load_config`.
        output_dir: If provided, replaces ``cfg["output"]["base_dir"]``.
        max_pages: If provided, replaces ``cfg["crawl"]["default_max_pages"]``.

    Returns:
        A new dict (shallow copy of each section) with the requested
        overrides applied. The original ``cfg`` is not mutated.
    """
    result = {
        "output": dict(cfg["output"]),
        "crawl": dict(cfg["crawl"]),
    }
    if output_dir is not None:
        result["output"]["base_dir"] = output_dir
    if max_pages is not None:
        result["crawl"]["default_max_pages"] = max_pages
    return result
