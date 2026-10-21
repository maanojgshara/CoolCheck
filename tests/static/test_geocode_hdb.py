"""geocode_hdb.py against a fake OneMap: no network, no real sleeping, no real token."""
import csv
import json
from datetime import datetime, timedelta

import pytest
import requests

import geocode_hdb as G
from fake_onemap import Clock, FakeOneMap, FakeSession, Resp, jwt, result

SGT = G.SGT
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=SGT)
EXPIRY = datetime(2026, 10, 24, 12, 58, tzinfo=SGT)
TOKEN = jwt(int(EXPIRY.timestamp()))
COLUMNS = ["blk_no", "street", "residential", "total_dwelling_units", *G.RENTAL]
ROWS = [  # file order
    ("1", "BEACH RD", "Y", "142", "0", "0", "0", "0"),
    ("187", "BISHAN ST 13", "Y", "100", "5", "0", "0", "0"),
    ("2", "SHOP ST", "N", "0", "0", "0", "0", "0"),  # not residential
    ("3", "EMPTY RD", "Y", "0", "0", "0", "0", "0"),  # no dwelling units
    ("54", "GEYLANG BAHRU", "Y", "200", "0", "0", "0", "1"),
    ("635B", "SENJA RD", "Y", "120", "0", "0", "0", "0"),
    ("18C", "HOLLAND DR", "Y", "90", "0", "0", "2", "0"),
    ("9", "TOH YI DR", "Y", "80", "0", "3", "0", "0"),
]
ORDER = ["187 BISHAN ST 13", "54 GEYLANG BAHRU", "18C HOLLAND DR", "9 TOH YI DR", "1 BEACH RD", "635B SENJA RD"]
# check 5's raw results for 187 BISHAN ST 13: the block, and a family service centre listed at it with no postal code
BLOCK = result("187", "BISHAN STREET 13", "570187", x="30028.28910252545", y="36852.0108636301",
               searchval="187 BISHAN STREET 13 SINGAPORE 570187")
CENTRE = result("187", "BISHAN STREET 13", "NIL", x="30023.73280240037", y="36853.82651890069",
                building="REACH FAMILY SERVICE CENTRE", searchval="REACH FAMILY SERVICE CENTRE")


def others(n):
    """n results that are not 187 BISHAN ST 13: other block numbers on another road."""
    return [result(str(500 + i), "BISHAN STREET 22", str(570500 + i)) for i in range(n)]


def hdb_csv(tmp_path, rows=ROWS):
    path = tmp_path / "hdb.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return path


def run(tmp_path, handler=None, *argv, env=None, clock=None, now=None):
    sess, clock = FakeSession(handler or FakeOneMap(TOKEN)), clock or Clock()
    code = G.main(["--hdb-csv", str(hdb_csv(tmp_path)), "--out-dir", str(tmp_path / "out"), *argv], session=sess,
                  sleep=clock.sleep, clock=clock, now=now or (lambda: NOW),
                  env={G.TOKEN_ENV: TOKEN} if env is None else env)
    return code, sess, clock


def then(seq, api=None):
    """A handler that answers call n with seq[n] when given, else with the fake API."""
    api = api or FakeOneMap(TOKEN)
    return lambda u, p, h, n: seq[n] if n in seq else api(u, p, h, n)


def queries(sess):
    return [p["searchVal"] for _, p, _ in sess.calls]


def pages(sess):
    return [p["pageNum"] for _, p, _ in sess.calls]


def lines(tmp_path, name="progress.jsonl"):
    """The JSON lines of an output file, in order, skipping lines that are not JSON."""
    path, out = tmp_path / "out" / name, []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def finished(tmp_path):
    return [r["query"] for r in lines(tmp_path)]


def log(tmp_path):
    return (tmp_path / "out" / "geocode.log").read_text(encoding="utf-8")


def report(tmp_path):
    return (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def waits(clock):
    return [s for s in clock.sleeps if s > 1]


# ---- input and order ----

def test_residential_blocks_with_units_rental_first_then_file_order(tmp_path):
    blocks = G.load_blocks(hdb_csv(tmp_path))
    assert [b["query"] for b in blocks] == ORDER
    assert [b["rental"] for b in blocks] == [True] * 4 + [False] * 2


def test_a_repeated_block_is_refused(tmp_path):
    with pytest.raises(ValueError, match="1 BEACH RD"):
        G.load_blocks(hdb_csv(tmp_path, ROWS + [("1", "BEACH RD", "Y", "10", "0", "0", "0", "0")]))


# ---- matching ----

@pytest.mark.parametrize("hdb, onemap", [
    ("BISHAN ST 13", "BISHAN STREET 13"), ("BEDOK NTH AVE 1", "BEDOK NORTH AVENUE 1"),
    ("C'WEALTH CL", "COMMONWEALTH CLOSE"), ("ST. GEORGE'S RD", "SAINT GEORGE'S ROAD"),
    ("ST. GEORGE'S LANE", "ST GEORGES LANE"), ("QUEEN'S CL", "QUEENS CLOSE"), ("JLN MA'MOR", "JALAN MA'MOR"),
    ("LOR 1 TOA PAYOH", "LORONG 1 TOA PAYOH"), ("NEW UPP CHANGI RD", "NEW UPPER CHANGI ROAD"),
    ("TG PAGAR PLAZA", "TANJONG PAGAR PLAZA"), ("KG KAYU RD", "KAMPONG KAYU ROAD"), ("NEW MKT RD", "NEW MARKET ROAD"),
    ("TENGAH GDN AVE", "TENGAH GARDEN AVENUE"), ("PANDAN GDNS", "PANDAN GARDENS"), ("WOODLANDS SQ", "WOODLANDS SQUARE"),
    ("TELOK BLANGAH HTS", "TELOK BLANGAH HEIGHTS"), ("MARINE TER", "MARINE TERRACE"), ("EVERTON PK", "EVERTON PARK"),
    ("BOON LAY PL", "BOON LAY PLACE"), ("BT BATOK CTRL", "BUKIT BATOK CENTRAL"), ("BEDOK STH RD", "BEDOK SOUTH ROAD"),
    ("UPP CROSS ST", "UPPER CROSS STREET"), ("DOVER CL EAST", "DOVER CLOSE EAST"), ("JLN BT HO SWEE", "JALAN BUKIT HO SWEE"),
])
def test_hdb_streets_match_onemap_road_names(hdb, onemap):
    assert G.norm_road(hdb) == G.norm_road(onemap)


@pytest.mark.parametrize("hdb, onemap", [
    ("BISHAN ST 13", "BISHAN STREET 12"), ("BEDOK NTH AVE 1", "BEDOK SOUTH AVENUE 1"),
    ("UPP SERANGOON RD", "SERANGOON ROAD"), ("LOR 1 TOA PAYOH", "LORONG 1A TOA PAYOH"),
    ("C'WEALTH AVE", "COMMONWEALTH AVENUE WEST"), ("QUEEN ST", "QUEEN'S ROAD"),
])
def test_different_roads_do_not_match(hdb, onemap):
    assert G.norm_road(hdb) != G.norm_road(onemap)


def rec(results, pages_read=(1,), total=1, blk="187", street="BISHAN ST 13"):
    return {"blk_no": blk, "street": street, "results": results, "pages_read": list(pages_read), "total_pages": total}


def test_one_result_with_the_block_the_road_and_a_postal_code_is_matched():
    c = G.classify(rec([result("187A", "BISHAN STREET 13", "571187"), BLOCK]))
    assert (c["outcome"], c["candidates"], c["kept"]) == ("matched", 1, BLOCK) and c["outcome"] in G.CONFIRMED


def test_a_block_and_a_centre_listed_at_it_are_one_place_and_the_postal_record_is_kept():
    c = G.classify(rec([CENTRE, BLOCK]))
    assert (c["outcome"], c["candidates"], c["kept"]) == ("matched_same_place", 2, BLOCK) and c["outcome"] in G.CONFIRMED
    assert 4 < c["spread_m"] < 6


def test_a_single_candidate_without_a_postal_code_is_kept_but_not_confirmed():
    c = G.classify(rec([CENTRE]))
    assert (c["outcome"], c["candidates"], c["kept"]) == ("matched_no_postal", 1, CENTRE)
    assert c["outcome"] not in G.CONFIRMED


def test_candidates_at_one_place_all_without_a_postal_code_are_matched_no_postal():
    school = {**CENTRE, "BUILDING": "MY FIRST SKOOL", "SEARCHVAL": "MY FIRST SKOOL", "X": "30026.0"}
    c = G.classify(rec([CENTRE, school]))
    assert (c["outcome"], c["candidates"], c["kept"]) == ("matched_no_postal", 2, CENTRE)


# postal codes that do not end in 187, so the postal rule (below) does not apply
@pytest.mark.parametrize("pair", [
    [{**BLOCK, "POSTAL": "570111"}, {**BLOCK, "POSTAL": "570222"}],  # two postal codes
    [{**BLOCK, "POSTAL": "570111"}, {**CENTRE, "X": "30400.0"}],  # one postal code, 370 m apart
    [CENTRE, {**CENTRE, "X": "30400.0"}],  # no postal code, 370 m apart: no single record to keep
])
def test_candidates_at_different_places_are_ambiguous(pair):
    c = G.classify(rec(pair))
    assert (c["outcome"], c["candidates"], c["kept"], c["rejected"]) == ("ambiguous", 2, None, [])


# ---- the postal rule: one postal code ends in the block number ----
def elsewhere(postal, **kw):
    """Another record for 187 BISHAN STREET 13, 470 m from BLOCK."""
    return {**BLOCK, "POSTAL": postal, "X": "30500.0", **kw}


def test_candidates_at_different_places_are_resolved_by_the_one_postal_code_that_ends_in_the_block_number():
    wrong = elsewhere("570999", BUILDING="SOME OTHER PLACE")
    c = G.classify(rec([wrong, BLOCK]))
    assert (c["outcome"], c["candidates"], c["kept"], c["rejected"]) == ("matched_postal_rule", 2, BLOCK, [wrong])
    assert c["outcome"] in G.CONFIRMED and c["spread_m"] > G.SAME_PLACE_M


def test_no_postal_code_that_ends_in_the_block_number_leaves_it_ambiguous():
    c = G.classify(rec([elsewhere("570999"), elsewhere("570111", X="30900.0")]))
    assert (c["outcome"], c["kept"], c["rejected"]) == ("ambiguous", None, [])
    assert c["outcome"] not in G.CONFIRMED


def test_two_different_postal_codes_that_end_in_the_block_number_leave_it_ambiguous():
    c = G.classify(rec([BLOCK, elsewhere("680187")]))
    assert (c["outcome"], c["kept"], c["rejected"]) == ("ambiguous", None, [])


def test_candidates_without_a_postal_code_are_ambiguous_whatever_the_block_number():
    c = G.classify(rec([elsewhere("NIL"), elsewhere("NIL", X="30900.0")]))
    assert c["outcome"] == "ambiguous"


@pytest.mark.parametrize("blk, street, postals, kept", [
    # block 5 has suffix 005: 560015 ends in 5 but not in 005, and 560500 begins with it
    ("5", "ANG MO KIO AVE 3", ["560015", "560005", "560500"], "560005"),
    # a letter after the number is dropped: 18C has suffix 018
    ("18C", "HOLLAND DR", ["274099", "274018"], "274018"),
    ("12", "TOH YI DR", ["590012", "590112"], "590012"),
])
def test_the_block_number_is_zero_padded_to_three_digits(blk, street, postals, kept):
    cands = [result(blk, G.norm_road(street), postal, x=30000.0 + 500 * i) for i, postal in enumerate(postals)]
    c = G.classify(rec(cands, blk=blk, street=street))
    assert (c["outcome"], c["kept"]["POSTAL"]) == ("matched_postal_rule", kept)
    assert sorted(r["POSTAL"] for r in c["rejected"]) == sorted(p for p in postals if p != kept)


def test_the_postal_rule_does_not_touch_matches_that_are_already_made():
    assert G.classify(rec([BLOCK]))["outcome"] == "matched"
    assert G.classify(rec([CENTRE, BLOCK]))["outcome"] == "matched_same_place"
    assert G.classify(rec([CENTRE]))["outcome"] == "matched_no_postal"


def test_a_wrong_block_or_road_is_not_found():
    c = G.classify(rec([result("187A", "BISHAN STREET 13", "571187"), result("187", "BISHAN STREET 12", "570188"),
                        {"SEARCHVAL": "BISHAN PARK"}]))
    assert (c["outcome"], c["candidates"], c["kept"]) == ("not_found", 0, None)


@pytest.mark.parametrize("results, pages_read, total, outcome, left", [
    ([BLOCK], [1], 4, "matched", True),  # a candidate on page 1: the later pages are not read
    ([], [1, 2, 3, 4, 5], 7, "not_found", True),  # pages beyond 5 are not read
    ([], [1, 2, 3], 3, "not_found", False),
])
def test_pages_left_unread(results, pages_read, total, outcome, left):
    c = G.classify(rec(results, pages_read, total))
    assert (c["outcome"], c["pages_left"]) == (outcome, left)


# ---- pages 2 to 5 ----

def test_a_match_only_on_page_2_is_found_with_one_extra_call_and_counted(tmp_path):
    code, sess, _ = run(tmp_path, FakeOneMap(TOKEN, {ORDER[0]: others(10) + [BLOCK] + others(3)}), "--limit", "1")
    assert code == 0 and queries(sess) == [ORDER[0]] * 2 and pages(sess) == [1, 2]
    line = lines(tmp_path)[0]
    assert (line["pages_read"], line["total_pages"], len(line["results"]), line["calls"]) == ([1, 2], 2, 14, 2)
    assert G.classify(line)["outcome"] == "matched"
    run_line = lines(tmp_path, "runs.jsonl")[0]
    assert (run_line["calls"], run_line["page_calls"]) == (2, 1)
    assert "calls 2 (1 for pages 2 to 5)" in log(tmp_path)
    text = report(tmp_path)
    assert "| 1 | 2 | 1 | 0 |" in text  # blocks, calls, of them for pages 2 to 5, retries
    assert ("Blocks for which pages 2 to 5 were read: 1; extra pages read: 1; of those blocks, with a candidate on "
            "the extra pages: 1; with no candidate on pages 1 to 5 and pages left unread: 0.") in text


def test_a_match_on_page_1_reads_no_further_page(tmp_path):
    code, sess, _ = run(tmp_path, FakeOneMap(TOKEN, {ORDER[0]: [BLOCK] + others(30)}), "--limit", "1")
    assert code == 0 and pages(sess) == [1]
    line = lines(tmp_path)[0]
    assert (line["pages_read"], line["total_pages"]) == ([1], 4) and G.classify(line)["pages_left"]
    assert "with a candidate on page 1, so no later page read: 1." in report(tmp_path)


def test_a_match_without_a_postal_code_on_page_1_also_ends_the_paging(tmp_path):
    code, sess, _ = run(tmp_path, FakeOneMap(TOKEN, {ORDER[0]: [CENTRE] + others(12)}), "--limit", "1")
    assert code == 0 and pages(sess) == [1]
    assert G.classify(lines(tmp_path)[0])["outcome"] == "matched_no_postal"


@pytest.mark.parametrize("n, read", [(25, [1, 2, 3]), (65, [1, 2, 3, 4, 5])])
def test_with_no_match_pages_are_read_in_turn_up_to_page_5(tmp_path, n, read):
    code, sess, _ = run(tmp_path, FakeOneMap(TOKEN, {ORDER[0]: others(n)}), "--limit", "1")
    assert code == 0 and pages(sess) == read
    line = lines(tmp_path)[0]
    assert line["pages_read"] == read and len(line["results"]) == min(n, 50) and line["calls"] == len(read)
    c = G.classify(line)
    assert c["outcome"] == "not_found" and c["pages_left"] == (n > 50)


# ---- resume ----

def test_a_rerun_skips_finished_blocks(tmp_path):
    code, sess, _ = run(tmp_path, None, "--limit", "2")
    assert code == 0 and queries(sess) == ORDER[:2]
    code, sess, _ = run(tmp_path)
    assert code == 0 and queries(sess) == ORDER[2:]
    code, sess, _ = run(tmp_path)
    assert code == 0 and sess.calls == []
    assert finished(tmp_path) == ORDER


def test_a_line_cut_short_by_a_crash_is_ignored_and_its_block_fetched_again(tmp_path):
    run(tmp_path, None, "--limit", "2")
    progress = tmp_path / "out" / "progress.jsonl"
    progress.write_bytes(progress.read_bytes() + b'{"key": "18C|HOLLAND DR", "blk_no": "18C", "resu')
    code, sess, _ = run(tmp_path)
    assert code == 0 and queries(sess) == ORDER[2:]
    assert finished(tmp_path) == ORDER  # the cut line stays on a line of its own and is skipped
    assert "1 line(s) could not be read" in log(tmp_path)


def test_ctrl_c_keeps_finished_blocks_and_a_rerun_goes_on(tmp_path):
    code, _, _ = run(tmp_path, then({3: KeyboardInterrupt()}))
    assert code == 1 and finished(tmp_path) == ORDER[:2]
    assert "STOPPED: interrupted (Ctrl+C)" in log(tmp_path)
    code, sess, _ = run(tmp_path)
    assert code == 0 and queries(sess) == ORDER[2:]


def test_a_second_run_on_the_same_out_dir_is_refused(tmp_path):
    (tmp_path / "out").mkdir()
    lock = G.acquire_lock(tmp_path / "out" / "geocode.lock")
    try:
        code, sess, _ = run(tmp_path)
    finally:
        lock.close()
    assert code == 3 and sess.calls == []
    assert "another geocoding run holds the lock" in log(tmp_path)


# ---- pace and back-off ----

def test_three_calls_a_second(tmp_path):
    code, sess, clock = run(tmp_path)
    assert code == 0 and len(sess.calls) == 6
    assert clock.t == pytest.approx(5 / 3) and not waits(clock)  # the fake answers at once, so only the gaps count


def test_429_waits_a_fixed_30_s_twice_then_succeeds(tmp_path):
    code, sess, clock = run(tmp_path, then({1: Resp(429), 2: Resp(429)}), "--limit", "1")
    assert code == 0 and queries(sess) == [ORDER[0]] * 3
    assert waits(clock) == [30, 30]
    assert lines(tmp_path)[0]["calls"] == 3


def test_429s_that_are_not_in_a_row_do_not_stop_the_run(tmp_path):
    code, sess, clock = run(tmp_path, then({1: Resp(429), 3: Resp(429), 4: Resp(429), 6: Resp(429)}))
    assert code == 0 and len(sess.calls) == 10 and finished(tmp_path) == ORDER
    assert waits(clock) == [30] * 4


def test_429_on_page_2_waits_and_is_retried(tmp_path):
    api = FakeOneMap(TOKEN, {ORDER[0]: others(10) + [BLOCK]})
    code, sess, clock = run(tmp_path, then({2: Resp(429), 3: Resp(429)}, api), "--limit", "1")
    assert code == 0 and pages(sess) == [1, 2, 2, 2] and waits(clock) == [30, 30]
    line = lines(tmp_path)[0]
    assert (line["pages_read"], line["calls"]) == ([1, 2], 4)
    run_line = lines(tmp_path, "runs.jsonl")[0]
    assert (run_line["calls"], run_line["page_calls"], run_line["retries"]) == (4, 3, 2)


# ---- stops ----

def test_three_429s_in_a_row_stop_the_run_and_a_rerun_resumes_there(tmp_path):
    api = FakeOneMap(TOKEN)
    code, sess, clock = run(tmp_path, lambda u, p, h, n: Resp(429) if p["searchVal"] == ORDER[1] else api(u, p, h, n))
    assert code == 1
    assert queries(sess) == [ORDER[0]] + [ORDER[1]] * 3 and waits(clock) == [30, 30]
    assert finished(tmp_path) == ORDER[:1]
    assert "STOPPED: 3 HTTP 429s in a row" in log(tmp_path)
    code, sess, _ = run(tmp_path)
    assert code == 0 and queries(sess) == ORDER[1:]


def test_three_429s_on_page_2_stop_the_run_and_nothing_of_the_block_is_kept(tmp_path):
    api = FakeOneMap(TOKEN, {ORDER[0]: others(10) + [BLOCK]})
    code, sess, clock = run(tmp_path, lambda u, p, h, n: Resp(429) if p["pageNum"] == 2 else api(u, p, h, n))
    assert code == 1 and pages(sess) == [1, 2, 2, 2] and waits(clock) == [30, 30]
    assert finished(tmp_path) == []
    assert "STOPPED: 3 HTTP 429s in a row (API limit exceeded) at '187 BISHAN ST 13' page 2" in log(tmp_path)
    code, sess, _ = run(tmp_path, api, "--limit", "2")  # the rerun starts the block again from page 1
    assert code == 0 and list(zip(queries(sess), pages(sess))) == [(ORDER[0], 1), (ORDER[0], 2), (ORDER[1], 1)]


def test_401_stops_at_once_and_gives_the_token_expiry(tmp_path):
    code, sess, clock = run(tmp_path, then({2: Resp(401, {"error": "Unauthorized"})}))
    assert code == 1 and len(sess.calls) == 2 and not waits(clock)
    assert finished(tmp_path) == ORDER[:1]
    text = log(tmp_path)
    assert "HTTP 401" in text and "expires 24 Oct 2026 12:58 SGT; that time has not come" in text
    assert "/api/auth/post/getToken" in text


def test_401_after_the_token_expired_mid_run_says_it_has_passed(tmp_path):
    clock, token = Clock(), jwt(int((NOW + timedelta(seconds=10)).timestamp()))
    code, _, _ = run(tmp_path, then({1: Resp(429), 2: Resp(401)}, FakeOneMap(token)), env={G.TOKEN_ENV: token},
                     clock=clock, now=lambda: NOW + timedelta(seconds=clock.t))
    assert code == 1
    assert "HTTP 401" in log(tmp_path) and "expires 22 Oct 2026 09:00 SGT; that time has passed" in log(tmp_path)


def test_403_stops_at_once(tmp_path):
    code, sess, clock = run(tmp_path, then({1: Resp(403, b"Access Forbidden. GET access is not allowed")}))
    assert code == 1 and len(sess.calls) == 1 and not waits(clock)
    assert "HTTP 403" in log(tmp_path) and "Access Forbidden" in log(tmp_path)
    assert finished(tmp_path) == []


@pytest.mark.parametrize("status", [401, 403])
def test_401_or_403_on_an_extra_page_stops_at_once_and_nothing_of_the_block_is_kept(tmp_path, status):
    code, sess, clock = run(tmp_path, then({3: Resp(status)}, FakeOneMap(TOKEN, {ORDER[0]: others(25)})))
    assert code == 1 and pages(sess) == [1, 2, 3] and not waits(clock)
    assert finished(tmp_path) == [] and f"HTTP {status} at '187 BISHAN ST 13' page 3" in log(tmp_path)


def test_an_error_attribute_with_http_200_stops_and_records_nothing(tmp_path):
    code, sess, _ = run(tmp_path, then({1: Resp(200, {"error": "Invalid token"})}))
    assert code == 1 and len(sess.calls) == 1 and finished(tmp_path) == []
    assert "error attribute (Invalid token)" in log(tmp_path) and "expires 24 Oct 2026 12:58 SGT" in log(tmp_path)


def test_server_errors_and_failed_connections_are_retried_twice_then_stop(tmp_path):
    code, sess, clock = run(tmp_path, then({1: Resp(502), 2: requests.ConnectionError("reset"), 3: Resp(503)}))
    assert code == 1 and len(sess.calls) == 3 and waits(clock) == [30, 30]
    assert "HTTP 503" in log(tmp_path) and finished(tmp_path) == []


def test_one_server_error_is_retried_and_the_run_goes_on(tmp_path):
    code, sess, clock = run(tmp_path, then({1: Resp(502)}))
    assert code == 0 and len(sess.calls) == 7 and waits(clock) == [30]


def test_any_other_status_stops_at_once(tmp_path):
    code, sess, _ = run(tmp_path, then({1: Resp(400, {"error": "Parameter searchVal is invalid."})}))
    assert code == 1 and len(sess.calls) == 1
    assert "unexpected HTTP 400" in log(tmp_path)


# ---- the token ----

def test_no_token_no_call(tmp_path, capsys):
    code, sess, _ = run(tmp_path, env={})
    assert code == 2 and sess.calls == []
    assert "ONEMAP_TOKEN is not set" in capsys.readouterr().err


def test_an_expired_token_stops_before_any_call(tmp_path):
    code, sess, _ = run(tmp_path, now=lambda: EXPIRY + timedelta(minutes=1))
    assert code == 2 and sess.calls == []
    assert "expired 24 Oct 2026 12:58 SGT" in log(tmp_path)


def test_the_token_goes_only_in_the_authorization_header(tmp_path):
    code, sess, _ = run(tmp_path, None, "--limit", "2", env={G.TOKEN_ENV: f" {TOKEN}\n"})  # stray whitespace trimmed
    assert code == 0 and len(sess.calls) == 2
    for (url, params, headers), q in zip(sess.calls, ORDER):
        assert url == G.SEARCH and headers["Authorization"] == TOKEN
        assert params == {"searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}


def test_the_token_is_never_printed_logged_or_written(tmp_path, capsys):
    echo = result("187", "BISHAN STREET 13", "570187", building=f"ECHO {TOKEN}")  # as if a body quoted the token
    handler = then({1: requests.ConnectionError(f"proxy refused {TOKEN}"), 3: Resp(403, {"error": f"{TOKEN} refused"})},
                   FakeOneMap(TOKEN, {ORDER[0]: [echo]}))
    code, _, _ = run(tmp_path, handler)
    assert code == 1
    cap = capsys.readouterr()
    text = cap.out + cap.err + "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "out").iterdir())
    assert TOKEN not in text and "ECHO ***" in text
    assert "HTTP 403" in text and "expires 24 Oct 2026 12:58 SGT" in text


# ---- usage and outputs ----

@pytest.mark.parametrize("argv, env, why", [
    (["--rate", "5"], None, "--rate must be above 0 and at most 4"),
    (["--limit", "0"], None, "--limit must be at least 1"),
    ([], {G.TOKEN_ENV: "two words"}, "holds a space"),
])
def test_usage_checks(tmp_path, capsys, argv, env, why):
    code, sess, _ = run(tmp_path, None, *argv, env=env)
    assert code == 2 and sess.calls == [] and why in capsys.readouterr().err


@pytest.mark.parametrize("out", [G.REPO / "tmp_geocode", G.DATA / "raw" / "geocode"])
def test_out_dir_inside_the_repo_or_coolcheck_data_raw_is_refused(tmp_path, out, capsys):
    code = G.main(["--hdb-csv", str(hdb_csv(tmp_path)), "--out-dir", str(out)], session=FakeSession(FakeOneMap(TOKEN)),
                  env={G.TOKEN_ENV: TOKEN})
    assert code == 2 and "--out-dir must be outside" in capsys.readouterr().err
    assert not out.exists()


def test_csv_and_report_count_each_outcome_and_list_buildings_without_postal_codes(tmp_path):
    holland = [result("18C", "HOLLAND DRIVE", "274001"), result("18C", "HOLLAND DRIVE", "274099", x=30500.0)]
    toh_yi = [result("9", "TOH YI DRIVE", "NIL", building="TOH YI GARDENS")]
    api = FakeOneMap(TOKEN, {ORDER[0]: [CENTRE, BLOCK], ORDER[1]: [], ORDER[2]: holland, ORDER[3]: toh_yi})
    code, _, _ = run(tmp_path, api, "--limit", "5")
    assert code == 0
    with (tmp_path / "out" / "geocoded_blocks.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == G.CSV_COLUMNS
    assert [(r["blk_no"], r["outcome"], r["confirmed"], r["onemap_postal"]) for r in rows] == [
        ("187", "matched_same_place", "Y", "570187"), ("54", "not_found", "N", ""), ("18C", "ambiguous", "N", ""),
        ("9", "matched_no_postal", "N", "NIL"), ("1", "matched", "Y", "100000")]
    assert rows[3]["onemap_latitude"] == "1.35"  # the record is kept, only not confirmed
    assert [r["note"] for r in rows] == ["", "", "", "address match through a tenant record", ""]
    text = report(tmp_path)
    for line in ("| matched | 0 | 1 | 1 |", "| matched_same_place | 1 | 0 | 1 |", "| matched_no_postal | 1 | 0 | 1 |",
                 "| ambiguous | 1 | 0 | 1 |", "| not_found | 1 | 0 | 1 |", "| not fetched yet | 0 | 1 | 1 |",
                 "| matched_postal_rule | 0 | 0 | 0 |", "| total | 4 | 2 | 6 |",
                 "Confirmed matches (matched, matched_same_place, matched_postal_rule): 2 of 5 finished blocks"):
        assert line in text
    assert "| 18C HOLLAND DR | 2 | 1 of 1 | 500 |" in text
    no_postal = text.split("## matched_no_postal (1)")[1].split("## ")[0]
    assert "TOH YI GARDENS" in no_postal and "address match through a tenant record" in no_postal
    assert "not confirmed (address match through a tenant record)" in log(tmp_path)


def test_a_block_resolved_by_the_postal_rule_is_confirmed_listed_with_its_rejected_candidates_and_kept_by_report_only(
        tmp_path):
    right = result("187", "BISHAN STREET 13", "570187", lat="1.3501", lon="103.8501")
    wrong = result("187", "BISHAN STREET 13", "570999", x=30500.0, building="WRONG PLACE", lat="1.3601", lon="103.8601")
    toh_yi = [result("9", "TOH YI DRIVE", "NIL", building="TOH YI GARDENS")]
    code, sess, _ = run(tmp_path, FakeOneMap(TOKEN, {ORDER[0]: [wrong, right], ORDER[3]: toh_yi}), "--limit", "4")
    assert code == 0
    assert ("matched_postal_rule (2 candidates, 500 m apart): 570187 at 1.3501, 103.8501; rejected postal codes 570999"
            in log(tmp_path))

    def csv_rows():
        with (tmp_path / "out" / "geocoded_blocks.csv").open(encoding="utf-8", newline="") as f:
            return {r["blk_no"]: r for r in csv.DictReader(f)}
    first = csv_rows()["187"]
    assert (first["outcome"], first["confirmed"], first["onemap_postal"], first["onemap_latitude"], first["candidates"]) \
        == ("matched_postal_rule", "Y", "570187", "1.3501", "2")
    assert (csv_rows()["9"]["confirmed"], csv_rows()["9"]["onemap_postal"]) == ("N", "NIL")
    text = report(tmp_path)
    assert "| matched_postal_rule | 1 | 0 | 1 |" in text
    section = text.split("## matched_postal_rule (1)")[1].split("\n## ")[0]
    assert "| 187 BISHAN ST 13 | 570187, 187 BISHAN STREET 13 SINGAPORE 570187 | 187, BISHAN STREET 13, 570999, WRONG PLACE |" \
        in section
    # report-only applies the same rule from progress.jsonl, with no call and no token
    (tmp_path / "out" / "geocoded_blocks.csv").unlink()
    (tmp_path / "out" / "report.md").unlink()
    code, again, _ = run(tmp_path, None, "--report-only", env={})
    assert code == 0 and again.calls == []
    assert (csv_rows()["187"]["outcome"], csv_rows()["187"]["confirmed"]) == ("matched_postal_rule", "Y")
    assert "| matched_postal_rule | 1 | 0 | 1 |" in report(tmp_path)


def test_report_only_makes_no_call_and_needs_no_token(tmp_path):
    run(tmp_path, None, "--limit", "2")
    (tmp_path / "out" / "report.md").unlink()
    code, sess, _ = run(tmp_path, None, "--report-only", env={})
    assert code == 0 and sess.calls == []
    assert "| not fetched yet | 2 | 2 | 4 |" in report(tmp_path)
