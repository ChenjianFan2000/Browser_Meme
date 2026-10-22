"""Evidence-bounded predictor, condition A. See rules.json for evidence.
observation: authenticated, release_id, wantlist_contains, collection_contains,
listing_id, listing_status, cart_items, selected_release_id, price_cents, quantity.
intent: dict with op and parameters, or an operation string. No network access.
Effects count changed business records, not optimistic UI counters.
"""
def predict(observation, intent):
    o = observation if isinstance(observation, dict) else {}
    i = intent if isinstance(intent, dict) else {"op": intent}
    op = i.get("op", i.get("action"))
    out = {"disposition": "unknown", "effects": {"persistent_state_changed": None, "affected_record_count": None}, "ui_claims": [], "unknowns": ["Operation or conditions are outside observed evidence"]}
    def known(disposition, changed, count, claim):
        return {"disposition": disposition, "effects": {"persistent_state_changed": changed, "affected_record_count": count}, "ui_claims": [{"claim": claim, "evidence_expected": "Rendered DOM after action, plus UI-caused response or navigation readback"}], "unknowns": []}
    if op in ("fill", "select", "hover"):
        return known("accepted", False, 0, "Only the visible control state changes")
    rid = i.get("release_id", o.get("release_id"))
    if op in ("add_to_wantlist", "add_to_collection") and rid == 221:
        if o.get("authenticated") is False and op == "add_to_wantlist":
            return known("rejected", False, 0, "Login page with next=/release/221 appears")
        if o.get("authenticated") is True:
            key = "wantlist_contains" if op == "add_to_wantlist" else "collection_contains"
            membership = o.get(key)
            if membership is not None:
                return known("accepted", not membership, 0 if membership else 1, "Immediate sidebar counter rises by one; Add button remains; persisted membership is unique")
    if op == "create_listing" and o.get("authenticated") is True and o.get("selected_release_id") == 221:
        p = i.get("price_cents", o.get("price_cents"))
        q = i.get("quantity", o.get("quantity"))
        if p in (0, -1):
            return known("rejected", False, 0, "Create Listing is disabled; no submission occurs")
        if q in (0, 1.5) and p in (1234, 1999):
            return known("rejected", False, 0, "A quantity validation response is rendered")
    if op == "deactivate_listing" and o.get("authenticated") is True and i.get("listing_id", o.get("listing_id")) == 640:
        state = o.get("listing_status")
        if state in ("active", "inactive"):
            return known("accepted", state == "active", 1 if state == "active" else 0, "Listing is inactive, retains Deactivate, and is absent from marketplace")
    if op == "add_to_cart" and o.get("authenticated") is True and i.get("listing_id") in (4, 7) and o.get("listing_status") == "active":
        return known("accepted", True, 1, "Cart gains one unit of this listing; same-listing additions share one cart row")
    if op == "remove_cart_item" and o.get("authenticated") is True and o.get("cart_listing_ids") == [7]:
        return known("accepted", True, 1, "Cart becomes empty and total is USD 0.00")
    return out
