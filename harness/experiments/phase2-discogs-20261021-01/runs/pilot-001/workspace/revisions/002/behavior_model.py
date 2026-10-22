"""Condition A predictor, frozen to this pilot's browser evidence.

predict(observation, intent) consumes dictionaries, with raw observations also accepted.
Intent keys: action (see aliases below), scope ('action' default; tasks remain unknown),
release_id, listing_id, query, quantity, price_cents, ships_from, min_rating, sort.
Observation keys: url, visible_text, authenticated, membership ('collection'/'wantlist'
to bool), cart_items (sanitized UI-caused cart items), target_visible, target_enabled,
selected_release_id. Supply only values read from the current permitted browser state.
Do not infer authenticated=True merely from a successful navigation.
Unknown input and states outside the observed sample deliberately abstain.
Only the supplied fixture account is in scope. No source, credentials, APIs, hidden state, or private task data are read here.
"""

def _result(disposition="unknown", changed=None, count=None, claims=None, unknowns=None):
    return {"disposition":disposition,"effects":{"persistent_state_changed":changed,"affected_record_count":count},"ui_claims":[{"claim":c,"evidence_expected":e} for c,e in (claims or [])],"unknowns":unknowns or []}

def _unknown(why):
    return _result(unknowns=[why])

def _number(value):
    try:
        return int(value)
    except (ValueError,TypeError):
        return None

def predict(observation, intent):
    if not isinstance(observation,dict):
        return _unknown("A structured current browser observation is required.")
    if isinstance(intent,str):
        intent={"action":intent}
    if not isinstance(intent,dict):
        return _unknown("Intent must be a dictionary or an action label.")
    if intent.get("scope","action")!="action":
        return _unknown("Whole-task combinations were not evaluated; this model predicts individual actions only.")
    action=str(intent.get("action",intent.get("operation",""))).lower().strip().replace(" ","_")
    aliases={"add_to_collection":"add_collection","add_to_wantlist":"add_wantlist","add_to_cart":"add_cart","create_listing":"create_listing","sign_in":"login","remove":"remove_cart","search":"search_catalog","apply":"filter_marketplace"}
    action=aliases.get(action,action)
    url=str(observation.get("url",""))
    text=str(observation.get("visible_text",""))
    auth=observation.get("authenticated") is True
    release=_number(intent.get("release_id"))
    if action=="login" and url.endswith("/login"):
        if intent.get("credentials_kind")=="fixture":
            return _result("accepted",False,0,[("Successful sign-in returns to /","Home URL after bounded wait; authenticated Account button on hydrated header")],["Authentication is excluded from target business record counts; only supplied fixture account was tested."])
        if intent.get("credentials_kind")=="observed_invalid_password":
            return _result("rejected",False,0,[("Login remains on /login with Invalid credentials","Rendered error text")],["Only the pilot's distinct invalid password was tried."])
    if action in ["add_collection","add_wantlist"] and auth and release==84 and url.endswith("/release/84"):
        kind="collection" if action=="add_collection" else "wantlist"
        present=observation.get("membership",{}).get(kind)
        if not isinstance(present,bool):
            return _unknown("Current account membership must be checked in the separate list view; the Add label is insufficient.")
        counter="Have" if kind=="collection" else "Want"
        return _result("accepted",not present,0 if present else 1,[("Add button retains its Add label","Release DOM after click"),("The sidebar "+counter+" count rises locally by one","Immediate release sidebar readback"),("Release 84 appears once in the account "+kind,"Fresh account list DOM and a fresh release visit")],["Main-page counters can remain stale until navigation.","Only release 84 and this supplied account were tested; hidden record metadata is unknown."])
    if action=="add_cart" and auth and observation.get("target_visible") is True:
        listing=_number(intent.get("listing_id"))
        items=observation.get("cart_items")
        if not isinstance(items,list):
            return _unknown("Read the current cart before predicting quantity changes.")
        if any(_number(x.get("listing",{}).get("listing_id")) not in [354,355] for x in items):
            return _unknown("A cart combination outside the observed sample is present.")
        old=next((x for x in items if _number(x.get("listing",{}).get("listing_id"))==listing),None)
        if listing==354 and (not items or (len(items)==1 and old and old.get("quantity")==1)):
            quantity=2 if old else 1
            return _result("accepted",True,1,[("Cart shows release 84 from caseyjones17","Fresh /cart DOM"),("Total is USD "+("34.38" if quantity==2 else "17.19"),"Cart summary; UI-caused cart response quantity is "+str(quantity))],["Only transitions 0→1 and 1→2 were observed; stock ceilings and other cart combinations are unknown."])
        if listing==355 and not items:
            return _result("accepted",True,1,[("Cart shows release 84 from melanie9414 and total USD 18.05","Fresh /cart DOM and UI-caused cart response")])
    if action=="remove_cart" and auth:
        items=observation.get("cart_items")
        if isinstance(items,list) and len(items)==1 and _number(items[0].get("listing",{}).get("listing_id"))==355 and items[0].get("quantity")==1:
            return _result("accepted",True,1,[("Cart is empty with total USD 0.00","Fresh /cart DOM and UI-caused response")])
    if action=="checkout" and auth:
        items=observation.get("cart_items")
        if items==[]:
            return _result("unknown",None,None,[("Checkout is disabled for an empty cart","disabled attribute on Checkout")],["This is a UI boundary; an empty-cart backend submission was not attempted."])
        if isinstance(items,list) and len(items)==1 and _number(items[0].get("listing",{}).get("listing_id"))==354 and items[0].get("quantity")==2:
            return _result("accepted",True,None,[("A paid order for total 3438 cents is returned","Sanitized response naturally caused by Checkout"),("Cart becomes empty with USD 0.00 total","Fresh cart DOM and naturally caused response")],["Order ID and creation time vary; record count and inventory effects are unknown. No receipt page was observed."])
    if action=="filter_marketplace" and auth and "/sell/release/84" in url and intent.get("ships_from")=="US" and intent.get("sort")=="price_desc":
        rating=intent.get("min_rating")
        if rating in [None,""]:
            return _result("accepted",False,0,[("Exactly two rows: USD 37.63 then USD 18.05","Marketplace table after Apply")])
        if str(rating)=="99":
            return _result("accepted",False,0,[("No listings match these filters.","Marketplace table after Apply"),("Marketplace listings count is 0","Marketplace heading after Apply")])
    if action=="search_catalog" and auth and intent.get("query")=="Pink Floyd":
        return _result("accepted",False,0,[("Search returns three release cards for Pink Floyd","/search?q=Pink+Floyd DOM")],["Other queries, case matching, pagination, and artist object results were not tested."])
    if action=="search_selling" and auth and url.endswith("/sell") and intent.get("query")=="Open-architected maximized Local Area Network":
        return _result("accepted",False,0,[("Unique result #84 is automatically selected","Selected: Chavez Trio - Open-architected maximized Local Area Network")],["Multiple-result selection behavior remains unknown."])
    if action=="create_listing" and auth and observation.get("selected_release_id")==84:
        price=_number(intent.get("price_cents")); quantity=_number(intent.get("quantity"))
        if price==0:
            return _result("unknown",None,None,[("Create Listing is disabled with zero price","disabled attribute in sell form")],["No backend price-zero rejection was observed. The pilot click timed out; write effect is conservatively unconfirmed."])
        if quantity==0 and price==1729 and intent.get("media_condition")=="Near Mint (NM or M-)" and intent.get("sleeve_condition")=="Very Good Plus (VG+)" and intent.get("ships_from")=="US":
            return _result("rejected",False,0,[("Quantity validation says Input should be greater than or equal to 1","Rendered validation and natural 422 response")],["Positive-quantity creation and all other validation combinations are unknown."])
    if action=="navigate" and auth and intent.get("path")=="/add-release":
        return _result("rejected",False,0,[("404 This page could not be found.","Rendered /add-release page")],["The observed route failure does not establish absence of backend release creation."])
    return _unknown("Intent or current conditions fall outside the observed browser evidence.")
