"""A fake OneMap search API for the geocoding tests: answers from a table of results per query and checks the token."""
import base64
import json
import math


class Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.headers = status, headers or {}
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()


class FakeSession:
    """handler(url, params, headers, n) -> Resp, or an exception to raise; n counts calls from 1."""

    def __init__(self, handler):
        self.handler, self.calls, self.headers = handler, [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(self.headers)))
        r = self.handler(url, params or {}, self.headers, len(self.calls))
        if isinstance(r, BaseException):
            raise r
        return r


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def __call__(self):
        return self.t


def jwt(exp):
    """A stand-in for a OneMap token: a JWT whose payload holds only exp. Built at run time, so that no token-like
    string sits in the repo for a secret scan to find."""
    def part(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{part({'alg': 'none'})}.{part({'exp': exp})}.TEST-SIGNATURE-not-a-secret"


def result(blk, road, postal, x=30000.0, y=36000.0, building="NIL", searchval=None, lat="1.35", lon="103.85"):
    return {"SEARCHVAL": searchval or f"{blk} {road} SINGAPORE {postal}", "BLK_NO": blk, "ROAD_NAME": road,
            "BUILDING": building, "ADDRESS": f"{blk} {road} SINGAPORE {postal}", "POSTAL": postal, "X": str(x),
            "Y": str(y), "LATITUDE": lat, "LONGITUDE": lon}


class FakeOneMap:
    """Answers table[query] when given, else one result for the block itself; 10 results a page. A request whose
    Authorization header is not `token` gets HTTP 401 with an error attribute."""

    def __init__(self, token, table=None):
        self.token, self.table = token, table or {}

    def __call__(self, url, params, headers, n):
        if headers.get("Authorization") != self.token:
            return Resp(401, {"error": "Unauthorized"})
        q = params["searchVal"]
        if q in self.table:
            res = self.table[q]
        else:
            blk, road = q.split(" ", 1)
            res = [result(blk, road, "100000")]
        page = int(params.get("pageNum", 1))
        return Resp(200, {"found": len(res), "totalNumPages": max(1, math.ceil(len(res) / 10)), "pageNum": page,
                          "results": res[(page - 1) * 10: page * 10]})
