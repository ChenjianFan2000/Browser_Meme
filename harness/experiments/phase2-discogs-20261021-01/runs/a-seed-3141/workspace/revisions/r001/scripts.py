def pred(disposition="unknown", changed=None, count=None, claim=None, unknown="Outcome not yet observed"):
    return {"disposition":disposition,"effects":{"persistent_state_changed":changed,"affected_record_count":count},"ui_claims":([] if claim is None else [{"claim":claim,"evidence_expected":"Rendered DOM and UI-caused response"}]),"unknowns":([unknown] if disposition=="unknown" else [])}

def go(h,path,why="Read discovered page"):
    h.expect(pred(),why)
    h.page.goto(h.origin+path)
    return obs(h,"navigate")

def act(h,loc,method="click",value=None,why="Probe visible control",prediction=None):
    if loc.count()!=1:
        h.note("locator: expected one target, found "+str(loc.count()))
        return None
    if not loc.is_visible():
        h.note("locator: target is not visible; no action")
        return None
    if not loc.is_enabled():
        h.note("business_rule: disabled control; no action")
        return None
    h.expect(prediction or pred(),why)
    if method == "click": loc.click()
    elif method == "fill": loc.fill(value)
    elif method == "press": loc.press(value)
    elif method == "select": loc.select_option(value)
    elif method == "check": loc.check()
    elif method == "uncheck": loc.uncheck()
    elif method == "hover": loc.hover()
    else:
        h.note("implementation: unsupported method")
        return None
    return obs(h,why)

def obs(h,label):
    o=h.observe(label)
    print({"label":label,"url":o.get("url"),"dom":o.get("dom"),"main":h.page.locator("main").inner_text()[:650] if h.page.locator("main").count()==1 else o.get("visible_text"),"network":o.get("network")})
    return o

# Native task entry points. Callers supply ids/hrefs observed in the current task.
# Every actual UI action is predicted and read back. No retry loop is provided.
def sign_in(h):
    go(h,"/login")
    act(h,h.page.locator("main input").nth(0),"fill",h.fixture["account"]["username"],"Enter supplied username",pred("accepted",False,0))
    act(h,h.page.locator('input[type="password"]'),"fill",h.fixture["account"]["password"],"Enter supplied password",pred("accepted",False,0))
    return act(h,h.page.get_by_role("button",name="Sign in",exact=True),why="Sign in with fixture credentials")

def search(h,query):
    go(h,"/")
    act(h,h.page.get_by_placeholder("Search artists, albums and more..."),"fill",query,"Set search query",pred("accepted",False,0))
    return act(h,h.page.get_by_role("button",name="Search",exact=True),why="Submit catalogue search",prediction=pred("accepted",False,0))

def add_membership(h,release_path,kind):
    if kind not in ("Wantlist","Collection"): return None
    go(h,release_path)
    result=act(h,h.page.get_by_role("button",name="Add to "+kind,exact=True),why="Add observed release to "+kind)
    if result is not None: go(h,release_path,"Check persisted aggregate after add")
    return result

def filter_marketplace(h,marketplace_path,fields):
    go(h,marketplace_path)
    for key in ("media_condition","sleeve_condition","ships_from","min_rating"):
        if key in fields:
            act(h,h.page.locator('input[name="'+key+'"]'),"fill",str(fields[key]),"Set "+key,pred("accepted",False,0))
    if "sort" in fields:
        act(h,h.page.locator('select[name="sort"]'),"select",fields["sort"],"Set sort",pred("accepted",False,0))
    return act(h,h.page.get_by_role("button",name="Apply",exact=True),why="Apply marketplace filters",prediction=pred("accepted",False,0))

def create_listing(h,title,media,sleeve,country,quantity,price_cents,comments):
    go(h,"/sell")
    act(h,h.page.get_by_placeholder("Search releases..."),"fill",title,"Find release")
    act(h,h.page.locator("main").get_by_role("button",name="Search",exact=True),why="Load seller search results")
    # Caller must inspect selection; exact title search selected first result in observed cases.
    selected=h.page.get_by_text("Selected: "+title,exact=False)
    if selected.count()!=1:
        h.note("locator: selection needs review; no business submission")
        return None
    f=h.page.locator("main input")
    if f.count()!=7:
        h.note("locator: seller field layout differs; no business submission")
        return None
    for idx,value in [(1,media),(2,sleeve),(3,country),(4,str(quantity)),(5,str(price_cents)),(6,comments)]:
        act(h,f.nth(idx),"fill",value,"Set seller field "+str(idx),pred("accepted",False,0))
    return act(h,h.page.get_by_role("button",name="Create Listing",exact=True),why="Submit listing once; inspect result before another write")

def add_cart(h,marketplace_path,observed_add_href):
    go(h,marketplace_path)
    return act(h,h.page.locator('a[href="'+observed_add_href+'"]'),why="Add observed listing once")

def remove_cart_row(h,unique_row_locator):
    return act(h,unique_row_locator.get_by_role("button",name="Remove",exact=True),why="Remove specified observed cart row once")

def checkout_current_cart(h):
    go(h,"/cart")
    return act(h,h.page.get_by_role("button",name="Checkout",exact=True),why="Checkout observed cart once; verify order response and empty cart")

def run(h):
    return go(h,"/","Default read-only discovery entry point")
