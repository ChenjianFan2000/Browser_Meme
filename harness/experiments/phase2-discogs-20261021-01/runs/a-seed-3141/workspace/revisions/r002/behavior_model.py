"""Condition A: executable, evidence-bounded behavior predictions.

Intent schema: {op, release_id, listing_id, ...parameters}. Observation schema:
authenticated, release_id, wantlist_contains, collection_contains, listing_status,
cart_items [{listing_id,quantity,status}], selected_release_id, media_condition,
sleeve_condition, ships_from, price_cents, quantity, comments. URL and visible_text
may also be supplied; they establish only visible page identity/auth redirects.
Unknown entities/parameter combinations remain unknown. See rules.json for bounded
verified claims and hypotheses. This module performs no browser or network work.
"""
import re

KNOWN_RELEASES = (84,153,221)
KNOWN_CART_LISTINGS = (4,7,12,19,641,642,643,644,645,646)
KNOWN_OWN_LISTINGS = (640,641,642,643,644,645,646)

def prediction_shape(disposition="unknown",changed=None,count=None,claim=None,unknowns=None):
    return {"disposition":disposition,"effects":{"persistent_state_changed":changed,"affected_record_count":count},"ui_claims":[] if claim is None else [{"claim":claim,"evidence_expected":"Rendered DOM and sanitized UI-caused response; persisted readback where required"}],"unknowns":unknowns or ([] if disposition!="unknown" else ["Conditions exceed the observed cases"])}

def predict(observation,intent):
    o=observation if isinstance(observation,dict) else {}
    i=intent if isinstance(intent,dict) else {"op":intent}
    if i.get("scope")=="whole_task" or "steps" in i:
        return prediction_shape(unknowns=["Whole-task compositions are not established by per-action evidence"])
    op=str(i.get("op",i.get("action",""))).strip().lower().replace(" ","_")
    aliases={"add_wantlist":"add_to_wantlist","add_collection":"add_to_collection","cart_add":"add_to_cart","deactivate":"deactivate_listing","remove":"remove_cart_item","apply_filters":"filter_marketplace"}
    op=aliases.get(op,op)
    url=o.get("url","")
    if not isinstance(url,str): url=""
    text=o.get("visible_text",o.get("text","")) or ""
    if not isinstance(text,str): text=""
    auth=o.get("authenticated")
    if auth is None:
        if "/login" in url and "Sign in" in text: auth=False
        elif any(v in text for v in ["My Collection","My Wantlist","Create and manage your marketplace listings.","Items you've added from the marketplace."]): auth=True
    rid=i.get("release_id",o.get("release_id"))
    if rid is None:
        m=re.search(r"/release/(\d+)",url)
        if m: rid=int(m.group(1))
    lid=i.get("listing_id",o.get("listing_id"))
    if op in ("fill","select","hover"):
        return prediction_shape("accepted",False,0,"No target business record is changed by this form/menu action")
    if op in ("add_to_wantlist","add_to_collection"):
        observed = (rid in (84,221)) or (rid==153 and op=="add_to_collection")
        if not observed: return prediction_shape(unknowns=["Membership behavior for this release/operation is untested"])
        if auth is False:
            if (rid==221 and op=="add_to_wantlist") or (rid==153 and op=="add_to_collection"):
                return prediction_shape("rejected",False,0,"Redirects to login with the release as next; no membership is added")
            return prediction_shape(unknowns=["Guest behavior for this precise release/action is a hypothesis"])
        if auth is True:
            key="wantlist_contains" if op=="add_to_wantlist" else "collection_contains"
            membership=o.get(key)
            if membership is False:
                return prediction_shape("accepted",True,1,"One membership persists; immediate sidebar count increases while release-summary count stays stale until navigation")
            if membership is True and (rid==221 or (rid==84 and op=="add_to_wantlist")):
                return prediction_shape("accepted",False,0,"Immediate sidebar count rises optimistically; persisted membership and aggregate stay unchanged after navigation")
            return prediction_shape(unknowns=["Prior membership or this repeat condition is not known, so persistent change/count cannot be determined"])
    if op=="create_listing":
        if auth is not True: return prediction_shape(unknowns=["Authentication is not established for submission"])
        selected=i.get("selected_release_id",o.get("selected_release_id"))
        if selected is None and o.get("selection_absent") is True:
            return prediction_shape("rejected",False,0,"Create Listing is disabled without a selected release")
        if selected not in (153,221): return prediction_shape(unknowns=["Creation for this release has not been observed"])
        p=i.get("price_cents",o.get("price_cents")); q=i.get("quantity",o.get("quantity"))
        if p in (0,-1): return prediction_shape("rejected",False,0,"Create Listing is disabled at this price")
        if selected==221:
            if q in (-1,0,1.5) and p in (1234,1999):
                return prediction_shape("rejected",False,0,"Server quantity validation is displayed; no listing is created")
            if p==1.5 and q==1:
                return prediction_shape("rejected",False,0,"Server integer validation for price_cents is displayed")
            for key in ("media_condition","sleeve_condition","ships_from"):
                if i.get(key,o.get(key))=="":
                    return prediction_shape("rejected",False,0,"Server minimum-length validation for "+key+" is displayed")
        if isinstance(p,bool) or isinstance(q,bool): return prediction_shape()
        media=i.get("media_condition",o.get("media_condition"))
        sleeve=i.get("sleeve_condition",o.get("sleeve_condition"))
        country=i.get("ships_from",o.get("ships_from"))
        cases=(selected==221 and (p,q,media) in [(1234,2,"Near Mint (NM or M-)"),(1,1,"Near Mint (NM or M-)"),(2,1,"Experimental Grade3141"),(3,1,"Near Mint (NM or M-)")]) or (selected==153 and (p,q,media)==(1111,3,"Near Mint (NM or M-)"))
        comment=i.get("comments",o.get("comments"))
        observed_comments={(221,1234,2):["Learner3141 controlled listing","Learner3141 task helper validation"],(221,1,1):["Learner3141 minimum-price experiment"],(221,2,1):["Learner3141 condition experiment"],(221,3,1):[""],(153,1111,3):["Learner3141 duplicate experiment"]}
        if cases and sleeve=="Very Good Plus (VG+)" and country=="US" and comment in observed_comments.get((selected,p,q),[]):
            return prediction_shape("accepted",True,1,"One new active listing appears in My Listings")
        return prediction_shape(unknowns=["Hypothesis: other positive integer prices/quantities with nonempty required strings are accepted; limits and this exact combination are untested"])
    if op=="deactivate_listing" and auth is True and lid in KNOWN_OWN_LISTINGS:
        state=i.get("listing_status",o.get("listing_status"))
        if state=="active" and lid in (640,642,644,646):
            return prediction_shape("accepted",True,1,"Listing becomes inactive; Deactivate remains; marketplace omits it")
        if state=="sold" and lid==643:
            return prediction_shape("accepted",True,1,"Sold listing becomes inactive; Deactivate remains")
        if state=="inactive" and lid==640:
            return prediction_shape("accepted",False,0,"Listing remains inactive with Deactivate still present")
        return prediction_shape(unknowns=["Deactivation from this listing/status has not been observed"])
    if op=="add_to_cart":
        state=i.get("listing_status",o.get("listing_status"))
        if auth is False and lid==7:
            return prediction_shape("rejected",False,0,"Login next preserves /cart?add=7; login can later complete the add")
        if auth is True and ((lid==4 and state=="sold") or (lid==642 and state=="inactive")):
            return prediction_shape("rejected",False,0,"UI-caused add returns Listing not found; the page can silently show the unchanged cart")
        if auth is True and lid in KNOWN_CART_LISTINGS and state=="active":
            return prediction_shape("accepted",True,1,"One unit is added; same listing shares its cart row and total increases by unit price")
    if op=="remove_cart_item" and auth is True:
        if lid in (7,12,19,642,644,645,646) and o.get("cart_contains_target") is True:
            return prediction_shape("accepted",True,1,"The entire target cart row disappears; other rows remain and the total adjusts")
    if op=="checkout" and auth is True:
        items=o.get("cart_items")
        if items==[]: return prediction_shape("rejected",False,0,"Checkout is disabled for the empty cart")
        if isinstance(items,list):
            if not all(isinstance(v,dict) for v in items): return prediction_shape()
            ids=[v.get("listing_id") for v in items]
            if not all(isinstance(v,int) and not isinstance(v,bool) for v in ids): return prediction_shape()
            if ids==[642] and items[0].get("status")=="inactive":
                return prediction_shape("rejected",False,0,"Unavailable-listing error replaces cart controls; navigating back reveals retained cart")
            if sorted(ids)==[643,644] and any(v.get("listing_id")==644 and v.get("status")=="inactive" for v in items):
                return prediction_shape("rejected",False,0,"Unavailable-listing error; both rows persist and active643 remains active")
            observed=(ids==[4] and items[0].get("quantity")==2) or (sorted(ids)==[7,641] and all(v.get("quantity")==1 for v in items)) or (ids==[643] and items[0].get("quantity")==1)
            if observed and all(v.get("status")=="active" for v in items):
                return prediction_shape("accepted",True,None,"A paid order is returned, cart clears, and purchased listings cease to be active",["Exact changed-record count includes order-related effects not fully enumerated by allowed observations"])
    if op=="search":
        q=i.get("query")
        if q in ("pink floyd","PINK FLOYD","moon","3141-no-such-release","","rock","Classic Rock"):
            claim="Search renders matching release links" if q in ("pink floyd","PINK FLOYD","moon") else "No release result links appear; empty query shows an enter-query prompt"
            return prediction_shape("accepted",False,0,claim)
    if op=="filter_marketplace" and rid==221:
        f=i.get("filters",{})
        if not isinstance(f,dict): return prediction_shape()
        if any(k not in ("media_condition","sleeve_condition","ships_from","min_rating","sort") for k in f): return prediction_shape()
        values=tuple(str(f.get(k,"")) for k in ("media_condition","sleeve_condition","ships_from","min_rating"))+(str(f.get("sort","price_asc")),)
        cases=[("","","US","","price_asc"),("","","US","95","price_desc"),("Mint (M)","","US","95","price_desc"),("Mint (M)","","us","95","price_desc"),("","","Sweden","99.1","price_asc"),("Good","","Sweden","99.1","price_asc"),("Good (G)","","Sweden","99.1","price_asc"),("Good (G)","Near Mint (NM or M-)","Sweden","99.1","price_asc"),("Good (G)","Near Mint (NM or M-)","Sweden","99.2","price_asc"),("","","","","newest"),("Good (G)","","Sweden","99.1","price_desc")]
        if values in cases:
            return prediction_shape("accepted",False,0,"Applying these observed filters changes URL and rendered rows",["Exact row set depends on the current active listings"])
        return prediction_shape(unknowns=["Hypothesis: other filter values use the same equality/intersection semantics; this combination has not been observed"])
    if op=="sign_out" and auth is True:
        return prediction_shape("accepted",False,0,"Returns to public home; cart membership can persist for the same account")
    if op=="sign_in" and i.get("credential_source")=="fixture":
        next_path=i.get("next", "/")
        if next_path in ("/","/cart","/release/153"):
            return prediction_shape("accepted",False,0,"Returns to the requested page without replaying a collection add")
        if next_path=="/cart?add=7":
            return prediction_shape("accepted",True,1,"Returns to cart and adds one unit of listing7")
    if op in ("remove_from_collection","remove_from_wantlist","activate_listing","edit_listing"):
        return prediction_shape(unknowns=["No such successful control/action was observed; absence of controls is not proof of absent backend behavior"])
    return prediction_shape()
