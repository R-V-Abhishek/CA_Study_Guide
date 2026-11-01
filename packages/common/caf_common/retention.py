"""Grandfather-father-son retention over recovery snapshot identifiers."""

from datetime import datetime, timezone
import re

SNAPSHOT_ID = re.compile(r"^caf_(\d{8})_(\d{6})_(\d{6})_[0-9a-f]{8}$")


def snapshot_time(identifier: str) -> datetime:
    match = SNAPSHOT_ID.fullmatch(identifier)
    if match is None:
        raise ValueError(f"Not a recovery snapshot identifier: {identifier!r}")
    return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S%f").replace(tzinfo=timezone.utc)


def plan_retention(identifiers: list[str], *, daily: int = 7, weekly: int = 4,
                   monthly: int = 6) -> tuple[list[str], list[str]]:
    """Return (keep, delete). Keeps the newest snapshot of each of the latest N days, ISO weeks
    and months, and always the single newest snapshot. Unknown names raise instead of being skipped."""
    if min(daily, weekly, monthly) < 1:
        raise ValueError("Every retention tier must keep at least one snapshot")
    ordered = sorted(identifiers, key=snapshot_time, reverse=True)
    keep: set[str] = set(ordered[:1])
    for limit, label in ((daily, lambda t: t.strftime("%Y-%m-%d")),
                         (weekly, lambda t: "%d-W%02d" % t.isocalendar()[:2]),
                         (monthly, lambda t: t.strftime("%Y-%m"))):
        seen: set[str] = set()
        for identifier in ordered:
            bucket = label(snapshot_time(identifier))
            if bucket in seen:
                continue
            if len(seen) >= limit:
                break
            seen.add(bucket)
            keep.add(identifier)
    return [i for i in ordered if i in keep], [i for i in ordered if i not in keep]
