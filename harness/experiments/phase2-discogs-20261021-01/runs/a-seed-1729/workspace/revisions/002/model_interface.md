# Behavior model interface

`predict(observation, intent)` is pure Python and returns the public prediction
shape. It reads no files and performs no actions. Intents are structured dicts;
free text and malformed/unrecognized input return unknown. Rules in rules.json
and their original evidence bound all predictions. Evidence links and hashes are
in that file and evidence_manifest.json.

Always distinguish a per-action forecast from a whole-task forecast. This model
covers individual operations only. It makes no private-task success claim.
A predicted accepted operation still needs browser readback. Authentication is
excluded from persistent business-state effects. Membership counts refer to the
targeted relationship, cart counts to the targeted cart record. Checkout leaves
affected_record_count null because the full number of changed business records
is not established.

Common facts:

- `account_scope: "supplied_fixture"`: caller has established that this is the
  supplied account; an Account button alone does not prove its identity.
- `authenticated: true`: current rendered signed-in account UI was observed.
- Unknown or omitted facts must not be filled by assumption.

Supported intents and additional observed facts:

| operation | facts needed | scope |
| --- | --- | --- |
| `auth.sign_in` | `page_kind:"login"`, `fixture_credentials_supplied:true` | Only supplied valid account; no blank/incorrect credential rejection learned |
| `wantlist.add` | intent `release_id:221`; `memberships.wantlist` boolean | First and one repeated addition |
| `collection.add` | intent `release_id:221`; `memberships.collection` boolean and `memberships.wantlist:true` | First and one repeat after wantlist addition |
| `cart.add` | intent `listing_id`; `listing_link_visible:true`, `listing_active:true`, `listing_price_cents`, complete `cart` | Exact three baseline/add transitions in call009 |
| `cart.checkout` | exact complete `cart` | One observed paid checkout in call010 |

A complete `cart` is `{ "items": [{"listing_id": 4, "quantity": 1,
"price_cents": 2145}], "total_cents": 2145 }`. A known empty cart has items=[]
and total_cents=0. Completeness is essential; an omitted line is not absence.

The exact cart-add contexts are listing4 into empty cart, listing7 into cart
containing listing4 quantity1, and repeating listing7 when listing4 and listing7
each have quantity1. Prices must be 2145/2285 cents. Other cart combinations,
stock limits and inactive listings are unknown. The exact checkout context has
listing4 quantity1 plus listing7 quantity2, total6715. Order IDs and timestamps
are not predicted. See R008-R011 and their actual network evidence.

Aliases: `login`, `add_to_wantlist`, `add_to_collection`, `add_to_cart`, `checkout`.
The key `action` may be used instead of `operation`. Unsupported operations return
unknown. The model is deliberately conservative outside observed conditions.

For native execution, supply scripts.py and behavior_model.py as own helper
modules to phase2.execute_script, with a small workspace wrapper exporting
`def run(h):`. Available script functions are `sign_in`, `inspect_release`,
`add_membership`, `add_to_cart`, `checkout_once`, and `inspect_selling`.
`run(h)` only inspects release221. Revised helpers were checked offline; the
original executed experiments remain unchanged in experiments/.

The current learning run stopped at a runtime boundary. These scripts are left
for later authorized task execution; they must not be used to resume this run.
