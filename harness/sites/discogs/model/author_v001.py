"""Independent gpt-6.1-sol source-visible experiment artifact authoring."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SITE = ROOT / "harness/sites/discogs"
SRC = "veri_env/external/VeriEnv-main/websites/discogs/"
OUT = SITE / "model/v001"

def ref(path, line):
    return f"{SRC}{path}:{line}"

def eq(path, value):
    return {"path": path, "op": "eq", "value": value}

def cmp(path, op, value):
    return {"path": path, "op": op, "value": value}

def same(path):
    return {"path": f"after.backend.{path}", "op": "eq", "value_from": f"before.backend.{path}"}

def unchanged():
    return [same("table_hashes")]

def protected(*names):
    return [same(n) for n in names]

def rule(id, statement, refs, preconditions, branches, forbidden):
    return {"id": id, "statement": statement, "source_refs": refs,
            "preconditions": preconditions, "branches": branches,
            "forbidden_side_effects": forbidden, "status": "source_supported"}

rules = [
 rule("R_NAV", "GET navigation and controlled input edits do not mutate business tables; authentication token creation also leaves business rows unchanged.",
      [ref("frontend/src/components/Header.tsx",22),ref("backend/app/api/auth.py",39),ref("backend/app/api/catalog.py",352)],
      ["Isolated baseline and fresh browser session; allowed local origin."],
      ["Source route renders requested page.","Unavailable backend or missing resource is an execution error, not a successful business endpoint."],
      ["No collection, wantlist, cart, listing, order or catalog mutations."]),
 rule("R_AUTH", "Login matches username or email and verifies password. Invalid credentials return HTTP400 detail Invalid credentials; successful token response sets httpOnly sameSite=lax discogs_token and LoginClient replaces URL with next (default /).",
      [ref("backend/app/api/auth.py",39),ref("frontend/src/app/api/auth/login/route.ts",5),ref("frontend/src/app/login/LoginClient.tsx",28)],
      ["Login form loaded; username/password supplied."],
      ["Valid seeded demo credentials navigate to next.","Invalid password remains at login with Invalid credentials error."],
      ["No business rows change on success or refusal."]),
 rule("R_SEARCH", "Header search submits q to /search. Backend trims q and uses case-insensitive title/main-artist substring search, ordered year descending then title, limit30. Blank query gives no results. ReleaseCard links to its release detail.",
      [ref("frontend/src/components/Header.tsx",22),ref("backend/app/api/catalog.py",352),ref("frontend/src/app/search/page.tsx",16),ref("frontend/src/components/ReleaseCard.tsx",21)],
      ["Catalog fixture contains release221 The Dark Side Of The Moon."],
      ["Matching query displays linked release card, whose detail includes metadata/tracklist.","No match produces an empty results grid, not a mutation."],
      ["All backend business state remains unchanged."]),
 rule("R_GATE", "Anonymous collection/wantlist POST requires bearer authentication; ReleaseActions handles HTTP401 by navigating to /login?next=/release/<id> without adding membership. Private collection/wantlist/cart/sell pages also redirect on401.",
      [ref("backend/app/api/deps.py",15),ref("frontend/src/components/ReleaseActions.tsx",23),ref("frontend/src/app/me/collection/page.tsx",23)],
      ["Fresh browser with no auth cookie; existing release."],
      ["401 navigates to login and leaves all business rows unchanged.","With valid auth, operation is handled by membership rule."],
      ["No anonymous collection addition or unrelated mutation."]),
 rule("R_COLLECTION", "Authenticated collection addition checks release existence, inserts one user/release pair if absent and returns {ok:true}; repeated add is idempotent in backend. Collection page reads real membership and renders ReleaseCard. ReleaseActions increments local Have after each successful POST, including duplicate POST, so local counter alone is not membership truth.",
      [ref("backend/app/api/account.py",39),ref("backend/app/api/account.py",66),ref("backend/app/models/collection.py",12),ref("frontend/src/components/ReleaseActions.tsx",32),ref("frontend/src/app/me/collection/page.tsx",57)],
      ["Authenticated demo; existing221; reset removes demo221 membership."],
      ["New membership contains221; My Collection renders221.","Existing membership returns ok unchanged.","Missing release returns404; anonymous request gated."],
      ["Wantlist, carts, orders, listings and catalog remain unchanged."]),
 rule("R_WANT", "Authenticated wantlist addition inserts at most one user/release pair and returns {ok:true}; wantlist page reads membership. Local Want counter increments on every successful POST even if backend already contains pair.",
      [ref("backend/app/api/account.py",82),ref("backend/app/api/account.py",109),ref("backend/app/models/wantlist.py",12),ref("frontend/src/components/ReleaseActions.tsx",33),ref("frontend/src/app/me/wantlist/page.tsx",57)],
      ["Authenticated demo; existing221; reset removes demo221 wantlist membership."],
      ["Membership contains221 and My Wantlist renders221.","Duplicate returns ok with no extra pair.","Missing release404; anonymous request gated."],
      ["Collection, carts, orders, listings and catalog remain unchanged."]),
 rule("R_MARKET", "Marketplace shows only active listings for release, defaults price ascending, offers exact condition/country and minimum seller rating filters. Each source-derived Add to Cart anchor points to /cart?add=<listing_id>.",
      [ref("backend/app/api/marketplace.py",33),ref("frontend/src/app/sell/release/[id]/page.tsx",145)],
      ["Release221 exists; frozen listing1 active for221."],
      ["Listing1 anchor is present in unfiltered marketplace.","No matching filters shows explicit no listings text."],
      ["Reading/filtering marketplace never changes rows."]),
 rule("R_CART", "CartClient sees add query, POSTs listing_id quantity1 then replaces URL /cart and loads cart. Active listing required; backend returns201 CartOut including sum(price_cents*quantity). Existing row quantity adds with cap99. Remove uses authenticated user's row id. UI displays price and empty message but omits item quantity.",
      [ref("frontend/src/app/cart/CartClient.tsx",57),ref("backend/app/api/account.py",126),ref("backend/app/api/account.py",162),ref("backend/app/api/account.py",183)],
      ["Authenticated demo and empty frozen cart; listing1 active."],
      ["One effect-driven add produces one row listing1 quantity1 and total equal fixture.price_cents.","Missing/inactive listing returns404.","Anonymous add redirects to login with add target retained."],
      ["Add alone cannot create order, sell a listing or change collection/wantlist/catalog."]),
 rule("R_CHECKOUT", "Checkout on nonempty available cart creates paid USD order and order items at current listing prices, marks listing status sold, clears demo cart and commits. It does not decrement listing quantity. Empty cart returns400 and UI disables Checkout. UI reloads cart then alerts Checkout complete (order created).",
      [ref("backend/app/api/account.py",190),ref("frontend/src/app/cart/CartClient.tsx",163)],
      ["Authenticated demo; cart listing1 quantity1; listing1 remains active."],
      ["Paid order total equals listing1 fixture price; item quantity1; listing1 sold; cart empty.","Empty cart400 (disabled in UI).", "Unavailable cart listing400; no commit."],
      ["Do not decrement stock quantity, alter unrelated listings, memberships or catalog."]),
 rule("R_SELL", "Sell search selects the first release result. Create sends selected release, conditions, cents, USD, country, quantity and comments; schema requires positive cents and quantity1..99. Backend creates new active listing; page reloads own listings newest first. Deactivate sends DELETE for owned listing, sets status inactive and retains row; nonowned/missing listing404. Create disabled without selection or positive price.",
      [ref("frontend/src/app/sell/page.tsx",100),ref("frontend/src/app/sell/page.tsx",216),ref("frontend/src/app/sell/page.tsx",284),ref("backend/app/api/account.py",234),ref("backend/app/api/account.py",264),ref("backend/app/api/account.py",303),ref("backend/app/schemas/sell.py",6)],
      ["Authenticated demo; exact title search uniquely identifies221; original listings predate new row."],
      ["New marker listing has requested fields and active status, appears first in My Listings.","Deactivation changes newly created owned row to inactive and preserves all its other fields.","Invalid payload422; no selected release/nonpositive price prevented by UI."],
      ["No changes to preexisting listings, cart, orders, memberships or catalog."]),
]

readouts = {
 "search_query": {"kind":"value", "selector":"header input[name='q']"},
 "login_username": {"kind":"value", "selector":"form input:not([name]):not([type])"},
 "login_password": {"kind":"value", "selector":"form input[type='password']"},
 "target_cards": {"kind":"count", "selector":"main a[href='/release/221']"},
 "seller_query": {"kind":"value", "selector":"main input[placeholder='Search releases...']"},
 "newest_seller_row": {"kind":"text", "selector":"main section:nth-of-type(2) > div.divide-y > div:first-child"},
}
for name, num in [("media",1),("sleeve",2),("country",3),("quantity",4),("price",5),("comments",6)]:
    readouts[f"seller_{name}"]={"kind":"value", "selector":f"main section:first-of-type > div.grid > div:nth-child({num}) > input"}

cases = json.loads((SITE/"cases.json").read_text(encoding="utf-8-sig"))

def add(case, label, action, wait, checks, ids, inv=None):
    case["steps"].append({"id": f"{case['id']}.{label}","rule_ids":ids,"action":action,"wait":wait,
        "expect":[{"id":label,"checks":checks}],"invariants":unchanged() if inv is None else inv})

def opening(case, url, text, rule_id="R_NAV"):
    add(case,"open",{"kind":"open","url":url},{"kind":"text","value":text},[cmp("after.ui.text","contains",text)],[rule_id])

def login(case, target, target_text, ready_selector=None):
    opening(case,"/login?next="+target,"Sign in","R_AUTH")
    for name, selector, value in [("username","form input:not([name]):not([type])",case["parameters"]["username"]),
                                  ("password","form input[type='password']",case["parameters"]["password"])]:
        add(case,"fill_"+name,{"kind":"fill","selector":selector,"value":value},{"kind":"selector","value":selector},
            [eq("after.ui.fields.login_"+name,value)],["R_AUTH","R_NAV"])
    add(case,"sign_in",{"kind":"click","selector":"form:has(input[type='password']) button"},
        {"kind":"selector","value":ready_selector} if ready_selector else {"kind":"text","value":target_text},
        [cmp("after.ui.url","contains",target),cmp("after.ui.text","contains",target_text)],["R_AUTH"])

membership_unchanged = ("collection_ids","wantlist_ids","orders","order_items","listings","catalog")
for case in cases:
    case["steps"]=[]
    k=case["id"]
    if k=="invalid_login":
        opening(case,"/login","Sign in","R_AUTH")
        for name, selector in [("username","form input:not([name]):not([type])"),("password","form input[type='password']")]:
            value=case["parameters"][name]
            add(case,"fill_"+name,{"kind":"fill","selector":selector,"value":value},{"kind":"selector","value":selector},[eq("after.ui.fields.login_"+name,value)],["R_AUTH","R_NAV"])
        add(case,"reject",{"kind":"click","selector":"form:has(input[type='password']) button"},{"kind":"text","value":"Invalid credentials"},
            [cmp("after.ui.url","contains","/login"),cmp("after.ui.text","contains","Invalid credentials")],["R_AUTH"])
    elif k=="catalog_search":
        opening(case,"/search","Enter a query in the search bar.","R_SEARCH")
        q=case["parameters"]["query"]
        add(case,"query",{"kind":"fill","selector":"header input[name='q']","value":q},{"kind":"selector","value":"header input[name='q']"},[eq("after.ui.fields.search_query",q)],["R_SEARCH","R_NAV"])
        add(case,"search",{"kind":"click","selector":"header form[action='/search'] button"},{"kind":"selector","value":"main a[href='/release/221']"},[cmp("after.ui.url","contains","/search?"),eq("after.ui.fields.target_cards",1),cmp("after.ui.text","contains",q)],["R_SEARCH"])
        add(case,"detail",{"kind":"click","selector":"main a[href='/release/221']"},{"kind":"text","value":"Tracklist"},[cmp("after.ui.url","contains","/release/221"),cmp("after.ui.text","contains",q),cmp("after.ui.text","contains","Speak to Me")],["R_SEARCH"])
    elif k=="anonymous_collection":
        opening(case,"/release/221","Tracklist","R_SEARCH")
        add(case,"login_gate",{"kind":"click","selector":"button:has-text('Add to Collection')"},{"kind":"selector","value":"form input[type='password']"},[cmp("after.ui.url","contains","/login?next="),cmp("after.ui.text","contains","Sign in"),cmp("after.backend.collection_ids","not_contains",221)],["R_GATE"])
    elif k in ("collection_add","wantlist_add"):
        login(case,"/release/221","Tracklist","button:has-text('Add to Collection')")
        coll=k=="collection_add"
        field="collection_ids" if coll else "wantlist_ids"
        rid="R_COLLECTION" if coll else "R_WANT"
        button="Add to Collection" if coll else "Add to Wantlist"
        inv=protected("wantlist_ids" if coll else "collection_ids","cart","orders","order_items","listings","catalog")
        add(case,"add",{"kind":"click","selector":f"button:has-text('{button}')"},{"kind":"selector","value":f"button:has-text('{button}'):not([disabled])"},[cmp("after.backend."+field,"contains",221)],[rid],inv)
        page="collection" if coll else "wantlist"
        add(case,"verify_membership",{"kind":"open","url":"/me/"+page},{"kind":"selector","value":"main a[href='/release/221']"},[eq("after.ui.fields.target_cards",1),cmp("after.ui.text","contains","My Collection" if coll else "My Wantlist"),cmp("after.backend."+field,"contains",221)],[rid])
    elif k in ("cart_add","checkout"):
        login(case,"/sell/release/221","Marketplace listings","main a[href='/cart?add=1']")
        add(case,"add_listing",{"kind":"click","selector":"main a[href='/cart?add=1']"},{"kind":"selector","value":"button:has-text('Remove'):not([disabled])"},
            [eq("after.backend.cart_count",1),eq("after.backend.cart.0.listing_id",1),eq("after.backend.cart.0.quantity",1),{"path":"after.backend.cart_total_cents","op":"eq","value_from":"after.backend.fixture.price_cents"},cmp("after.ui.text","contains","The Dark Side Of The Moon")],["R_MARKET","R_CART"],protected(*membership_unchanged))
        if k=="checkout":
            add(case,"pay",{"kind":"click","selector":"button:has-text('Checkout')"},{"kind":"text","value":"Your cart is empty."},
                [eq("after.backend.cart",[]),eq("after.backend.cart_total_cents",0),eq("after.backend.listings.0.status","sold"),{"path":"after.backend.table_counts.orders","op":"gt","value_from":"before.backend.table_counts.orders"},eq("after.backend.latest_demo_order.status","paid"),eq("after.backend.latest_demo_order.currency","USD"),{"path":"after.backend.latest_demo_order.total_cents","op":"eq","value_from":"after.backend.fixture.price_cents"},eq("after.backend.latest_demo_order_items.0.listing_id",1),eq("after.backend.latest_demo_order_items.0.quantity",1),{"path":"after.backend.latest_demo_order_items.0.price_cents","op":"eq","value_from":"after.backend.fixture.price_cents"},cmp("after.ui.text","contains","Your cart is empty.")],["R_CHECKOUT"],
                protected("collection_ids","wantlist_ids","catalog")+[{"path":"after.backend.listings.0.quantity","op":"eq","value_from":"before.backend.listings.0.quantity"}])
    elif k=="seller_create_deactivate":
        login(case,"/sell","Create a listing","main input[placeholder='Search releases...']")
        title="The Dark Side Of The Moon"
        add(case,"query",{"kind":"fill","selector":"main input[placeholder='Search releases...']","value":title},{"kind":"selector","value":"main input[placeholder='Search releases...']"},[eq("after.ui.fields.seller_query",title)],["R_SELL","R_NAV"])
        add(case,"find_release",{"kind":"click","selector":"main section:first-of-type button:has-text('Search')"},{"kind":"text","value":"Selected:"},[cmp("after.ui.text","contains","Selected: Pink Floyd - The Dark Side Of The Moon"),cmp("after.ui.text","contains","#221")],["R_SELL"])
        for name,num,key in [("media",1,"media_condition"),("sleeve",2,"sleeve_condition"),("country",3,"ships_from"),("quantity",4,"quantity"),("price",5,"price_cents"),("comments",6,"comments")]:
            value=str(case["parameters"][key]); selector=f"main section:first-of-type > div.grid > div:nth-child({num}) > input"
            add(case,"set_"+name,{"kind":"fill","selector":selector,"value":value},{"kind":"selector","value":selector},[eq("after.ui.fields.seller_"+name,value)],["R_SELL","R_NAV"])
        no_other=protected("collection_ids","wantlist_ids","cart","orders","order_items","catalog")
        add(case,"create",{"kind":"click","selector":"button:has-text('Create Listing')"},{"kind":"selector","value":"button:has-text('Create Listing'):not([disabled])"},
            [{"path":"after.backend.table_counts.marketplace_listings","op":"gt","value_from":"before.backend.table_counts.marketplace_listings"},eq("after.backend.phase1_listing.release_id",221),eq("after.backend.phase1_listing.price_cents",1999),eq("after.backend.phase1_listing.quantity",1),eq("after.backend.phase1_listing.currency","USD"),eq("after.backend.phase1_listing.comments",case["parameters"]["comments"]),eq("after.backend.phase1_listing.ships_from","US"),eq("after.backend.phase1_listing.media_condition",case["parameters"]["media_condition"]),eq("after.backend.phase1_listing.sleeve_condition",case["parameters"]["sleeve_condition"]),{"path":"after.backend.phase1_listing.seller_user_id","op":"eq","value_from":"after.backend.demo_user_id"},eq("after.backend.phase1_listing.status","active"),cmp("after.ui.fields.newest_seller_row","contains",title),cmp("after.ui.fields.newest_seller_row","contains","active"),cmp("after.ui.fields.newest_seller_row","contains","USD 19.99")],["R_SELL"],no_other)
        add(case,"deactivate_new",{"kind":"click","selector":"main section:nth-of-type(2) > div.divide-y > div:first-child button:has-text('Deactivate')"},{"kind":"text","value":"inactive"},
            [eq("after.backend.phase1_listing.status","inactive"),cmp("after.ui.fields.newest_seller_row","contains",title),cmp("after.ui.fields.newest_seller_row","contains","inactive"),{"path":"after.backend.table_counts.marketplace_listings","op":"eq","value_from":"before.backend.table_counts.marketplace_listings"}],["R_SELL"],no_other+[same("phase1_listing."+n) for n in ("id","release_id","price_cents","quantity","currency","comments","ships_from","media_condition","sleeve_condition","seller_user_id","created_at")])

bundle={"schema_version":1,"site_id":"discogs","model":"gpt-6.1-sol","revision":"v001","rules":rules,"readouts":readouts,"cases":cases,
 "limitations":[
 "Source-supported white-box hypotheses, not measured runtime results. Fresh model context is not OS-enforced isolation; this context is disqualified as a future phase2 learner.",
 "Eight fixed development goals; no official benchmark or complete site coverage. Filters, duplicate membership, invalid sell payload, missing-resource paths, cart removal and empty checkout are source-described but not exercised in these cases.",
 "Single CartClient effect-driven add is predicted; development-mode React effect duplication or search-parameter rerenders remain a runtime integration uncertainty and must be diagnosed if exact quantity1 is contradicted.",
 "Checkout alert may require generic browser dialog handling; it is not an extra business step. Every wait/readback and management observation belongs in measured execution time.",
 "Optional page-specific readouts are absent on other routes and may yield null plus observation errors; only evidence named in checks is used to confirm a branch.",
 "Seller newest-row selector follows source newest-created ordering; exact marker/ownership and preexisting-row preservation require independent adapter evaluation, not model UI counters alone.",
 "No private evaluator code, private data or prior experimental answers read; no browser experimentation, API mutation or source modifications used in generation. Public upstream demo credentials are intentionally used for fixed cases.",
 "Source refs describe implemented success and refusal semantics; actual backend responses are not collected directly by generated UI actions. No claims for strict speed controls, phase2 exploration or phase3 held-out generalization."]}

consulted=[
 "AGENTS.md","实验方案.md","harness/CONTRACT.md","harness/sites/discogs/cases.json","harness/sites/discogs/adapter_contract.md","harness/sites/discogs/site.json",
 *[SRC+p for p in ["frontend/src/components/ReleaseActions.tsx","frontend/src/app/login/LoginClient.tsx","backend/app/api/account.py","backend/app/api/marketplace.py","frontend/src/app/cart/CartClient.tsx","frontend/src/app/sell/release/[id]/page.tsx","frontend/src/app/me/collection/page.tsx","frontend/src/app/me/wantlist/page.tsx","frontend/src/components/Header.tsx","backend/app/db/seed.py","frontend/src/app/search/page.tsx","frontend/src/app/sell/page.tsx","backend/app/api/auth.py","frontend/src/app/release/[id]/page.tsx","backend/app/api/catalog.py","frontend/src/app/api/auth/login/route.ts","frontend/src/components/CookieBanner.tsx","frontend/src/components/ReleaseCard.tsx","frontend/src/app/layout.tsx","backend/app/api/deps.py","backend/app/schemas/sell.py","frontend/src/lib/backend.ts","frontend/src/lib/api.ts","backend/app/models/collection.py","backend/app/models/wantlist.py","backend/app/models/cart.py","backend/app/models/marketplace.py","backend/app/models/order.py"]]]

OUT.mkdir(parents=True,exist_ok=True)
target=OUT/"bundle.json"
if target.exists():
    raise SystemExit("v001 already exists; never overwrite immutable model generation")
target.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
provenance={"model":"gpt-6.1-sol","revision":"v001","generation_mode":"Independent session subagent source-visible phase1; no remote API call","bundle_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"total_ui_steps":sum(len(c["steps"]) for c in cases),"consulted_files":[{"path":p,"sha256":hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in consulted],"source_unchanged":True,"browser_experimentation_before_generation":False,"private_evaluator_access":False,"actual_model_tokens_and_cost":"not supplied by runtime"}
(OUT/"provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"bundle":str(target),"steps":provenance["total_ui_steps"],"sha256":provenance["bundle_sha256"]}))
