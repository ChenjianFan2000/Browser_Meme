"""Independent extension checks from upstream source and real observations only.

The original eight endpoints are delegated unchanged. Public extension goals are
fixed separately. This module never loads model plans, rules or predictions.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("discogs_anchor_evaluator", HERE / "evaluator.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
EXTENSIONS = {c["id"]: c for c in json.loads((HERE / "extension_cases.json").read_text(encoding="utf-8"))}
observe = base.observe


def _fixed(case):
    fixed = EXTENSIONS[case["id"]]
    if case.get("goal") != fixed["goal"] or case.get("parameters") != fixed["parameters"]:
        raise ValueError("Extension goal or parameters changed")
    return fixed


def reset(case):
    if case["id"] in base.CASES:
        return base.reset(case)
    fixed = _fixed(case)
    result = base.reset(next(iter(base.CASES.values())))
    return {**result, "case_id": fixed["id"]}


def observe_ui(page):
    """Read DOM/storage and passively record public mutation response metadata.

    No request is initiated; request payloads, headers, token values and login
    bodies are deliberately excluded. Listeners observe normal page traffic.
    """
    if not hasattr(page, "_discogs_independent_responses"):
        page._discogs_independent_responses = []

        def response_seen(response):
            parsed = urlparse(response.url)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                return
            if parsed.path.startswith(("/api/me/", "/api/cart", "/api/auth/")):
                page._discogs_independent_responses.append({
                    "path": parsed.path, "method": response.request.method,
                    "status": response.status,
                })
        page.on("response", response_seen)
    state = page.evaluate("""() => {
      const visible = e => !!(e.getClientRects().length);
      const rows = [...document.querySelectorAll('main table tbody tr')].filter(visible).map(tr => ({
        cells: [...tr.querySelectorAll('td')].map(td => td.innerText.trim()),
        add_href: tr.querySelector('a[href^="/cart?add="]')?.getAttribute('href') || null
      }));
      let consent = null;
      try { consent = localStorage.getItem('discogs_clone_cookie_consent_v1'); } catch {}
      return {
        url: location.href, consent,
        navigation_type: performance.getEntriesByType('navigation')[0]?.type || null,
        main_text: document.querySelector('main')?.innerText || '',
        release_links: [...document.querySelectorAll('main a[href^="/release/"]')].filter(visible).map(a => a.getAttribute('href')),
        rows,
        filters: Object.fromEntries([...document.querySelectorAll('main form input[name],main form select[name]')].map(e => [e.name,e.value])),
        checkout_disabled: [...document.querySelectorAll('button')].find(e => e.innerText.trim() === 'Checkout')?.disabled ?? null,
        cookie_button_visible: [...document.querySelectorAll('button')].some(e => e.innerText.trim() === 'Accept All Cookies' && visible(e))
      };
    }""")
    state["auth_cookie_present"] = any(c["name"] == "discogs_token" for c in page.context.cookies())
    state["responses"] = list(page._discogs_independent_responses)
    return state


def _snapshots(before, after):
    result = [before]
    for step in after.get("history", []):
        result.extend([step["before"], step["after"]])
    result.append(after)
    return result


def evaluate(case, before, after):
    if case["id"] in base.CASES:
        return base.evaluate(case, before, after)
    fixed = _fixed(case)
    kind = fixed["parameters"]["kind"]
    b, a = before["backend"], after["backend"]
    samples = _snapshots(before, after)
    final = after.get("independent_ui", {})
    ui = [s.get("independent_ui", {}) for s in samples]
    path = urlparse(after["ui"]["url"]).path
    checks = []

    def check(identifier, passed, detail):
        checks.append({"id": identifier, "passed": bool(passed), "detail": detail})

    membership = kind in {"collection_duplicate", "wantlist_duplicate", "signout_gate"}
    allowed = {"collection_items" if kind != "wantlist_duplicate" else "wantlist_items"} if membership else set()
    if kind == "anonymous_cart_return":
        allowed = {"cart_items"}
    check("unrelated_tables_unchanged", all(b["table_hashes"][t] == a["table_hashes"][t] for t in b["table_hashes"] if t not in allowed),
          "All tables outside the exact public task mutation remain unchanged")
    intermediate_allowed = allowed | ({"cart_items"} if kind == "cart_repeat_remove" else set())
    check("observed_intermediate_unrelated_state", all(
        s["backend"]["table_hashes"][t] == b["table_hashes"][t]
        for s in samples for t in b["table_hashes"] if t not in intermediate_allowed),
        "Unrelated tables also remain unchanged at every recorded intermediate snapshot")
    responses = final.get("responses", [])

    def response_count(route, method="POST", success=True):
        return sum(r["path"] == route and r["method"] == method and
                   ((200 <= r["status"] < 300) if success else r["status"] == 401) for r in responses)

    if kind == "consent_persistence":
        check("accepted_survives_reload", final.get("consent") == "accepted" and final.get("cookie_button_visible") is False
              and final.get("navigation_type") == "reload" and any(u.get("cookie_button_visible") for u in ui),
              "Initially visible consent banner is absent after a real reload with accepted localStorage")
    elif kind == "genre_navigation":
        genre_views = [u for u in ui if urlparse(u.get("url", "")).path == "/genre/rock"]
        try:
            release_id = int(path.removeprefix("/release/")) if path.startswith("/release/") else -1
        except ValueError:
            release_id = -1
        with base._connect(base.DB) as con:
            member = con.execute("SELECT 1 FROM release_genres rg JOIN genres g ON g.id=rg.genre_id WHERE rg.release_id=? AND g.slug='rock'", (release_id,)).fetchone()
            tracks = [r[0] for r in con.execute("SELECT title FROM tracks WHERE release_id=? ORDER BY position", (release_id,))]
        check("genre_card_detail_tracklist", bool(member and tracks and genre_views)
              and any('/release/' + str(release_id) in u.get("release_links", []) for u in genre_views)
              and "Tracklist" in final.get("main_text", "")
              and all(t in final.get("main_text", "") for t in tracks),
              "A displayed Rock card leads to its real database tracklist")
    elif kind in {"search_empty", "search_no_match"}:
        query = fixed["parameters"]["query"]
        actual_query = parse_qs(urlparse(after["ui"]["url"]).query, keep_blank_values=True).get("q", [""])[0]
        check("exact_search_empty_results", path == "/search" and actual_query == query
              and final.get("release_links") == [] and ("Enter a query in the search bar." in final.get("main_text", "") if not query else query in final.get("main_text", "")),
              "Fixed search term and correct empty-result rendering with no result cards")
    elif kind.startswith("market_"):
        _market_checks(kind, before, final, ui, check)
    elif membership:
        want = kind == "wantlist_duplicate"
        field = "wantlist_ids" if want else "collection_ids"
        table = "wantlist_items" if want else "collection_items"
        segment = "wantlist_others" if want else "collection_others"
        check("exact_single_membership", 221 not in b[field] and a[field] == sorted(b[field] + [221])
              and a["table_counts"][table] == b["table_counts"][table] + 1
              and a["segment_hashes"][segment] == b["segment_hashes"][segment],
              "Exactly one demo/221 membership added and all other membership rows preserved")
        route = "/api/me/" + ("wantlist" if want else "collection") + "/221"
        if kind == "signout_gate":
            check("real_signout_and_gate", response_count("/api/auth/logout") >= 1
                  and path == "/login" and response_count("/api/me/collection", "GET", False) >= 1
                  and final.get("auth_cookie_present") is False,
                  "Successful UI logout, removed auth cookie and real anonymous collection refusal")
        else:
            check("two_real_adds_and_reload", response_count(route) >= 2
                  and any(urlparse(u.get("url", "")).path == "/release/221" and u.get("navigation_type") == "reload" for u in ui),
                  "At least two successful actual add responses and detail reload observed")
            check("membership_page_visible", path == ("/me/wantlist" if want else "/me/collection") and "The Dark Side Of The Moon" in final.get("main_text", ""),
                  "Persistent target appears on the requested account list")
    elif kind == "cart_repeat_remove":
        target_samples = [s for s in samples if len(s["backend"]["cart"]) == 1 and s["backend"]["cart"][0]["listing_id"] == 1
                          and s["backend"]["cart"][0]["quantity"] == 2 and s["backend"]["cart_total_cents"] == b["fixture"]["price_cents"] * 2
                          and f'USD {b["fixture"]["price_cents"] * 2 / 100:.2f}' in s.get("independent_ui", {}).get("main_text", "")]
        check("double_quantity_intermediate", bool(target_samples) and response_count("/api/cart/items") >= 2,
              "Actual intermediate cart and displayed total show two units in one row")
        check("removed_final_cart", a["cart"] == [] and path == "/cart" and final.get("checkout_disabled") is True
              and "Your cart is empty" in final.get("main_text", "") and any(r["method"] == "DELETE" and r["path"].startswith("/api/cart/items/") and 200 <= r["status"] < 300 for r in responses),
              "Successful real removal leaves empty cart and disabled checkout")
    elif kind == "anonymous_cart_return":
        check("anonymous_login_return", any(urlparse(u.get("url", "")).path == "/login" and parse_qs(urlparse(u.get("url", "")).query).get("next") == ["/cart?add=1"] for u in ui)
              and response_count("/api/cart/items", success=False) >= 1 and response_count("/api/auth/login") >= 1,
              "Anonymous add refused then login returns to exact add URL")
        check("exact_cart_after_return", path == "/cart" and len(a["cart"]) == 1 and a["cart"][0]["listing_id"] == 1 and a["cart"][0]["quantity"] == 1
              and a["cart_total_cents"] == b["fixture"]["price_cents"] and a["segment_hashes"]["cart_others"] == b["segment_hashes"]["cart_others"]
              and "The Dark Side Of The Moon" in final.get("main_text", ""),
              "Return completes exactly one target unit, preserving other users' carts")
    return checks


def _market_checks(kind, before, final, ui, check):
    parsed = urlparse(final.get("url", ""))
    query = parse_qs(parsed.query, keep_blank_values=True)
    candidates = [r for r in before["backend"]["listings"] if r["release_id"] == 221 and r["status"] == "active"]
    if kind == "market_filter_none":
        check("exact_empty_filter", parsed.path == "/sell/release/221" and query.get("ships_from") == ["phase1-no-country"]
              and not any(r.get("add_href") for r in final.get("rows", [])) and "No listings match these filters." in final.get("main_text", ""),
              "Fixed impossible shipping filter produces explicit empty table")
        return
    if kind == "market_filter_combo":
        initial = next((u for u in ui if urlparse(u.get("url", "")).path == "/sell/release/221" and any(r.get("add_href") for r in u.get("rows", []))), {})
        first = next((r for r in initial.get("rows", []) if r.get("add_href")), {})
        listing_id = int(parse_qs(urlparse(first.get("add_href", "")).query).get("add", [-1])[0])
        selected = next((r for r in candidates if r["id"] == listing_id), None)
        exact = selected is not None and all(query.get(key) == [selected[key]] for key in ["media_condition", "sleeve_condition", "ships_from"])
        check("first_offer_filter_values", exact, "Filter values equal the actually displayed first offer")
        if not exact:
            return
        candidates = [r for r in candidates if all(r[key] == selected[key] for key in ["media_condition", "sleeve_condition", "ships_from"])]
    candidates.sort(key=lambda r: (r["price_cents"], r["created_at"]), reverse=True)
    expected = candidates[:50]
    actual = [r for r in final.get("rows", []) if r.get("add_href")]
    expected_by_id = {r["id"]: r for r in expected}
    ids = [int(parse_qs(urlparse(r["add_href"]).query)["add"][0]) for r in actual]
    # Equal price/time ties have no SQL total ordering: compare tied sets while
    # checking descending price and exact immutable row data independently.
    values_match = len(ids) == len(expected) and set(ids) == set(expected_by_id)
    if values_match:
        for shown, identifier in zip(actual, ids):
            row = expected_by_id[identifier]
            cells = shown["cells"]
            values_match = values_match and len(cells) == 5 and cells[1] == row["ships_from"] and cells[2] == f'{row["media_condition"]} / {row["sleeve_condition"]}' and cells[3] == f'{row["currency"]} {row["price_cents"] / 100:.2f}'
    prices = [expected_by_id[i]["price_cents"] for i in ids if i in expected_by_id]
    check("exact_sorted_market_rows", parsed.path == "/sell/release/221" and query.get("sort") == ["price_desc"]
          and bool(actual) and values_match and prices == sorted(prices, reverse=True),
          "Exact independently derived active offer set, row fields, prices and descending order")
