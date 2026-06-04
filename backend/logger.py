# backend/logger.py
import json
from pathlib import Path


def _log_path(date_str: str, base_dir: str) -> Path:
    log_dir = Path(base_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{date_str}.jsonl"


def write_log_entry(entry: dict, base_dir: str = "downloads") -> None:
    ts = entry.get("ts", "")
    date_str = ts[:10] if ts else "unknown"
    path = _log_path(date_str, base_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log_entries(date_str: str, base_dir: str = "downloads") -> list[dict]:
    path = _log_path(date_str, base_dir)
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def read_log_entries_by_task(task_id: int, base_dir: str = "downloads") -> list[dict]:
    log_dir = Path(base_dir) / "logs"
    if not log_dir.exists():
        return []
    entries = []
    for path in sorted(log_dir.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("task_id") == task_id:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    return entries


def list_log_dates(base_dir: str = "downloads") -> list[str]:
    log_dir = Path(base_dir) / "logs"
    if not log_dir.exists():
        return []
    return sorted(
        [f.stem for f in log_dir.glob("*.jsonl") if len(f.stem) == 10],
        reverse=True,
    )
