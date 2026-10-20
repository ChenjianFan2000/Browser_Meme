"""Independent original-site checks for the fixed supervised complex task.

No model scripts, predictions, notes or declared selected pair are loaded.
Canonical choices come from the actual initial DB, checked against visible UI.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get("BM_DISCOGS_RUNTIME", ROOT / ".runtime/phase1-complex-pw-20261020-1815")).resolve()
DB = RUNTIME / "data/discogs.db"
BASELINE = RUNTIME / "data/baseline.db"
CASES = {c["id"]: c for c in json.loads((HERE / "complex_cases.json").read_text(encoding="utf-8"))}


def _fixed(case):
    fixed = CASES[case["id"]]
    if case.get("goal") != fixed["goal"] or case.get("parameters") != fixed["parameters"]:
        raise ValueError("Fixed complex goal/parameters changed")
    return fixed


def _connect(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _hash(rows):
    canonical = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_state(path):
    with _connect(path) as con:
        con.execute("BEGIN")
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        rows = {}
        for table in tables:
            quoted = table.replace('"', '""')
            rows[table] = [dict(row) for row in con.execute(f'SELECT * FROM "{quoted}"')]
        users = {row["id"]: row for row in rows["users"]}
        demo = next(row["id"] for row in rows["users"] if row["username"] == "demo")
        listings = sorted(rows["marketplace_listings"], key=lambda row: row["id"])
        listing_map = {row["id"]: row for row in listings}
        cart_all = sorted(rows["cart_items"], key=lambda row: row["id"])
        cart = [row for row in cart_all if row["user_id"] == demo]
        all_orders = sorted(rows["orders"], key=lambda row: row["id"])
        orders = [row for row in all_orders if row["buyer_user_id"] == demo]
        items = sorted(rows["order_items"], key=lambda row: row["id"])
        latest = orders[-1] if orders else None
        target = [{**row, "seller_username": users[row["seller_user_id"]]["username"],
                   "seller_rating": users[row["seller_user_id"]]["seller_rating"],
                   "seller_location": users[row["seller_user_id"]]["location"]}
                  for row in listings if row["release_id"] == 221]
        # Password hashes participate in integrity hashing but are never returned.
        return {
            "demo_user_id": demo,
            "collection_ids": sorted(row["release_id"] for row in rows["collection_items"] if row["user_id"] == demo),
            "wantlist_ids": sorted(row["release_id"] for row in rows["wantlist_items"] if row["user_id"] == demo),
            "cart": cart, "cart_rows_all": cart_all, "cart_count": len(cart),
            "cart_total_cents": sum(listing_map[row["listing_id"]]["price_cents"] * row["quantity"] for row in cart),
            "orders": orders, "order_count": len(orders), "all_orders": all_orders,
            "order_items": items, "latest_demo_order": latest,
            "latest_demo_order_items": [row for row in items if latest and row["order_id"] == latest["id"]],
            "listings": listings, "target_marketplace": target,
            "catalog": {"release_id": 221, "title": next(row["title"] for row in rows["releases"] if row["id"] == 221)},
            "table_hashes": {table: _hash(data) for table, data in rows.items()},
            "table_counts": {table: len(data) for table, data in rows.items()},
        }


def observe():
    return _read_state(DB)


def reset(case):
    fixed = _fixed(case)
    expected = (RUNTIME / "baseline.sha256").read_text(encoding="ascii").strip()
    actual = hashlib.sha256(BASELINE.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("Complex frozen baseline hash mismatch")
    with _connect(BASELINE) as source:
        with sqlite3.connect(DB, timeout=15) as destination:
            source.backup(destination)
    state = observe()
    return {"case_id": fixed["id"], "baseline_sha256": actual, "table_hashes": state["table_hashes"]}


def observe_ui(page):
    """Passive public response capture plus privileged token verification only."""
    if not hasattr(page, "_discogs_complex_traffic"):
        page._discogs_complex_traffic = []
        page._discogs_complex_dispatches = []

        def dispatched(request):
            parsed = urlparse(request.url)
            if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith("/api/") or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
                return
            item = {"_request": request, "path": parsed.path, "method": request.method, "state": "pending"}
            if parsed.path == "/api/cart/items" and request.method == "POST":
                try:
                    body = request.post_data_json
                    item["request"] = {key: body.get(key) for key in ["listing_id", "quantity"]}
                except Exception as exc:
                    item["request_error"] = type(exc).__name__
            page._discogs_complex_dispatches.append(item)

        def failed(request):
            for item in page._discogs_complex_dispatches:
                if item["_request"] == request:
                    item["state"] = "failed"

        def seen(response):
            parsed = urlparse(response.url)
            if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith("/api/"):
                return
            request = response.request
            for item in page._discogs_complex_dispatches:
                if item["_request"] == request:
                    item.update(state="response", status=response.status)
            item = {"path": parsed.path, "method": request.method, "status": response.status}
            if parsed.path == "/api/cart/items" and request.method == "POST":
                try:
                    body = request.post_data_json
                    item["request"] = {key: body.get(key) for key in ["listing_id", "quantity"]}
                except Exception as exc:
                    item["request_error"] = type(exc).__name__
            if parsed.path in {"/api/cart", "/api/cart/items", "/api/checkout"} and 200 <= response.status < 300:
                try:
                    body = response.json()
                    if parsed.path == "/api/checkout":
                        item["body"] = {key: body.get(key) for key in ["id", "status", "total_cents", "currency", "items"]}
                    else:
                        item["body"] = {key: body.get(key) for key in ["items", "total_cents", "currency"]}
                except Exception as exc:
                    item["body_error"] = type(exc).__name__
            page._discogs_complex_traffic.append(item)

        page.on("request", dispatched)
        page.on("requestfailed", failed)
        page.on("response", seen)
    result = page.evaluate("""() => {
      const visible = e => !!e.getClientRects().length;
      const main = document.querySelector('main');
      const text = main?.innerText || '';
      const money = t => { const m = t.match(/([A-Z]{3})\\s+(\\d+)\\.(\\d{2})/); return m ? {currency:m[1],cents:Number(m[2])*100+Number(m[3])} : null; };
      const rows = [...document.querySelectorAll('main table tbody tr')].filter(visible).map(tr => {
        const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
        const href = tr.querySelector('a[href^="/cart?add="]')?.getAttribute('href');
        if (!href) return null;
        const rating = cells[0]?.match(/(\\d+(?:\\.\\d+)?)\\s*%/);
        const condition = (cells[2] || '').split(' / ');
        const amount = money(cells[3] || '');
        return {listing_id:Number(new URL(href,location.href).searchParams.get('add')),
          seller_username:tr.querySelector('td div')?.innerText.trim() || null,
          seller_rating:rating ? Number(rating[1]) : null, ships_from:cells[1] || null,
          media_condition:condition[0] || null,sleeve_condition:condition[1] || null,
          currency:amount?.currency || null,price_cents:amount?.cents ?? null,cells,add_href:href};
      }).filter(Boolean);
      const cart = location.pathname === '/cart' ? [...document.querySelectorAll('main section .divide-y > div')].map(row => {
        const link = row.querySelector('a[href^="/release/"]');
        if (!link) return null;
        const t = row.innerText;
        const seller = t.match(/Seller:\\s*([^\\n]+)/);
        const amount = money(t);
        return {release_href:link.getAttribute('href'),seller_username:seller?.[1].trim() || null,
          currency:amount?.currency || null,unit_price_cents:amount?.cents ?? null,text:t};
      }).filter(Boolean) : [];
      const total = money(document.querySelector('main aside')?.innerText || '');
      const count = text.match(/Marketplace listings[\\s\\S]*?(\\d+)\\s+for sale/);
      return {url:location.href,main_text:text,
        release_links:[...document.querySelectorAll('main a[href^="/release/"]')].filter(visible).map(a => a.getAttribute('href')),
        market_total:count ? Number(count[1]) : null,market_rows:rows,
        filters:Object.fromEntries([...document.querySelectorAll('main form input[name],main form select[name]')].map(e => [e.name,e.value])),
        cart_rows:cart,cart_total_cents:location.pathname === '/cart' ? total?.cents ?? null : null,
        checkout_disabled:[...document.querySelectorAll('button')].find(e => e.innerText.trim() === 'Checkout')?.disabled ?? null};
    }""")
    token = next((cookie["value"] for cookie in page.context.cookies() if cookie["name"] == "discogs_token"), None)
    auth = {"present": bool(token), "verified": False, "subject": None}
    if token:
        try:
            from jose import jwt
            payload = jwt.decode(token, os.environ.get("JWT_SECRET", "dev_secret_change_me"),
                                 algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")])
            auth.update(verified=True, subject=UUID(str(payload["sub"])).hex)
        except Exception as exc:
            auth["error_type"] = type(exc).__name__
    result["auth"] = auth
    result["traffic"] = list(page._discogs_complex_traffic)
    result["dispatches"] = [{key: value for key, value in item.items() if not key.startswith("_")}
                            for item in page._discogs_complex_dispatches]
    return result


def _states(initial, current, history):
    states = [initial]
    for step in history:
        for key in ["before", "after"]:
            if isinstance(step.get(key), dict):
                states.append(step[key])
    states.append(current)
    return states


def _ui(state):
    return state.get("independent_ui", {})


def _path(state):
    return urlparse(_ui(state).get("url", state.get("ui", {}).get("url", ""))).path


def _market_universe(initial, parameters):
    return [row for row in initial["backend"]["target_marketplace"]
            if row["status"] == "active" and row["seller_rating"] >= parameters["minimum_seller_rating"]]


def _pair(initial, parameters):
    eligible = [row for row in _market_universe(initial, parameters)
                if row["currency"] == parameters["currency"] and row["seller_username"] != parameters["exclude_seller_username"]]
    pairs = [(a["price_cents"] + b["price_cents"], min(a["id"], b["id"]), max(a["id"], b["id"]))
             for a, b in itertools.combinations(eligible, 2) if a["seller_user_id"] != b["seller_user_id"]]
    if not pairs:
        return None
    total, low, high = min(pairs)
    if total > parameters["maximum_total_cents"]:
        return None
    by_id = {row["id"]: row for row in eligible}
    return [by_id[low], by_id[high]]


def _market_matches(initial, state, parameters):
    shown = _ui(state)
    if not all(key in shown for key in ["market_rows", "market_total", "url"]):
        return None
    query = parse_qs(urlparse(shown["url"]).query, keep_blank_values=True)
    try:
        exact_rating = float(query.get("min_rating", [""])[0]) == parameters["minimum_seller_rating"]
    except ValueError:
        exact_rating = False
    exact_filter = _path(state) == "/sell/release/221" and exact_rating and query.get("sort") == [parameters["sort"]]
    exact_filter = exact_filter and all(not query.get(key, [""])[0] for key in ["media_condition", "sleeve_condition", "ships_from"])
    expected = _market_universe(initial, parameters)
    actual = shown["market_rows"]
    if not exact_filter or len(expected) > 50 or shown["market_total"] != len(expected) or len(actual) != len(expected):
        return False
    reference = {row["id"]: row for row in expected}
    ids = [row["listing_id"] for row in actual]
    if len(set(ids)) != len(ids) or set(ids) != set(reference):
        return False
    for row in actual:
        ref = reference[row["listing_id"]]
        if any(row.get(key) != ref[key] for key in ["seller_username", "ships_from", "media_condition", "sleeve_condition", "currency", "price_cents"]):
            return False
        if row.get("seller_rating") is None or abs(row["seller_rating"] - ref["seller_rating"]) > 0.051:
            return False
    prices = [row["price_cents"] for row in actual]
    return prices == sorted(prices)


def _unchanged(initial, current, allowed):
    before, after = initial["backend"]["table_hashes"], current["backend"]["table_hashes"]
    return set(before) == set(after) and all(before[name] == after[name] for name in before if name not in allowed)


def _nav_ok(initial, current, history, parameters):
    states = _states(initial, current, history)
    for i, state in enumerate(states):
        parsed = urlparse(_ui(state).get("url", ""))
        query = parse_qs(parsed.query)
        if parsed.path != "/search" or query.get("q") != [parameters["search_query"]] or "/release/221" not in _ui(state).get("release_links", []):
            continue
        for j in range(i + 1, len(states)):
            if _path(states[j]) == "/release/221" and initial["backend"]["catalog"]["title"] in _ui(states[j]).get("main_text", ""):
                if any(_market_matches(initial, later, parameters) is True for later in states[j + 1:]):
                    return True
    return False


def _return_nav_ok(initial, current, history, parameters, chosen):
    states = _states(initial, current, history)
    ids = {row["id"] for row in chosen}
    for i, state in enumerate(states):
        cart = state.get("backend", {}).get("cart", [])
        if _path(state) != "/cart" or len(cart) != 1 or cart[0]["listing_id"] not in ids or cart[0]["quantity"] != 1:
            continue
        second = next(iter(ids - {cart[0]["listing_id"]}))
        if "/release/221" not in _ui(state).get("release_links", []):
            continue
        for j in range(i + 1, len(states)):
            if _path(states[j]) == "/release/221" and states[j].get("backend", {}).get("cart") == cart:
                if any(_market_matches(initial, later, parameters) is True and later.get("backend", {}).get("cart") == cart and second in {row["listing_id"] for row in _ui(later).get("market_rows", [])}
                       for later in states[j + 1:]):
                    return True
    return False


def _cart_exact(initial, current, chosen):
    cart = current["backend"]["cart"]
    return len(cart) == 2 and {row["listing_id"] for row in cart} == {row["id"] for row in chosen} and all(
        row["quantity"] == 1 and row["user_id"] == initial["backend"]["demo_user_id"] for row in cart
    ) and current["backend"]["cart_total_cents"] == sum(row["price_cents"] for row in chosen)


def _cart_dom_exact(current, chosen):
    state = _ui(current)
    rows = state.get("cart_rows")
    if rows is None or state.get("cart_total_cents") is None:
        return None
    expected = sorted((row["seller_username"], row["currency"], row["price_cents"], "/release/221") for row in chosen)
    actual = sorted((row["seller_username"], row["currency"], row["unit_price_cents"], row["release_href"]) for row in rows)
    return _path(current) == "/cart" and actual == expected and state["cart_total_cents"] == sum(row["price_cents"] for row in chosen) and state.get("checkout_disabled") is False


def _cart_payload_exact(body, chosen):
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        return None
    actual = [(row.get("listing", {}).get("listing_id"), row.get("quantity"), row.get("listing", {}).get("price_cents"), row.get("listing", {}).get("seller_username")) for row in body["items"]]
    expected = [(row["id"], 1, row["price_cents"], row["seller_username"]) for row in chosen]
    return sorted(actual) == sorted(expected) and body.get("total_cents") == sum(row["price_cents"] for row in chosen) and body.get("currency") == "USD"


def _checks(initial, current):
    checks = []
    def add(identifier, passed, detail):
        checks.append({"id": identifier, "passed": passed if passed is None else bool(passed), "detail": detail})
    required = {"demo_user_id", "table_hashes", "cart", "cart_rows_all", "cart_total_cents", "target_marketplace", "catalog", "listings", "all_orders", "order_items"}
    usable = all(isinstance(state.get("backend"), dict) and required <= state["backend"].keys()
                 and isinstance(state.get("independent_ui"), dict) and {"url", "auth", "traffic", "dispatches"} <= state["independent_ui"].keys()
                 for state in [initial, current])
    add("required_actual_channels", True if usable else None, "Actual independent UI and transaction-consistent DB snapshots required")
    return checks, add, usable


def _decision(checks):
    if any(check["passed"] is False for check in checks):
        return "stop"
    if not checks or any(check["passed"] is not True for check in checks):
        return "unknown"
    return "continue"


def checkpoint(case, checkpoint_id, initial, current, history):
    fixed = _fixed(case)
    parameters = fixed["parameters"]
    checks, add, usable = _checks(initial, current)
    if checkpoint_id not in {"selection_committed", "before_checkout"}:
        add("supported_checkpoint", None, "Unknown checkpoint cannot authorize a write")
    elif usable:
        chosen = _pair(initial, parameters)
        auth = _ui(current).get("auth", {})
        traffic = _ui(current).get("traffic", [])
        dispatches = _ui(current).get("dispatches", [])
        add("no_unconfirmed_mutation", all(row.get("state") == "response" and 200 <= row.get("status", 0) < 300 for row in dispatches),
            "Every observed API mutation dispatch has a confirmed successful response; pending/failed writes cannot authorize continuation")
        add("authenticated_demo", auth.get("verified") is True and auth.get("subject") == initial["backend"]["demo_user_id"],
            "Current signed, unexpired auth subject matches initial demo account")
        add("initial_cart_empty", initial["backend"]["cart"] == [], "Initial demo cart must be empty")
        add("independent_budget_pair_exists", chosen is not None, "Independent initial-state enumeration finds a distinct-seller USD optimum within fixed budget")
        add("search_detail_market_navigation", _nav_ok(initial, current, history, parameters), "Actual search-result, release-detail and filtered marketplace observations occur in order")
        add("login_succeeded", sum(row["path"] == "/api/auth/login" and row["method"] == "POST" and row["status"] == 200 for row in traffic) == 1,
            "One successful real UI login response")
        mutations = [row for row in traffic if row["method"] in {"POST", "PUT", "PATCH", "DELETE"}]
        if checkpoint_id == "selection_committed":
            add("complete_exact_visible_market", _market_matches(initial, current, parameters), "Exact full initial filtered universe, visible total and all rows, including unselected offers, agree")
            add("no_business_write_before_selection", _unchanged(initial, current, set()), "All business tables remain byte-semantic equal to initial rows")
            add("no_cart_or_checkout_dispatch", all(row["path"] == "/api/auth/login" for row in dispatches), "No add/checkout or other mutation dispatch before first gate")
        elif chosen:
            add("only_cart_changed_before_checkout", _unchanged(initial, current, {"cart_items"}), "No orders/items/listings/catalog/accounts/memberships changed before checkout")
            add("other_users_carts_preserved", [r for r in current["backend"]["cart_rows_all"] if r["user_id"] != initial["backend"]["demo_user_id"]] == [r for r in initial["backend"]["cart_rows_all"] if r["user_id"] != initial["backend"]["demo_user_id"]], "Other users' cart rows unchanged")
            add("exact_independent_pair_quantity_total", _cart_exact(initial, current, chosen), "Actual demo cart equals independent canonical pair, each qty1 and exact total")
            add("exact_cart_dom", _cart_dom_exact(current, chosen), "Two visible seller/price/release rows, exact summary total and enabled Checkout")
            add("cross_page_second_offer_readback", _return_nav_ok(initial, current, history, parameters, chosen), "After one-item cart, actual release detail then re-filtered complete marketplace revalidates the other offer")
            adds = [row for row in traffic if row["path"] == "/api/cart/items" and row["method"] == "POST"]
            add("exactly_two_real_adds", len(adds) == 2 and all(row["status"] == 201 and row.get("request", {}).get("quantity") == 1 for row in adds)
                and {row.get("request", {}).get("listing_id") for row in adds} == {row["id"] for row in chosen}, "Exactly two actual POST add responses; original safe request IDs and quantities match")
            gets = [row for row in traffic if row["path"] == "/api/cart" and row["method"] == "GET" and row["status"] == 200]
            add("actual_cart_get_matches", _cart_payload_exact(gets[-1].get("body"), chosen) if gets else None, "Latest successful browser GET cart payload independently agrees with DB and DOM")
            add("no_checkout_or_unrelated_dispatch", all(row["path"] in {"/api/auth/login", "/api/cart/items"} for row in dispatches), "No Checkout or other write dispatch before explicit gate")
            add("observed_unrelated_state_preserved", all(_unchanged(initial, state, {"cart_items"}) for state in _states(initial, current, history)), "Unrelated tables unchanged at every recorded pre-checkout state")
    decision = _decision(checks)
    summary = "独立检查通过；仅可在本次状态复核和Solar明确继续后执行紧邻的声明操作。" if decision == "continue" else "独立检查未授权继续；保持暂停，不执行待定写入，不替换对象或重试写入。"
    return {"decision": decision, "checks": checks, "public_summary": summary}


def evaluate(case, before, after):
    fixed = _fixed(case)
    parameters = fixed["parameters"]
    checks, add, usable = _checks(before, after)
    if not usable:
        return checks
    chosen = _pair(before, parameters)
    add("independent_pair_exists", chosen is not None, "Initial independent exact-budget optimum required")
    if not chosen:
        return checks
    b, a = before["backend"], after["backend"]
    history = after.get("history", [])
    traffic = _ui(after).get("traffic", [])
    dispatches = _ui(after).get("dispatches", [])
    auth = _ui(after).get("auth", {})
    add("final_authenticated_demo", auth.get("verified") is True and auth.get("subject") == before["backend"]["demo_user_id"], "Final signed account remains demo")
    add("confirmed_exact_mutation_dispatches", all(row.get("state") == "response" and 200 <= row.get("status", 0) < 300 for row in dispatches)
        and sum(row["path"] == "/api/auth/login" for row in dispatches) == 1
        and sum(row["path"] == "/api/cart/items" for row in dispatches) == 2
        and sum(row["path"] == "/api/checkout" for row in dispatches) == 1,
        "Exactly one login, two adds and one checkout dispatch; no pending/failed mutation")
    selected_ids = {row["id"] for row in chosen}
    total = sum(row["price_cents"] for row in chosen)
    add("unchanged_unrelated_tables", _unchanged(before, after, {"marketplace_listings", "orders", "order_items", "cart_items"}), "All other table contents, including sealed user password state, unchanged")
    old_order_ids = {row["id"] for row in b["all_orders"]}
    new = [row for row in a["all_orders"] if row["id"] not in old_order_ids]
    add("one_exact_paid_demo_order", len(new) == 1 and new[0]["buyer_user_id"] == b["demo_user_id"] and new[0]["status"] == "paid" and new[0]["currency"] == "USD" and new[0]["total_cents"] == total,
        "Exactly one new demo paid USD order with canonical pair total")
    add("all_prior_orders_unchanged", [row for row in a["all_orders"] if row["id"] in old_order_ids] == b["all_orders"], "Every existing order, including other users', preserved")
    previous_item_ids = {row["id"] for row in b["order_items"]}
    added_items = [row for row in a["order_items"] if row["id"] not in previous_item_ids]
    expected_items = sorted((row["id"], row["price_cents"], 1) for row in chosen)
    actual_items = sorted((row["listing_id"], row["price_cents"], row["quantity"]) for row in added_items)
    add("exact_two_new_order_items", len(new) == 1 and actual_items == expected_items and all(row["order_id"] == new[0]["id"] for row in added_items), "Only canonical two listing/price/quantity lines belong to the new order")
    add("all_prior_items_unchanged", [row for row in a["order_items"] if row["id"] in previous_item_ids] == b["order_items"], "Every previous item is untouched")
    expected_listings = [{**row, "status": "sold"} if row["id"] in selected_ids else row for row in b["listings"]]
    add("only_two_listing_statuses_change", a["listings"] == expected_listings, "Only selected statuses become sold; their quantity and all other fields/listings stay unchanged")
    add("cart_restored_exactly", a["cart_rows_all"] == b["cart_rows_all"] and a["cart"] == [], "Demo cart empty and all users' final cart rows equal initial state")
    final_ui = _ui(after)
    add("empty_cart_ui_disabled", _path(after) == "/cart" and "Your cart is empty" in final_ui.get("main_text", "") and final_ui.get("cart_rows") == [] and final_ui.get("checkout_disabled") is True and final_ui.get("cart_total_cents") == 0,
        "Actual cart DOM is empty, exact zero total, Checkout disabled")
    checkout = [row for row in traffic if row["method"] == "POST" and row["path"] == "/api/checkout"]
    add("single_checkout_dispatch_success", len(checkout) == 1 and checkout[0]["status"] == 200, "Exactly one actual checkout POST, not an automatic retry")
    response = checkout[0].get("body") if len(checkout) == 1 else None
    response_items = sorted((row.get("listing_id"), row.get("price_cents"), row.get("quantity")) for row in response.get("items", [])) if isinstance(response, dict) else []
    add("checkout_response_matches_persistence", isinstance(response, dict) and len(new) == 1 and response.get("id") == new[0]["id"] and response.get("status") == "paid" and response.get("currency") == "USD" and response.get("total_cents") == total and response_items == expected_items,
        "Real browser checkout response agrees with independently persisted order and lines")
    adds = [row for row in traffic if row["path"] == "/api/cart/items" and row["method"] == "POST"]
    add("only_two_single_quantity_adds", len(adds) == 2 and all(row["status"] == 201 and row.get("request", {}).get("quantity") == 1 for row in adds)
        and {row.get("request", {}).get("listing_id") for row in adds} == selected_ids, "Exactly two actual canonical add requests, each quantity1")
    allowed_paths = {"/api/auth/login", "/api/cart/items", "/api/checkout"}
    add("no_other_mutation_attempts", all(row["path"] in allowed_paths for row in traffic if row["method"] in {"POST", "PUT", "PATCH", "DELETE"}), "No unrelated mutation attempt in observed UI traffic")
    states = _states(before, after, history)
    add("observed_exact_precheckout_cart", any(_cart_exact(before, state, chosen) and _cart_dom_exact(state, chosen) is True and state["backend"]["table_hashes"]["orders"] == b["table_hashes"]["orders"] for state in states), "Actual two-item cart with exact DOM/DB total was observed before any new order")
    add("required_search_and_return_navigation", _nav_ok(before, after, history, parameters) and _return_nav_ok(before, after, history, parameters, chosen), "Actual search/detail/market and one-cart/detail/re-filtered-market sequences retained")
    add("observed_unrelated_tables_preserved", all(_unchanged(before, state, {"cart_items", "marketplace_listings", "orders", "order_items"}) for state in states), "Unrelated data remained unchanged at every recorded point")
    return checks
