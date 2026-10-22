"""Reusable native Playwright entry points. Supply identities from current allowed
observations. No APIs, JS evaluation, hidden retries, or hardcoded credentials.
Use execute_script modules=["revisions/r002/scripts.py","revisions/r002/behavior_model.py"].
Every helper returns None if a target is missing/ambiguous/disabled. Callers MUST
stop dependent operations on None. A failed/unknown business write needs evidence
review; these helpers never retry it. The runtime confirms and scrolls targets.
"""
import re
from behavior_model import predict

def snapshot(h):
    text=h.page.locator("body").inner_text()
    auth=None
    if h.page.get_by_role("button",name="Account",exact=True).count()==1:
        auth=True
    elif h.page.get_by_role("link",name="Account",exact=True).count()==1 or "/login" in h.page.url:
        auth=False
    return {"url":h.page.url,"visible_text":text,"authenticated":auth}

def readback(h,label):
    o=h.observe(label)
    print({"label":label,"url":o.get("url"),"dom":o.get("dom"),"text":o.get("visible_text","")[:600]})
    return o

def go(h,path,why="Navigate to previously observed page"):
    h.expect(predict(snapshot(h),{"op":"navigate","path":path}),why)
    h.page.goto(h.origin+path)
    return readback(h,why)

def act(h,loc,method="click",value=None,intent=None,context=None,why="Use observed control once"):
    if loc.count()!=1:
        h.note("locator: missing or ambiguous target; no action; stop dependent work")
        return None
    if not loc.is_visible() or not loc.is_enabled():
        h.note("locator or business_rule: invisible/disabled target; no action; stop dependent work")
        return None
    o=snapshot(h)
    if context: o.update(context)
    h.expect(predict(o,intent or {"op":method}),why)
    if method=="click": loc.click()
    elif method=="fill": loc.fill(value)
    elif method=="select": loc.select_option(value)
    elif method=="hover": loc.hover()
    elif method=="press": loc.press(value)
    elif method=="check": loc.check()
    elif method=="uncheck": loc.uncheck()
    else:
        h.note("implementation: unsupported method; no action")
        return None
    return readback(h,why)

def sign_in(h,use_current=False):
    if not use_current: go(h,"/login")
    if h.page.locator("main input").count()!=2: return None
    if act(h,h.page.locator("main input").nth(0),"fill",h.fixture["account"]["username"],why="Fill supplied username") is None: return None
    if act(h,h.page.locator('input[type="password"]'),"fill",h.fixture["account"]["password"],why="Fill supplied password") is None: return None
    return act(h,h.page.get_by_role("button",name="Sign in",exact=True),intent={"op":"sign_in"},why="Sign in once; preserve current next target")

def sign_out(h):
    if act(h,h.page.get_by_role("button",name="Account",exact=True),"hover",why="Expose account menu") is None: return None
    return act(h,h.page.get_by_role("button",name="Sign out",exact=True),intent={"op":"sign_out"},why="Sign out once")

def search(h,query):
    go(h,"/")
    if act(h,h.page.get_by_placeholder("Search artists, albums and more..."),"fill",query,why="Set public search query") is None: return None
    return act(h,h.page.get_by_role("button",name="Search",exact=True),intent={"op":"search","query":query},why="Submit catalogue text search")

def select_release_for_listing(h,query,release_id,artist_and_title):
    go(h,"/sell")
    if act(h,h.page.get_by_placeholder("Search releases..."),"fill",query,why="Find listing release") is None: return None
    if act(h,h.page.locator("main").get_by_role("button",name="Search",exact=True),why="Load seller search results") is None: return None
    choice=h.page.locator("main button").filter(has_text=re.compile(r"#"+str(release_id)+r"\s*$"))
    if act(h,choice,why="Explicitly select required release id") is None: return None
    if "Selected: "+artist_and_title not in h.page.locator("main").inner_text():
        h.note("locator: selection readback differs; stop before business write")
        return None
    return readback(h,"confirmed-release-selection")

def create_listing(h,query,release_id,artist_and_title,media,sleeve,country,quantity,price_cents,comments):
    if select_release_for_listing(h,query,release_id,artist_and_title) is None: return None
    f=h.page.locator("main input")
    if f.count()!=7:
        h.note("locator: field layout changed; no submission")
        return None
    for idx,value in [(1,media),(2,sleeve),(3,country),(4,str(quantity)),(5,str(price_cents)),(6,comments)]:
        if act(h,f.nth(idx),"fill",value,why="Set seller field "+str(idx)) is None: return None
        if f.nth(idx).input_value()!=value:
            h.note("implementation: field readback differs; no submission")
            return None
    before=h.page.locator("main section div.flex.items-center").count()
    intent={"op":"create_listing","selected_release_id":release_id,"media_condition":media,"sleeve_condition":sleeve,"ships_from":country,"quantity":quantity,"price_cents":price_cents,"comments":comments}
    result=act(h,h.page.get_by_role("button",name="Create Listing",exact=True),intent=intent,why="Submit listing once; no automatic retry")
    if result is None: return None
    after=h.page.locator("main section div.flex.items-center").count()
    h.note("Listing readback: prior rows="+str(before)+", after rows="+str(after)+". Inspect exported response if row count is not +1; no retry.")
    return result

def deactivate_own_listing(h,title,display_price,listing_id,expected_status):
    go(h,"/sell")
    row=h.page.locator("main section div.flex.items-center").filter(has_text=title).filter(has=h.page.get_by_text(display_price,exact=True)).filter(has=h.page.get_by_text(expected_status,exact=True))
    if row.count()!=1:
        h.note("locator: own listing identity/status is ambiguous; no action")
        return None
    return act(h,row.get_by_role("button",name="Deactivate",exact=True),intent={"op":"deactivate_listing","listing_id":listing_id},context={"listing_status":expected_status},why="Deactivate specified own listing once")

def filter_marketplace(h,release_id,fields):
    go(h,"/sell/release/"+str(release_id))
    for key in ("media_condition","sleeve_condition","ships_from","min_rating"):
        if key in fields:
            if act(h,h.page.locator('input[name="'+key+'"]'),"fill",str(fields[key]),why="Set "+key) is None: return None
    if "sort" in fields:
        if act(h,h.page.locator('select[name="sort"]'),"select",fields["sort"],why="Set marketplace sort") is None: return None
    return act(h,h.page.get_by_role("button",name="Apply",exact=True),intent={"op":"filter_marketplace","release_id":release_id,"filters":fields},why="Apply marketplace form")

def add_membership(h,release_id,kind,contains=None):
    if kind not in ("Collection","Wantlist"): return None
    go(h,"/release/"+str(release_id))
    key="collection_contains" if kind=="Collection" else "wantlist_contains"
    return act(h,h.page.get_by_role("button",name="Add to "+kind,exact=True),intent={"op":"add_to_"+kind.lower(),"release_id":release_id},context={key:contains},why="Add release membership once; check list or navigate for persistence")

def add_cart(h,release_id,listing_id):
    go(h,"/sell/release/"+str(release_id))
    return act(h,h.page.locator('a[href="/cart?add='+str(listing_id)+'"]'),intent={"op":"add_to_cart","listing_id":listing_id},context={"listing_status":"active"},why="Add one unit through the currently rendered marketplace link")

def remove_cart_item(h,title,seller,display_price,listing_id):
    go(h,"/cart")
    row=h.page.locator("main section div.flex.items-center").filter(has_text=title).filter(has_text="Seller: "+seller).filter(has=h.page.get_by_text(display_price,exact=True))
    return act(h,row.get_by_role("button",name="Remove",exact=True),intent={"op":"remove_cart_item","listing_id":listing_id},context={"cart_contains_target":True},why="Remove the entire uniquely identified cart row")

def checkout(h,observed_cart_items=None):
    go(h,"/cart")
    context={} if observed_cart_items is None else {"cart_items":observed_cart_items}
    return act(h,h.page.get_by_role("button",name="Checkout",exact=True),intent={"op":"checkout"},context=context,why="Checkout current observed cart once; review exported order/error and readback")

def run(h):
    return go(h,"/","Default read-only entry point")
