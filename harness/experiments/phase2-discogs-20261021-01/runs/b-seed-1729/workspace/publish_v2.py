import build_package as b
from pathlib import Path
import json
for r in b.RULES:
 if r['id']=='R17':
  r['statement']='With release12 selected, prices -1 and 0 disabled Create Listing and price1 enabled it. Quantity0 remained entered and left Create Listing enabled; submitting quantity0 subsequently returned 422 greater_than_equal 1, with no new listing in canonical readback. Quantity2 enabled creation. This corrects the parent r001 quantity-UI claim using original call16 and new call26 evidence.'
  r['evidence_refs']=b.refs(15,16,26)
 if r['id']=='U01':
  r['statement']='Checkout, larger and unusual numeric boundaries, arbitrary accounts, unobserved routes, membership deletion and listing reactivation remain unknown.'
b.rule('R24','Release1 listing creation accepted media_condition NotACondition1729 with otherwise default valid fields, returning listing641 quantity1 price1999. The custom condition string was displayed in marketplace.',[22])
b.rule('R25','Adding listing641 with stock quantity1 twice was accepted: cart item4 quantity changed from1 to2, total cart increased from6888 to8887 cents. A stock-at-one cap hypothesis is refuted for this cart operation; checkout inventory handling remains unknown.',[22,23])
b.rule('R26','Submitting identical release1 listing fields again returned distinct listing642; My Listings showed two separate active cards where previously there was one. This example was not deduplicated.',[22,24])
b.rule('R27','Listing search for Pink Floyd automatically selected first result153. Explicitly clicking result221 selected it; repeating the same search reset selection to153. No-match and empty listing searches cleared selection and disabled Create Listing.',[24,28])
b.rule('R28','Release12 condition filter Very Good yielded no rows but Very Good (VG) matched melanie9414. With that condition, ships_from germany yielded no rows while Germany matched. Adding incompatible sleeve Mint (M) excluded the row; clearing sleeve restored it.',[25])
b.rule('R29','Quantity1.5 and price_cents1.5 submissions each returned422 int_from_float at the corresponding field. Correcting both to integer1 then created listing643 at USD0.01 quantity1, preserved in My Listings.',[27])
b.rule('R30','Inactive listing640 still had an enabled Deactivate button. Repeating Deactivate returned success and retained inactive owner state, absence from marketplace and existing cart line.',[28,29])
b.rule('R31','Release12 min_rating92.7 included three sellers including the92.7% seller;92.71 excluded that seller and left two. Minimum-1 included all three. Literal abc caused an application error on this route; subsequent home navigation recovered.',[30,31])
b.rule('R32','The tested global title query Business-focused and its lowercase spelling both included release1 among3 results. Whitespace-padded Pink Floyd returned3 results. Columbia,2008 and rock each returned no release cards in this catalog. Do not generalize the full search field set from these examples.',[31])
b.rule('R33','Rock Releases, Rock Artists and Alternative Rock links navigated to search routes; observed Forum and Blog links rendered404. These rendered failures do not determine backend community capability.',[32])
b.rule('R34','Blank media_condition,sleeve_condition,ships_from left Create Listing enabled but submission returned422 string_too_short with a separate minimum-length1 error for each field. My Listings canonical readback contained no new entry.',[33])
b.rule('R35','After listing640 was inactive, revisiting its previously observed UI navigation route /cart?add=640 produced a rejected add and unchanged cart readback. This is distinct from retained pre-existing cart membership.',[17,18,34])
if __name__=='__main__':
 d=b.publish('r002','r001',34)
 rev=json.loads((d/'revision.json').read_text());rev['rationale']='Correct parent R17 with original enabled-state evidence and confirmed zero-quantity backend rejection; add discriminating string, number, duplicate, stock, selection and inactive-cart experiments. Preserve r001 and all failed scripts.';(d/'revision.json').write_text(json.dumps(rev,indent=2)+'\n')
 cov=json.loads((d/'coverage.json').read_text());cov['explored']+=['quantity0 and fractional numeric server rejection','one-cent successful listing','custom condition and empty-string boundaries','duplicate listing creates distinct record','stock-one repeated cart add','inactive add rejection via previously observed UI route','case-sensitive exact marketplace text filters','rating threshold and invalid-format application error','listing selection cleared/reset by searches','community404 routes'];cov['unexplored']=['checkout','larger inventory limits and checkout stock checks','membership removal','listing reactivation','arbitrary users','unobserved routes'];cov['current_competing_hypotheses']=[{'question':'Checkout with inactive and overstock items','alternatives':['rejects cart','ignores invalid item','accepts','UI placeholder'],'distinguishing_experiment':'One final click with cart, listing and network readback; stop if effect remains unconfirmed'}];(d/'coverage.json').write_text(json.dumps(cov,indent=2)+'\n')
 print(d)
