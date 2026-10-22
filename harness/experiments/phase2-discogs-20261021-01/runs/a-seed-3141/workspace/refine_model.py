from pathlib import Path
p=Path('revisions/r002/behavior_model.py');s=p.read_text()
s=s.replace('643,644,645)','643,644,645,646)')
s=s.replace('if state=="active" and lid in (640,642,644):','if state=="active" and lid in (640,642,644,646):')
s=s.replace('        if state=="inactive" and lid==640:', '        if state=="sold" and lid==643:\n            return prediction_shape("accepted",True,1,"Sold listing becomes inactive; Deactivate remains")\n        if state=="inactive" and lid==640:')
s=s.replace('lid in (7,12,19,642,644,645)', 'lid in (7,12,19,642,644,645,646)')
s=s.replace('            return prediction_shape("accepted",None,None,"Add remains available; sidebar count rises",["Prior membership or this repeat condition is not known, so persistent change/count cannot be determined"])','            return prediction_shape(unknowns=["Prior membership or this repeat condition is not known, so persistent change/count cannot be determined"])')
s=s.replace('            ids=[v.get("listing_id") for v in items]','            if not all(isinstance(v,dict) for v in items): return prediction_shape()\n            ids=[v.get("listing_id") for v in items]\n            if not all(isinstance(v,int) and not isinstance(v,bool) for v in ids): return prediction_shape()')
s=s.replace('        media=i.get("media_condition",o.get("media_condition"))','        if isinstance(p,bool) or isinstance(q,bool): return prediction_shape()\n        media=i.get("media_condition",o.get("media_condition"))')
s=s.replace('        if cases and sleeve=="Very Good Plus (VG+)" and country=="US":','        comment=i.get("comments",o.get("comments"))\n        observed_comments={(221,1234,2):["Learner3141 controlled listing","Learner3141 task helper validation"],(221,1,1):["Learner3141 minimum-price experiment"],(221,2,1):["Learner3141 condition experiment"],(221,3,1):[""],(153,1111,3):["Learner3141 duplicate experiment"]}\n        if cases and sleeve=="Very Good Plus (VG+)" and country=="US" and comment in observed_comments.get((selected,p,q),[]):')
s=s.replace('    if op=="filter_marketplace" and rid==221:\n        return prediction_shape("accepted",False,0,"Applying filters changes the URL and rendered rows without changing business records",["Exact row set depends on current listings; equality/intersection, percentage rating and sort were verified only for documented values"])','''    if op=="filter_marketplace" and rid==221:
        f=i.get("filters",{})
        if not isinstance(f,dict): return prediction_shape()
        values=tuple(str(f.get(k,"")) for k in ("media_condition","sleeve_condition","ships_from","min_rating"))+(str(f.get("sort","price_asc")),)
        cases=[("","","US","","price_asc"),("","","US","95","price_desc"),("Mint (M)","","US","95","price_desc"),("Mint (M)","","us","95","price_desc"),("","","Sweden","99.1","price_asc"),("Good","","Sweden","99.1","price_asc"),("Good (G)","","Sweden","99.1","price_asc"),("Good (G)","Near Mint (NM or M-)","Sweden","99.1","price_asc"),("Good (G)","Near Mint (NM or M-)","Sweden","99.2","price_asc"),("","","","","newest"),("Good (G)","","Sweden","99.1","price_desc")]
        if values in cases:
            return prediction_shape("accepted",False,0,"Applying these observed filters changes URL and rendered rows",["Exact row set depends on the current active listings"])
        return prediction_shape(unknowns=["Hypothesis: other filter values use the same equality/intersection semantics; this combination has not been observed"])''')
s=s.replace('    if op in ("remove_from_collection"','''    if op=="sign_out" and auth is True:
        return prediction_shape("accepted",False,0,"Returns to public home; cart membership can persist for the same account")
    if op=="sign_in" and i.get("credential_source")=="fixture":
        next_path=i.get("next", "/")
        if next_path in ("/","/cart","/release/153"):
            return prediction_shape("accepted",False,0,"Returns to the requested page without replaying a collection add")
        if next_path=="/cart?add=7":
            return prediction_shape("accepted",True,1,"Returns to cart and adds one unit of listing7")
    if op in ("remove_from_collection"''')
p.write_text(s)
Path('experiments/behavior_model_v4.py').write_text(s)
