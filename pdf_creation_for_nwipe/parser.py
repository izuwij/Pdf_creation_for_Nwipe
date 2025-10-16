"""Parsing helpers for NWipe log output."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Union
import csv
import io
import json
import os
import re


_KeyValue = Mapping[str, Any]


def _normalize_key(key: str) -> str:
    """Return a snake_case variant of ``key`` suitable for dictionary lookups."""
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", key.strip().lower())
    return cleaned.strip("_")


def _stringify(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="replace")
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_stringify(v) for v in value if v is not None)
    return str(value)


_INT_RE = re.compile(r"-?\d+")


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):  # avoid bool subclassing int
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _stringify(value).strip()
    if not text:
        return None
    match = _INT_RE.search(text.replace(",", ""))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None


_DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%d %b %Y %H:%M:%S",
    "%b %d %Y %H:%M:%S",
    "%a %b %d %H:%M:%S %Y",
]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError):
            return None
    text = _stringify(value).strip()
    if not text:
        return None
    # Allow trailing timezone like UTC or Z
    cleaned = text.replace("UTC", "").strip()
    if cleaned.endswith("Z") and "T" in cleaned:
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        pass
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _split_messages(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [msg.strip() for msg in (_stringify(v) for v in value) if msg.strip()]
    text = _stringify(value).strip()
    if not text:
        return []
    if any(sep in text for sep in ("\n", ";", "|", ",")):
        parts = re.split(r"[;|\n,]+", text)
        return [part.strip() for part in parts if part.strip()]
    return [text]


@dataclass
class NwipeRun:
    """Structured representation of a single NWipe execution."""

    device: Optional[str] = None
    method: Optional[str] = None
    passes: Optional[int] = None
    verify_passes: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[str] = None
    result: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def is_successful(self) -> Optional[bool]:
        if self.result is None:
            return None
        value = self.result.strip().lower()
        if not value:
            return None
        if value in {"success", "successful", "completed", "ok", "passed", "done"}:
            return True
        if value in {"fail", "failed", "failure", "error", "aborted", "stopped"}:
            return False
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "method": self.method,
            "passes": self.passes,
            "verify_passes": self.verify_passes,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "result": self.result,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "notes": self.notes,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_mapping(cls, mapping: _KeyValue) -> "NwipeRun":
        norm_map: Dict[str, Any] = {}
        original_names: Dict[str, str] = {}
        for raw_key, value in mapping.items():
            if value is None:
                continue
            norm_key = _normalize_key(str(raw_key))
            if not norm_key:
                continue
            if norm_key not in norm_map:
                norm_map[norm_key] = value
                original_names[norm_key] = str(raw_key)
            else:
                existing = norm_map[norm_key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    norm_map[norm_key] = [existing, value]
        used: set[str] = set()

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm_map:
                    used.add(name)
                    return norm_map[name]
            return None

        device = pick("device", "drive", "disk", "target", "path")
        method = pick("method", "wipe_method", "type")
        passes = _to_int(pick("passes", "pass_count", "number_of_passes", "wipe_passes"))
        verify_passes = _to_int(pick("verify_passes", "verify_pass", "verify"))
        start_time = _parse_datetime(pick("start_time", "started", "start", "start_date", "begin"))
        end_time = _parse_datetime(pick("end_time", "completed", "finish_time", "ended", "finish", "end_date"))
        duration = pick("duration", "elapsed", "elapsed_time", "time_taken")
        result = pick("result", "status", "outcome", "state")
        errors = pick("errors", "error", "error_messages")
        warnings = pick("warnings", "warning")
        notes = pick("notes", "note", "comment", "comments", "message")

        extra: Dict[str, str] = {}
        for key, value in norm_map.items():
            if key in used:
                continue
            original_key = original_names.get(key, key)
            extra[original_key] = _stringify(value)

        return cls(
            device=_stringify(device).strip() if device is not None else None,
            method=_stringify(method).strip() if method is not None else None,
            passes=passes,
            verify_passes=verify_passes,
            start_time=start_time,
            end_time=end_time,
            duration=_stringify(duration).strip() if duration is not None else None,
            result=_stringify(result).strip() if result is not None else None,
            errors=_split_messages(errors),
            warnings=_split_messages(warnings),
            notes=_stringify(notes).strip() if notes is not None else None,
            extra=extra,
        )


_KEY_VALUE_RE = re.compile(r"^\s*([^:=\t]+?)\s*(?:[:=]\s*|\s{2,}|\t+)(.+?)\s*$")


def _parse_key_value_text(text: str) -> List[_KeyValue]:
    entries: List[MutableMapping[str, Any]] = []
    current: MutableMapping[str, Any] = {}
    last_key: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or set(line) == {"-"}:
            if current:
                entries.append(current)
                current = {}
                last_key = None
            continue
        match = _KEY_VALUE_RE.match(raw_line)
        key: Optional[str] = None
        value: Optional[str] = None
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
        else:
            parts = line.split(None, 1)
            if len(parts) == 2:
                key, value = parts[0], parts[1]
        if key is None or value is None:
            if last_key and last_key in current:
                current[last_key] = f"{current[last_key]} {line}".strip()
            continue
        if key in current:
            existing = current[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                current[key] = [existing, value]
        else:
            current[key] = value
        last_key = key
    if current:
        entries.append(current)
    return entries


def _parse_json(text: str) -> Optional[List[_KeyValue]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, Mapping):
        # Common pattern: {"runs": [...]} or single run mapping
        if any(isinstance(v, Mapping) for v in data.values()):
            if len(data) == 1:
                value = next(iter(data.values()))
                if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
                    return list(value)
            if "runs" in data and isinstance(data["runs"], list):
                runs = [item for item in data["runs"] if isinstance(item, Mapping)]
                if runs:
                    return runs
        return [data]
    if isinstance(data, list):
        runs = [item for item in data if isinstance(item, Mapping)]
        if runs:
            return runs
    return None


def _parse_csv(text: str) -> Optional[List[_KeyValue]]:
    sample = text.lstrip()
    if not sample:
        return []
    first_line = sample.splitlines()[0]
    if "," not in first_line and ";" not in first_line:
        return None
    dialect = csv.excel
    delimiter = ","
    if ";" in first_line and first_line.count(";") >= first_line.count(","):
        delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: List[Dict[str, Any]] = []
    for row in reader:
        cleaned_row = {key.strip(): value.strip() if isinstance(value, str) else value for key, value in row.items() if key}
        if any(value for value in cleaned_row.values()):
            rows.append(cleaned_row)
    return rows or None


def _read_text(source: Union[str, bytes, os.PathLike[str], os.PathLike[bytes], io.TextIOBase, io.BufferedIOBase]) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8", errors="replace")
    if isinstance(source, os.PathLike):
        return Path(source).read_text(encoding="utf-8", errors="replace")
    if isinstance(source, str):
        potential_path = Path(source)
        if potential_path.exists():
            return potential_path.read_text(encoding="utf-8", errors="replace")
        return source
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)
    raise TypeError("Unsupported log source type")


def parse_nwipe_log(log_source: Union[str, os.PathLike[str], os.PathLike[bytes], bytes, Mapping[str, Any], Sequence[Any], NwipeRun]) -> List[NwipeRun]:
    """Parse NWipe output from a variety of formats into :class:`NwipeRun` objects."""
    if isinstance(log_source, NwipeRun):
        return [log_source]
    if isinstance(log_source, Mapping):
        return [NwipeRun.from_mapping(log_source)]
    if isinstance(log_source, Sequence) and not isinstance(log_source, (str, bytes, bytearray)):
        runs: List[NwipeRun] = []
        for item in log_source:
            if isinstance(item, NwipeRun):
                runs.append(item)
            elif isinstance(item, Mapping):
                runs.append(NwipeRun.from_mapping(item))
            else:
                raise TypeError("Unsupported element in log sequence; expected mapping or NwipeRun")
        return runs

    text = _read_text(log_source)
    text = text.replace("\ufeff", "").strip()
    if not text:
        return []

    json_entries = _parse_json(text)
    if json_entries is not None:
        return [NwipeRun.from_mapping(entry) for entry in json_entries]

    csv_entries = _parse_csv(text)
    if csv_entries is not None:
        return [NwipeRun.from_mapping(entry) for entry in csv_entries]

    kv_entries = _parse_key_value_text(text)
    return [NwipeRun.from_mapping(entry) for entry in kv_entries]
