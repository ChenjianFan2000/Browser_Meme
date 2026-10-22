# Native browser runtime

The `phase2.execute_script` MCP tool executes a Python file in your workspace.
Discover its actual tool name in your available tool list. This is the only
website channel. Your command tools have no website network or browser socket.
The coordinator retains original evidence outside your workspace. Rewriting an
exported copy does not rewrite the experiment record.

Your script exports `def run(h):`. `h.page` is the native Playwright synchronous
Page. Native locators, get_by_role/text/label/placeholder/test_id, locator/filter,
first/last/nth, state/count/attribute/text methods and UI operations are available.
There are no predefined website operations. Read-only DOM methods filter scripts
and secret fields. Arbitrary JavaScript evaluation, response objects, direct HTTP,
request interception, raw browser contexts and runtime internals are excluded.

Call `h.expect(prediction, rationale)` before **each** goto, click, fill, press,
check/uncheck/select, hover, focus or explicit scroll. The runtime records and
fsyncs your prediction before executing the action, then confirms/scrolls native
locators, performs the action and exports DOM, accessibility, screenshot and
same-origin public responses. The timeout is 30 seconds, and the normal post-action
settle interval is 250 ms. Use bounded wait_for conditions and readback for actual
readiness. One script is limited to 300 seconds. A timeout stops further execution
because a write effect might be unconfirmed. All waiting counts toward elapsed time.

`h.observe(label)` returns the current public observation. `h.network()` returns
new sanitized UI-caused responses. `h.note(text)` records your rationale,
classification and hypothesis update. `h.origin` is the registered origin;
`h.fixture` is the same public fixture JSON supplied in your workspace. Inspect
its keys there, discover login in the UI, and do not print account values.

Each tool call starts a new browser page, while cookies/local storage and website
business state persist during your learning run. Navigate explicitly at each
call. The coordinator resets business state only between experimental runs.
You may read the exported evidence files and use view_image on screenshots.
The result names the evidence directory and authoritative budget. Preserve
failed scripts and create a new version when correcting them.

Only pure Python imports `json`, `re`, `math`, `statistics`, `collections` are
allowed inside browser scripts. Supply own pure helper modules using the tool's
`modules` array of workspace-relative Python paths. Own helpers undergo the same
policy. `print`, normal control flow, functions, containers and ordinary string,
list/dict and regex methods are supported. Use ordinary command tools for other
offline analysis and artifact writing; these cannot access the website.

An example of **generic** exploration structure (no site knowledge):

```python
def run(h):
    unknown = {"disposition": "unknown", "effects": {
        "persistent_state_changed": None, "affected_record_count": None},
        "ui_claims": [], "unknowns": ["Initial page not yet observed"]}
    h.expect(unknown, "Inspect the initial page")
    h.page.goto(h.origin)
    print(h.observe("initial-page"))
```

After learning, write `READY.json` with `revision_directory` pointing to a complete
new revision, plus `stop_reason` and concise limits. A finished revision is required
even when substantial areas remain unknown. Do not stop at a proposal.
