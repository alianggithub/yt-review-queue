"""Typed, non-secret application configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os

import yaml


def _data_home() -> Path:
    """Get the data home directory from env or default to current location."""
    return Path(os.environ.get("YT_REVIEW_QUEUE_DATA_HOME", "var")).expanduser()


@dataclass(slots=True)
class ResolverConfig:
    schedule: str = "daily"
    expiry_days: int = 14
    candidate_window_before_s: int = 30
    candidate_window_after_s: int = 120
    auto_select_min_confidence: float = 0.90
    ambiguity_margin: float = 0.10
    algorithm_version: str = "v1-weighted"


@dataclass(slots=True)
class NoteMatcherConfig:
    lookback_hours: int = 2
    buffer_after_s: int = 300
    min_confidence: float = 0.70
    ambiguity_margin: float = 0.10
    max_candidates: int = 20
    expiry_days: int = 14
    algorithm_version: str = "watch-note-v1"


@dataclass(slots=True)
class WikiConfig:
    auto_request: bool = False
    max_attempts: int = 3


@dataclass(slots=True)
class PrivacyConfig:
    raw_activity_retention_days: int = 30
    max_malformed_ratio: float = 0.10


@dataclass(slots=True)
class TelegramConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    markdown_dir: str = "var/queues"


@dataclass(slots=True)
class BackupConfig:
    directory: str = "var/backups"
    retain: int = 14


@dataclass(slots=True)
class AppConfig:
    resolver: ResolverConfig = field(default_factory=ResolverConfig)
    note_matcher: NoteMatcherConfig = field(default_factory=NoteMatcherConfig)
    wiki: WikiConfig = field(default_factory=WikiConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    database_path: str = "var/queue.sqlite3"
    knowledge_base_path: str = "~/knowledge_base"


_SECTIONS: dict[str, type[Any]] = {
    "resolver": ResolverConfig,
    "note_matcher": NoteMatcherConfig,
    "wiki": WikiConfig,
    "privacy": PrivacyConfig,
    "telegram": TelegramConfig,
    "backup": BackupConfig,
}


def _construct(cls: type[Any], values: dict[str, Any], section: str) -> Any:
    unknown = set(values) - set(cls.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown keys in {section}: {sorted(unknown)}")
    return cls(**values)


def load_config(path: str | Path | None = None) -> AppConfig:
    raw: dict[str, Any] = {}
    data_home = _data_home()
    if path is not None:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("configuration root must be a mapping")
        raw = loaded
    allowed = set(_SECTIONS) | {"database_path", "knowledge_base_path"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown configuration sections: {sorted(unknown)}")
    sections = {
        name: _construct(cls, raw.get(name, {}), name) for name, cls in _SECTIONS.items()
    }
    # Resolve database_path relative to data_home if not absolute
    db_path = raw.get("database_path", "var/queue.sqlite3")
    if not Path(db_path).is_absolute():
        db_path = str(data_home / Path(db_path).name)
    # Resolve telegram.markdown_dir relative to data_home if not absolute
    telegram_config = sections.get("telegram")
    if telegram_config and not Path(telegram_config.markdown_dir).is_absolute():
        telegram_config.markdown_dir = str(data_home / Path(telegram_config.markdown_dir).name)
    # Resolve backup.directory relative to data_home if not absolute
    backup_config = sections.get("backup")
    if backup_config and not Path(backup_config.directory).is_absolute():
        backup_config.directory = str(data_home / Path(backup_config.directory).name)
    config = AppConfig(
        **sections,
        database_path=db_path,
        knowledge_base_path=raw.get("knowledge_base_path", "~/knowledge_base"),
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    resolver = config.resolver
    if resolver.expiry_days < 1:
        raise ValueError("resolver.expiry_days must be positive")
    if min(resolver.candidate_window_before_s, resolver.candidate_window_after_s) < 0:
        raise ValueError("candidate windows cannot be negative")
    note_matcher = config.note_matcher
    if note_matcher.lookback_hours < 1 or note_matcher.max_candidates < 1:
        raise ValueError("note matcher lookback and max_candidates must be positive")
    if note_matcher.buffer_after_s < 0 or note_matcher.expiry_days < 1:
        raise ValueError("note matcher buffer/expiry values are invalid")
    for name, value in (
        ("auto_select_min_confidence", resolver.auto_select_min_confidence),
        ("ambiguity_margin", resolver.ambiguity_margin),
        ("note_matcher.min_confidence", note_matcher.min_confidence),
        ("note_matcher.ambiguity_margin", note_matcher.ambiguity_margin),
        ("max_malformed_ratio", config.privacy.max_malformed_ratio),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if config.telegram.port < 1 or config.telegram.port > 65535:
        raise ValueError("telegram.port must be between 1 and 65535")
    if config.backup.retain < 1:
        raise ValueError("backup.retain must be positive")
