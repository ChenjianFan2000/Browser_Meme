# Browser-only generic runtime

The sole browser MCP tool is `browser.execute_script`. Write a workspace-relative
Python file exporting `def run(h)` and pass `script_path`; optional `modules`
are workspace-relative pure Python helper module files. Use native Playwright
locators on `h.page`. No target-specific actions or fixed selectors are supplied.

Each call creates a NEW browser, context and Page at `about:blank`. Only cookies
and localStorage persist through private storage_state; open pages and
sessionStorage do not. Every call must explicitly predict and navigate to
`h.origin` or a known same-origin path before using locators. No navigation is
performed implicitly. Ordinary missing/multiple/hidden/disabled target failures
return `failure_category: localization` without closing the broker; revise the
script and make another call. Permission and observation-policy denials remain
persistently closed.

- `h.origin`: the sole allowed HTTP origin. Use `h.page.goto(h.origin)` to start.
- `h.fixture`: public experimental inputs. Treat unspecified facts as unknown.
- `h.expect(prediction, rationale='')`: required immediately before every UI
  action, including navigation, fill, click, keyboard, scroll, and hover.
  `prediction` is a dict with `disposition` equal to `accepted`, `rejected`, or
  `unknown`; record predicted UI/state effects and uncertainty as extra fields.
- `h.confirm(locator)`: require one visible, enabled target, scroll it into view,
  and record tag/role/name/id/text identity. Does not consume a separate action.
- `h.observe(label='observation')`: save projected DOM, CDP accessibility tree,
  masked screenshot, visible text, and permitted network responses. DOM removes
  script elements and executable attributes; secret controls/tokens are redacted.
  These public observations are projections, not a claim of complete raw DOM.
- `h.network()`: return newly observed sanitized same-origin response records;
  Only JSON response bodies are exported; HTML is metadata-only. JS, maps,
  assets, arbitrary HTTP clients and source inspection are excluded.
- `h.read_point(reason)`: save an observation and raise a controlled pause;
  the authoritative result status is `needs_reading`, and the script stops.
  A later broker call may resume after interpretation. Routine
  multi-page flows can continue without a model round trip at every action.
- `h.classify(disposition, explanation='')`: record `matches_prediction`,
  `contradiction`, or `unconfirmed`; this is a learner claim, not independent truth.
- `h.note(text)`: preserve a reasoning/evidence note.

Every native action is wrapped with prediction, target confirmation, scroll,
fixed waits, before/after screenshots and observations. The standard timeout is
30 seconds, fixed post-action wait is 250 ms; all waits count toward elapsed time.
Evidence is copied to `workspace/evidence/call-.../`; inspect it with your allowed
workspace tools. A policy denial latches the runtime and broker closed; further
execution is refused, including after a broker restart. Budgets are authoritative
in the MCP `status` result. Do not interpret an `unconfirmed` result as success.

Scripts may import json/re/math/statistics/collections and registered helper
modules. They cannot open files, import OS/network modules, use eval/exec,
reflection, arbitrary browser JavaScript, raw requests, client script bodies,
internal runtime objects, or navigate to another origin. The AST policy is an
interface restriction; the independent OS namespace separately enforces mounts,
process visibility, and network isolation. Learn and write your own models only
from the permitted public evidence. Full tree comparison and privileged resets
belong to the coordinator and are not available through browser tools.

Registered helper modules support both `import ui; ui.login(h)` (including an
import alias) and `from ui import login; login(h)`. Attribute form is restricted
to that immutable imported receiver and its public top-level function exports.
Private/nested reflection and unsafe attributes remain excluded. Unsupported
interfaces and syntax errors are pre-execution, zero-dispatch, recoverable errors;
permission denials still latch the broker closed.

Paired evaluation may opt into a separately registered stability policy. It waits
for bounded native load/network conditions, a fresh quiet interval and consecutive
full canonical DOM/AX equality in each lane, then verifies the persisted checkpoint.
It never compares against the other lane to choose another capture, and never
retries a website action. Failure is `unconfirmed`, stops the script suffix, and
does not act as a permission denial. The independent runner watchdog also bounds
a blocked renderer. Default learning does not enable this policy.
