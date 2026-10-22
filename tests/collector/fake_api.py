"""A fake data.gov.sg for the collector tests: newest-first pages of 25 timestamps per feed and date (check 9)."""
import json
from datetime import date, datetime, time, timedelta, timezone

SGT = timezone(timedelta(hours=8))
UTC = timezone.utc
STEP = {"wbgt": 15, "rainfall": 5, "air_temperature": 1}
ISSUES = (time(5, 30), time(11, 30), time(17, 30), time(23, 30))
PER_PAGE = 25


class Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class FakeSession:
    """handler(url, params, n) -> Resp; n counts calls from 1."""

    def __init__(self, handler):
        self.handler, self.calls, self.headers = handler, [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.handler(url, params or {}, len(self.calls))


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def __call__(self):
        return self.t


def feed_of(url):
    return ("wbgt" if url.endswith("/weather") else "rainfall" if url.endswith("/rainfall")
            else "air_temperature" if url.endswith("/air-temperature") else "forecast")


def _dump(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


class FakeAPI:
    """Readings exist up to `now` (an aware datetime). value(feed, ts) -> the reading's value, so a test can make a
    later run see a changed value. Calls are recorded as (feed, date, page) in self.log."""

    def __init__(self, now, value=None):
        self.now, self.value, self.log = now, value or (lambda feed, ts: "30.1" if feed == "wbgt" else 0), []

    def stamps(self, feed, day):
        start = datetime.combine(day, time(0), SGT)
        if feed == "forecast":
            out = [datetime.combine(day, t, SGT) for t in ISSUES]
        else:
            out = [start + timedelta(minutes=STEP[feed] * i) for i in range(24 * 60 // STEP[feed])]
        return sorted((s for s in out if s <= self.now), reverse=True)

    def body(self, feed, page_stamps, token):
        if feed == "wbgt":
            data = {"records": [{"datetime": s.isoformat(), "updatedTimestamp": s.isoformat(), "item": {
                "type": "observation", "isStationData": True, "readings": [
                    {"station": {"id": "S124", "name": "Upper Changi", "townCenter": "Changi"},
                     "location": {"latitude": "1.36777", "longitude": "103.982262"},
                     "wbgt": self.value(feed, s), "heatStress": "Low"}]}} for s in page_stamps]}
        elif feed == "rainfall":
            data = {"stations": [{"id": "S218", "deviceId": "S218", "name": "Bukit Batok",
                                  "location": {"latitude": 1.36491, "longitude": 103.75065}}],
                    "readings": [{"timestamp": s.isoformat(), "data": [{"stationId": "S218", "value": self.value(feed, s)}]}
                                 for s in page_stamps],
                    "readingType": "TB1 Rainfall 5 Minute Total F", "readingUnit": "mm"}
        elif feed == "air_temperature":
            data = {"stations": [{"id": "S109", "deviceId": "S109", "name": "Ang Mo Kio Avenue 5",
                                  "location": {"latitude": 1.3793, "longitude": 103.85}}],
                    "readings": [{"timestamp": s.isoformat(), "data": [{"stationId": "S109", "value": self.value(feed, s)}]}
                                 for s in page_stamps],
                    "readingType": "DBT 1M F", "readingUnit": "deg C"}
        else:
            data = {"records": [{"date": s.date().isoformat(), "timestamp": s.isoformat(), "updatedTimestamp": s.isoformat(),
                                 "general": {"temperature": {"low": 25, "high": 33, "unit": "Degrees Celsius"}}}
                                for s in page_stamps]}
        if token:
            data["paginationToken"] = token
        return _dump({"code": 0, "data": data, "errorMsg": ""})

    def __call__(self, url, params, n):
        feed, day = feed_of(url), date.fromisoformat(params["date"])
        page = int(params.get("paginationToken", "p1")[1:])
        self.log.append((feed, day, page))
        stamps = self.stamps(feed, day)
        if not stamps:
            return Resp(404, _dump({"code": 17, "data": None, "errorMsg": "Data not found"}))
        per = len(stamps) if feed == "forecast" else PER_PAGE
        chunk = stamps[(page - 1) * per: page * per]
        more = page * per < len(stamps)
        return Resp(200, self.body(feed, chunk, f"p{page + 1}" if more else None))

    def pages(self, feed, day):
        return [p for f, d, p in self.log if f == feed and d == day]
