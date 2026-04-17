import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigError(Exception):
    pass


DEFAULT_CONFIG = """\
[output]
base_dir = "~/Downloads"

[crawl]
default_max_pages = 0
default_format = "markdown"
"""

DEFAULT_CONFIG_PATH = Path("~/.config/doublefinger/config.toml").expanduser()


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)

    try:
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Malformed config file at {config_path}: {exc}") from exc

    cfg.setdefault("output", {})
    cfg.setdefault("crawl", {})
    cfg["output"].setdefault("base_dir", "~/Downloads")
    cfg["crawl"].setdefault("default_max_pages", 0)
    cfg["crawl"].setdefault("default_format", "markdown")

    cfg["output"]["base_dir"] = str(Path(cfg["output"]["base_dir"]).expanduser())

    return cfg


def apply_overrides(cfg: dict, output_dir: str = None, max_pages: int = None) -> dict:
    result = {
        "output": dict(cfg["output"]),
        "crawl": dict(cfg["crawl"]),
    }
    if output_dir is not None:
        result["output"]["base_dir"] = output_dir
    if max_pages is not None:
        result["crawl"]["default_max_pages"] = max_pages
    return result
