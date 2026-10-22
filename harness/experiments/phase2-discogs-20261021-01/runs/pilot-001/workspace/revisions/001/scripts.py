def prediction(disposition="unknown", changed=None, count=None, claims=None, unknowns=None):
    return {"disposition":disposition,"effects":{"persistent_state_changed":changed,"affected_record_count":count},"ui_claims":claims or [],"unknowns":unknowns or []}

def go(h, path, why):
    h.expect(prediction("accepted",False,0),why)
    h.page.goto(h.origin+path)
    return h.observe(why)

def click(h, loc, why, p=None):
    if loc.count()!=1 or not loc.is_visible():
        raise ValueError("Target not uniquely visible: "+why)
    h.expect(p or prediction(unknowns=["Effect to discover"]),why)
    loc.click()
    return h.observe(why)

def fill(h,loc,value,why):
    if loc.count()!=1 or not loc.is_visible():
        raise ValueError("Target not uniquely visible: "+why)
    h.expect(prediction("accepted",False,0),why)
    loc.fill(value)
    return h.observe(why)


def run(h):
    """Initial checkpoint: home observation only."""
    print(go(h,"/","Initial checkpoint home inspection"))
