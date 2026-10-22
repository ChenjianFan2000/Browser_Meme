"""Native Playwright entry points; pass this and behavior_model.py as workspace modules.

run(h) is a read-only home inspection. Other functions are called by a task wrapper.
No function retries a write. Caller must stop on any timeout/unconfirmed write.
The runtime confirms targets and scrolls them into view when dispatching UI actions.
Only current rendered controls/attributes and naturally caused network are consumed.
Positive listing creation helper is UNTESTED beyond its quantity rejection path.
"""
from behavior_model import predict

def _unknown(why):
    return {"disposition":"unknown","effects":{"persistent_state_changed":None,"affected_record_count":None},"ui_claims":[],"unknowns":[why]}

def _authenticated(h):
    """Read current hydrated header; absence stays False and predictor abstains."""
    control=h.page.get_by_role("button",name="Account",exact=True)
    return control.count()==1 and control.is_visible()

def _ready(loc):
    if loc.count()!=1:
        raise ValueError("locator: expected one target; no action performed")
    loc.wait_for(state="visible",timeout=10000)
    if not loc.is_enabled():
        raise ValueError("business_rule: target disabled; inspect boundary without clicking")

def navigate(h,path):
    if not path.startswith("/") or path.startswith("//") or "?add=" in path:
        raise ValueError("Use observed same-origin read navigation paths only")
    h.expect(predict({"url":h.page.url,"authenticated":_authenticated(h)},{"action":"navigate","path":path}),"Navigate to observed route "+path)
    h.page.goto(h.origin+path)
    return h.observe("navigation-readback")

def _click(h,loc,prediction,why):
    _ready(loc)
    h.expect(prediction,why)
    loc.click()
    observation=h.observe(why+" readback")
    h.note("Readback captured; no automatic business retry. Inspect response and persistent view before another write.")
    return observation

def _fill(h,loc,value,why):
    _ready(loc)
    h.expect({"disposition":"accepted","effects":{"persistent_state_changed":False,"affected_record_count":0},"ui_claims":[],"unknowns":[]},why)
    loc.fill(str(value))
    return h.observe(why+" readback")

def login(h):
    navigate(h,"/login")
    form=h.page.locator("form").filter(has=h.page.get_by_role("button",name="Sign in",exact=True))
    _fill(h,form.locator("input").first,h.fixture["account"]["username"],"Fill fixture username")
    _fill(h,h.page.locator('input[type="password"]'),h.fixture["account"]["password"],"Fill fixture password")
    _click(h,h.page.get_by_role("button",name="Sign in",exact=True),predict({"url":h.page.url},{"action":"login","credentials_kind":"fixture"}),"Sign in once")
    h.page.get_by_role("button",name="Account",exact=True).wait_for(state="visible",timeout=10000)
    return h.observe("hydrated-authenticated-header")

def search_catalog(h,query):
    navigate(h,"/")
    _fill(h,h.page.get_by_placeholder("Search artists, albums and more..."),query,"Stage catalog search")
    return _click(h,h.page.get_by_role("button",name="Search",exact=True),predict({"url":h.page.url,"authenticated":_authenticated(h)},{"action":"search_catalog","query":query}),"Submit catalog search")

def membership(h,release_id,kind):
    """Inspect separate list first. Returns observed membership; no write."""
    if kind not in ["collection","wantlist"]:
        raise ValueError("Unknown list kind")
    navigate(h,"/me/"+kind)
    h.page.get_by_text("My Collection" if kind=="collection" else "My Wantlist",exact=True).wait_for(state="visible",timeout=10000)
    return h.page.locator('main a[href="/release/'+str(release_id)+'"]').count()==1

def add_membership(h,release_id,kind):
    present=membership(h,release_id,kind)
    navigate(h,"/release/"+str(release_id))
    h.page.get_by_role("button",name="Account",exact=True).wait_for(state="visible",timeout=10000)
    obs={"url":h.page.url,"authenticated":_authenticated(h),"membership":{kind:present}}
    intent={"action":"add_"+kind,"release_id":release_id}
    _click(h,h.page.get_by_role("button",name="Add to "+("Collection" if kind=="collection" else "Wantlist"),exact=True),predict(obs,intent),"Add to "+kind+" once")
    confirmed=membership(h,release_id,kind)
    if not confirmed:
        raise ValueError("unconfirmed: membership absent from readback; stop without retry")
    return h.observe("persistent-list-membership-confirmed")

def cart_snapshot(h):
    navigate(h,"/cart")
    h.page.get_by_role("button",name="Checkout",exact=True).wait_for(state="visible",timeout=10000)
    return h.observe("cart-ready")

def add_cart(h,marketplace_path,listing_id,current_cart_items):
    """Current items must come from a fresh permitted UI-caused cart observation."""
    navigate(h,marketplace_path)
    loc=h.page.locator('main a[href="/cart?add='+str(listing_id)+'"]')
    _ready(loc)
    p=predict({"url":h.page.url,"authenticated":_authenticated(h),"target_visible":True,"cart_items":current_cart_items},{"action":"add_cart","listing_id":listing_id})
    _click(h,loc,p,"Add exact observed listing once")
    return cart_snapshot(h)

def remove_cart(h,release_title,seller,current_cart_items):
    """Only proceeds with one item, avoiding a wrong seller when title is repeated."""
    cart_snapshot(h)
    if len(current_cart_items)!=1:
        raise ValueError("locator: multiple-item card disambiguation untested")
    item=current_cart_items[0].get("listing",{})
    if item.get("release_title")!=release_title or item.get("seller_username")!=seller:
        raise ValueError("locator: caller's item identity does not match")
    p=predict({"authenticated":_authenticated(h),"cart_items":current_cart_items},{"action":"remove_cart"})
    _click(h,h.page.get_by_role("button",name="Remove",exact=True),p,"Remove confirmed sole item once")
    return cart_snapshot(h)

def checkout(h,current_cart_items):
    cart_snapshot(h)
    p=predict({"authenticated":_authenticated(h),"cart_items":current_cart_items},{"action":"checkout"})
    _click(h,h.page.get_by_role("button",name="Checkout",exact=True),p,"Checkout confirmed cart once")
    print(h.network())
    return cart_snapshot(h)

def filter_marketplace(h,path,fields):
    navigate(h,path)
    for key in ["media_condition","sleeve_condition","ships_from","min_rating"]:
        if key in fields:
            _fill(h,h.page.locator('input[name="'+key+'"]'),fields[key],"Stage "+key)
    if "sort" in fields:
        loc=h.page.locator('select[name="sort"]'); _ready(loc)
        h.expect(_unknown("Selection changes staged UI; Apply commits query"),"Stage marketplace sort")
        loc.select_option(fields["sort"])
        h.observe("sort-readback")
    intent=dict(fields); intent["action"]="filter_marketplace"
    return _click(h,h.page.get_by_role("button",name="Apply",exact=True),predict({"url":h.page.url,"authenticated":_authenticated(h)},intent),"Apply marketplace filters")

def select_selling_release(h,query):
    navigate(h,"/sell")
    _fill(h,h.page.get_by_placeholder("Search releases..."),query,"Search selling release")
    return _click(h,h.page.locator("main").get_by_role("button",name="Search",exact=True),predict({"url":h.page.url,"authenticated":_authenticated(h)},{"action":"search_selling","query":query}),"Find selling release")

def stage_listing(h,values):
    """Call after reading selected result; selector order guarded against changed UI."""
    fields=h.page.locator("main input")
    if fields.count()!=7:
        raise ValueError("locator: selling form structure changed")
    mapping={"media_condition":1,"sleeve_condition":2,"ships_from":3,"quantity":4,"price_cents":5,"comments":6}
    for key in mapping:
        if key in values:
            _fill(h,fields.nth(mapping[key]),values[key],"Stage "+key)
    button=h.page.get_by_role("button",name="Create Listing",exact=True)
    return {"enabled":button.is_enabled(),"observation":h.observe("staged-listing")}

def submit_listing(h,selected_release_id,values):
    """Positive success untested. Caller must inspect result; no blind repetition."""
    intent=dict(values); intent["action"]="create_listing"
    return _click(h,h.page.get_by_role("button",name="Create Listing",exact=True),predict({"authenticated":_authenticated(h),"selected_release_id":selected_release_id},intent),"Submit listing once")

def run(h):
    print(navigate(h,"/"))
