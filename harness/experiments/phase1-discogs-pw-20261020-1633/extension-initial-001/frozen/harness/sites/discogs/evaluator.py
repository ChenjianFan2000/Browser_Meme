"""Trusted independent endpoint evaluator; no model bundle or predictions are read."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get("BM_DISCOGS_RUNTIME", str(ROOT / ".runtime/phase1-discogs-20261020"))).resolve()
DB = RUNTIME / "data/discogs.db"
BASELINE = RUNTIME / "data/baseline.db"
MARKER = "phase1-independent-fixture"
CASES = {c["id"]: c for c in json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))}


def _case(case: dict) -> dict:
    fixed = CASES[case["id"]]
    if case.get("goal") != fixed["goal"] or case.get("parameters") != fixed["parameters"]:
        raise ValueError("Case goals and parameters differ from fixed independent cases")
    return fixed


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _hash(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reset(case: dict) -> dict:
    fixed = _case(case)
    expected = (RUNTIME / "baseline.sha256").read_text(encoding="ascii").strip()
    actual = hashlib.sha256(BASELINE.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("Frozen baseline hash mismatch")
    with _connect(BASELINE) as source:
        # SQLite backup coordinates with active connections and preserves source DB.
        with sqlite3.connect(DB, timeout=15) as destination:
            source.backup(destination)
    observed = observe()
    return {"case_id": fixed["id"], "baseline_sha256": actual,
            "table_hashes": observed["table_hashes"], "fixture": observed["fixture"]}


def observe() -> dict:
    with _connect(DB) as con:
        con.execute("BEGIN")
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        rows = {}
        for table in tables:
            # Table names come only from SQLite metadata, quoted defensively.
            safe = table.replace('"', '""')
            data = [dict(r) for r in con.execute(f'SELECT * FROM "{safe}"')]
            for row in data:
                row.pop("password_hash", None)
            rows[table] = sorted(data, key=lambda r: json.dumps(r, sort_keys=True))
        demo = next(r["id"] for r in rows["users"] if r["username"] == "demo")
        collection = sorted(r["release_id"] for r in rows["collection_items"] if r["user_id"] == demo)
        wantlist = sorted(r["release_id"] for r in rows["wantlist_items"] if r["user_id"] == demo)
        cart = sorted([r for r in rows["cart_items"] if r["user_id"] == demo], key=lambda r: r["id"])
        listings = sorted(rows["marketplace_listings"], key=lambda r: r["id"])
        listing_map = {r["id"]: r for r in listings}
        orders = sorted([r for r in rows["orders"] if r["buyer_user_id"] == demo], key=lambda r: r["id"])
        items = sorted(rows["order_items"], key=lambda r: r["id"])
        marker = [r for r in listings if r["comments"] == MARKER and r["seller_user_id"] == demo]
        if len(marker) > 1:
            raise RuntimeError("Ambiguous phase 1 listing marker")
        with _connect(BASELINE) as frozen:
            fixture_row = dict(frozen.execute("SELECT * FROM marketplace_listings WHERE id=1").fetchone())
        fixture = {"listing_id": 1, **{k: fixture_row[k] for k in ["release_id", "price_cents", "quantity", "status", "currency", "seller_user_id"]}}
        latest = orders[-1] if orders else None
        segments = {
            "collection_others": [r for r in rows["collection_items"] if not (r["user_id"] == demo and r["release_id"] == 221)],
            "wantlist_others": [r for r in rows["wantlist_items"] if not (r["user_id"] == demo and r["release_id"] == 221)],
            "cart_others": [r for r in rows["cart_items"] if r["user_id"] != demo],
            "orders_others": [r for r in rows["orders"] if r["buyer_user_id"] != demo],
        }
        return {
            "demo_user_id": demo, "collection_ids": collection, "wantlist_ids": wantlist,
            "cart": cart, "cart_count": len(cart),
            "cart_total_cents": sum(listing_map[r["listing_id"]]["price_cents"] * r["quantity"] for r in cart),
            "orders": orders, "order_count": len(orders), "order_items": items,
            "latest_demo_order": latest,
            "latest_demo_order_items": [r for r in items if latest and r["order_id"] == latest["id"]],
            "listings": listings,
            "demo_listings": [r for r in listings if r["seller_user_id"] == demo],
            "demo_listing_count": sum(r["seller_user_id"] == demo for r in listings),
            "phase1_listing": marker[0] if marker else None,
            "fixture": fixture,
            "catalog": {"release_id": 221, "title": next(r["title"] for r in rows["releases"] if r["id"] == 221)},
            "table_hashes": {t: _hash(data) for t, data in rows.items()},
            "table_counts": {t: len(data) for t, data in rows.items()},
            "segment_hashes": {s: _hash(data) for s, data in segments.items()},
        }


def evaluate(case: dict, before: dict, after: dict) -> list[dict]:
    fixed = _case(case)
    kind = fixed["parameters"]["kind"]
    b, a = before["backend"], after["backend"]
    ui = after["ui"]
    path = urlparse(ui["url"]).path
    text = ui["text"]
    checks = []

    def check(id: str, passed: bool, detail: str) -> None:
        checks.append({"id": id, "passed": bool(passed), "detail": detail})

    allowed = {
        "invalid_login": set(), "catalog_search": set(), "anonymous_collection": set(),
        "collection_add": {"collection_items"}, "wantlist_add": {"wantlist_items"},
        "cart_add": {"cart_items"},
        "checkout": {"cart_items", "orders", "order_items", "marketplace_listings"},
        "seller_create_deactivate": {"marketplace_listings"},
    }[kind]
    unchanged = [t for t in b["table_hashes"] if t not in allowed]
    check("unrelated_tables_unchanged", all(b["table_hashes"][t] == a["table_hashes"][t] for t in unchanged),
          "Unchanged tables: " + ", ".join(unchanged))
    if kind == "invalid_login":
        check("invalid_credentials_visible", path == "/login" and "Invalid credentials" in text,
              "Invalid password must remain at login and display backend refusal")
    elif kind == "catalog_search":
        check("release_detail_reached", path == "/release/221" and "The Dark Side Of The Moon" in text,
              "Requested search result detail is rendered")
    elif kind == "anonymous_collection":
        check("authentication_gate", path == "/login", "Anonymous mutation reaches login")
    elif kind in {"collection_add", "wantlist_add"}:
        collection = kind == "collection_add"
        field = "collection_ids" if collection else "wantlist_ids"
        table = "collection_items" if collection else "wantlist_items"
        segment = "collection_others" if collection else "wantlist_others"
        page = "/me/collection" if collection else "/me/wantlist"
        check("exact_target_added", 221 not in b[field] and a[field] == sorted(b[field] + [221])
              and a["table_counts"][table] == b["table_counts"][table] + 1,
              "Exactly one target membership persisted for demo")
        check("other_memberships_unchanged", b["segment_hashes"][segment] == a["segment_hashes"][segment],
              "All other membership rows preserved")
        check("list_page_visible", path == page and "The Dark Side Of The Moon" in text,
              "Persisted membership is visible on the requested list page")
    elif kind == "cart_add":
        expected_price = b["fixture"]["price_cents"]
        check("exact_cart", len(a["cart"]) == 1 and a["cart"][0]["listing_id"] == 1
              and a["cart"][0]["quantity"] == 1 and a["cart_total_cents"] == expected_price,
              "One unit of listing 1 with exact seeded price")
        check("cart_page_visible", path == "/cart" and "The Dark Side Of The Moon" in text,
              "Cart UI renders target release")
        check("other_carts_unchanged", b["segment_hashes"]["cart_others"] == a["segment_hashes"]["cart_others"],
              "Other users' carts preserved")
    elif kind == "checkout":
        previous = {r["id"]: r for r in b["orders"]}
        new = [r for r in a["orders"] if r["id"] not in previous]
        preserved = all(previous.get(r["id"]) == r for r in a["orders"] if r["id"] in previous)
        check("single_paid_order", len(new) == 1 and len(a["orders"]) == len(b["orders"]) + 1
              and new[0]["status"] == "paid" and new[0]["total_cents"] == b["fixture"]["price_cents"]
              and new[0]["currency"] == "USD" and preserved, "One new exact paid order, previous orders preserved")
        added_items = [r for r in a["order_items"] if r["id"] not in {r["id"] for r in b["order_items"]}]
        check("exact_order_item", len(new) == 1 and len(added_items) == 1
              and added_items[0]["order_id"] == new[0]["id"] and added_items[0]["listing_id"] == 1
              and added_items[0]["quantity"] == 1 and added_items[0]["price_cents"] == b["fixture"]["price_cents"],
              "Order item matches one unit of listing 1")
        old_items = [r for r in a["order_items"] if r["id"] in {r["id"] for r in b["order_items"]}]
        check("prior_order_items_preserved", old_items == b["order_items"], "No previous order item modified")
        target_b = next(r for r in b["listings"] if r["id"] == 1)
        target_a = next(r for r in a["listings"] if r["id"] == 1)
        check("only_listing_status_changed", target_a == {**target_b, "status": "sold"}
              and [r for r in a["listings"] if r["id"] != 1] == [r for r in b["listings"] if r["id"] != 1],
              "Only listing 1 changes active to sold; quantity preserved by original backend")
        check("cart_cleared", a["cart"] == [] and "Your cart is empty" in text and path == "/cart", "Cart emptied in DB and UI")
        check("other_users_unchanged", all(b["segment_hashes"][s] == a["segment_hashes"][s] for s in ["cart_others", "orders_others"]),
              "Other users' cart and order rows preserved")
    elif kind == "seller_create_deactivate":
        p = fixed["parameters"]
        old = {r["id"]: r for r in b["listings"]}
        created = [r for r in a["listings"] if r["id"] not in old]
        exact = len(created) == 1
        if exact:
            row = created[0]
            exact = all(row[key] == p[key] for key in ["release_id", "price_cents", "quantity", "comments", "ships_from", "media_condition", "sleeve_condition"])
            exact = exact and row["seller_user_id"] == a["demo_user_id"] and row["currency"] == "USD" and row["status"] == "inactive"
        check("exact_listing_created_deactivated", exact, "One demo-owned marker listing with exact fields ends inactive")
        check("existing_listings_preserved", [r for r in a["listings"] if r["id"] in old] == b["listings"], "Existing listing rows unchanged")
        check("seller_page_visible", path == "/sell" and "inactive" in text and "The Dark Side Of The Moon" in text,
              "Seller listing remains visible as inactive")
    return checks
