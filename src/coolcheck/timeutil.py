"""Timestamps and Singapore dates that do not depend on the session time zone.

The API strings carry their own offset (+08:00), so parsing them gives an instant. The SGT date and minute of day
are computed from the epoch with a fixed +08:00 offset: Singapore has used UTC+08:00, with no daylight saving,
since 1982. A reading at 00:00 SGT belongs to the new day.
"""
from pyspark.sql import Column
from pyspark.sql import functions as F

SGT_OFFSET_S = 8 * 3600
TS_FORMAT = "yyyy-MM-dd'T'HH:mm:ssXXX"


def parse_ts(c) -> Column:
    """ISO string with offset -> TIMESTAMP; NULL (not an error) if it does not parse."""
    return F.try_to_timestamp(F.col(c) if isinstance(c, str) else c, F.lit(TS_FORMAT))


def sgt_date(ts) -> Column:
    ts = F.col(ts) if isinstance(ts, str) else ts
    return F.date_from_unix_date(F.floor((F.unix_seconds(ts) + SGT_OFFSET_S) / 86400).cast("int"))


def sgt_minute(ts) -> Column:
    """Minutes since 00:00 SGT (0..1439)."""
    ts = F.col(ts) if isinstance(ts, str) else ts
    return (F.pmod(F.unix_seconds(ts) + SGT_OFFSET_S, 86400) / 60).cast("int")


def sgt_instant(d, minutes: int) -> Column:
    """The instant `minutes` after 00:00 SGT on DATE d (e.g. the 00:15 cut-off)."""
    d = F.col(d) if isinstance(d, str) else d
    return F.timestamp_seconds(F.unix_date(d).cast("long") * 86400 - SGT_OFFSET_S + minutes * 60)
