"""Strict corruption checks plus opt-in real Chromium capture acceptance."""

from copy import deepcopy
import json
import os

import pytest

from harness.replica.trees import canonicalize, capture, compare


def sample(origin="http://original.test", offset=0):
    def element(name, backend, children=None, attributes=None, live=None):
        return {"nodeType": 1, "nodeName": name, "namespaceURI": "http://www.w3.org/1999/xhtml",
                "attributes": attributes or {}, "live": live or {"focused": False}, "children": children or [],
                "backendNodeId": backend + offset}

    link = element("A", 12, [{"nodeType": 3, "nodeName": "#text", "text": "Link", "children": []}], {"href": origin + "/item", "id": "business-id"})
    link["urls"] = {"href": origin + "/item"}
    field = element("INPUT", 13, attributes={"value": "initial"}, live={"value": "edited", "focused": True, "checked": False, "disabled": False})
    dom = {"nodeType": 9, "nodeName": "#document", "children": [link, field]}
    # These protocol records describe the same DOM, with unrelated allocated IDs.
    cdp_dom = {"nodeType": 9, "nodeName": "#document", "backendNodeId": 11 + offset, "children": [
        {"nodeType": 1, "nodeName": "A", "backendNodeId": 12 + offset, "children": []},
        {"nodeType": 1, "nodeName": "INPUT", "backendNodeId": 13 + offset, "children": []}]}
    for child in dom["children"]:
        child.pop("backendNodeId", None)
    root_id, child_id = str(1 + offset), str(2 + offset)
    ax = [{"nodeId": root_id, "ignored": False, "role": {"type": "internalRole", "value": "RootWebArea"},
           "childIds": [child_id], "backendDOMNodeId": 11 + offset, "frameId": "frame" + str(offset)},
          {"nodeId": child_id, "parentId": root_id, "ignored": False,
           "role": {"type": "role", "value": "link"}, "name": {"type": "computedString", "value": "Link", "sources": [{"relatedNodes": [{"backendDOMNodeId": 12 + offset, "idref": "business-id"}]}]},
           "backendDOMNodeId": 12 + offset, "childIds": [],
           "properties": [{"name": "url", "value": {"type": "string", "value": origin + "/item"}}]}]
    return {"raw": {"environment": {"browser_version": "same", "viewport": {"width": 900, "height": 700}, "locale": "en-US"},
                    "frames": [{"key": "f0", "parent": None, "owner": None, "name": "", "url": origin + "/",
                                "dom": dom, "cdp_dom": cdp_dom, "cdp_frame_id": "frame" + str(offset), "ax": ax}],
                    "unsupported": []}}


def test_protocol_id_allocation_is_not_business_data():
    assert compare(sample(), sample(offset=100))["exact"]


@pytest.mark.parametrize("change", ["tag", "text", "order", "attribute", "value", "checked", "disabled", "focus", "ax_role", "ax_parent", "ax_backend", "ax_related", "ax_child_order"])
def test_meaningful_corruption_never_passes(change):
    expected = sample()
    actual = deepcopy(expected)
    frame = actual["raw"]["frames"][0]
    first, second = frame["dom"]["children"]
    if change == "tag":
        first["nodeName"] = "BUTTON"
    elif change == "text":
        first["children"][0]["text"] = "link"
    elif change == "order":
        frame["dom"]["children"].reverse()
    elif change == "attribute":
        first["attributes"]["id"] = "changed-business-id"
    elif change in ("value", "checked", "disabled", "focus"):
        prop = "focused" if change == "focus" else change
        second["live"][prop] = "different" if prop == "value" else not second["live"][prop]
    elif change == "ax_role":
        frame["ax"][1]["role"]["value"] = "button"
    elif change == "ax_parent":
        frame["ax"][1]["parentId"] = "2"
    elif change == "ax_backend":
        frame["ax"][1]["backendDOMNodeId"] = 13
    elif change == "ax_related":
        frame["ax"][1]["name"]["sources"][0]["relatedNodes"][0]["backendDOMNodeId"] = 13
    elif change == "ax_child_order":
        frame["ax"][0]["childIds"] = ["2", "1"]
    result = compare(expected, actual)
    assert not result["exact"]
    assert result["full_tree_exact_score"] == 0
    assert result["first_difference"]
    assert result["difference_subtrees"]["expected"]["tree"]


def test_full_tree_exact_and_semantic_overlap_are_separate():
    a, b = sample(), sample()
    b["raw"]["frames"][0]["dom"]["children"].reverse()
    result = compare(a, b)
    assert result["full_tree_exact_score"] == 0
    assert result["supplemental_semantic_score"] == 1.0


def test_explicit_url_mapping_retains_path_query_and_text():
    roots = {"http://original.test": "@site", "http://replica.test": "@site"}
    a, b = sample(), sample("http://replica.test", 100)
    assert not compare(a, b)["exact"]
    assert compare(a, b, url_roots=roots)["exact"]
    b["raw"]["frames"][0]["dom"]["children"][0]["attributes"]["href"] += "?wrong=1"
    assert not compare(a, b, url_roots=roots)["exact"]
    b = sample("http://replica.test", 100)
    b["raw"]["frames"][0]["dom"]["children"][0]["children"][0]["text"] = "http://replica.test"
    a["raw"]["frames"][0]["dom"]["children"][0]["children"][0]["text"] = "http://original.test"
    assert not compare(a, b, url_roots=roots)["exact"]


def test_url_mapping_does_not_swallow_a_different_hostname():
    a, b = sample(), sample("http://original.test.evil")
    assert not compare(a, b, url_roots={"http://original.test": "@site"})["exact"]


def test_closed_shadow_or_failed_frame_cannot_be_exact_pass():
    a = sample()
    a["raw"]["frames"][0]["cdp_dom"]["children"][0]["shadowRoots"] = [
        {"nodeName": "#document-fragment", "nodeType": 11, "backendNodeId": 50, "shadowRootType": "closed"}]
    result = compare(a, deepcopy(a))
    assert result["trees_equal"]
    assert not result["supported"]
    assert not result["exact"]


def test_attribute_key_order_is_immaterial_and_capture_is_not_mutated():
    a, b = sample(), sample()
    b["raw"]["frames"][0]["dom"]["children"][0]["attributes"] = {"id": "business-id", "href": "http://original.test/item"}
    original = deepcopy(a)
    assert compare(a, b)["exact"]
    assert a == original


def test_environment_mismatch_fails():
    a, b = sample(), sample()
    b["raw"]["environment"]["locale"] = "zh-CN"
    assert not compare(a, b)["exact"]


def test_ax_storage_order_is_not_child_order():
    a, b = sample(), sample(offset=100)
    b["raw"]["frames"][0]["ax"].reverse()
    assert compare(a, b)["exact"]


def test_frame_owner_relationship_is_material():
    a, b = sample(), sample()
    for snapshot in (a, b):
        child = deepcopy(snapshot["raw"]["frames"][0])
        child.update({"key": "f1", "parent": "f0", "owner": "f0/document/children/2", "cdp_frame_id": "child-frame"})
        snapshot["raw"]["frames"].append(child)
    b["raw"]["frames"][1]["owner"] = "f0/document/children/3"
    assert not compare(a, b)["exact"]


def test_renderer_backend_id_collision_keeps_frame_relationships():
    snapshot = sample()
    child = deepcopy(snapshot["raw"]["frames"][0])
    child.update({"key": "f1", "parent": "f0", "owner": "f0/document/children/2", "cdp_frame_id": "child-frame"})
    child["ax"][0]["frameId"] = "child-frame"
    snapshot["raw"]["frames"].append(child)
    tree = canonicalize(snapshot["raw"])
    assert tree["frames"][0]["ax"][0]["backendDOMNodeId"] == "f0/document"
    assert tree["frames"][1]["ax"][0]["backendDOMNodeId"] == "f1/document"


def test_whitespace_comments_and_script_text_are_not_ignored():
    for node_type, name, text in ((3, "#text", " "), (8, "#comment", " marker "), (1, "SCRIPT", "globalThis.state=1")):
        a, b = sample(), sample()
        a["raw"]["frames"][0]["dom"]["children"].append({"nodeType": node_type, "nodeName": name, "text": text, "children": []})
        assert not compare(a, b)["exact"]


def test_raw_canonical_difference_evidence_is_written(tmp_path):
    a, b = sample(), sample()
    b["raw"]["frames"][0]["dom"]["children"][0]["nodeName"] = "BUTTON"
    result = compare(a, b, output_dir=tmp_path)
    assert json.loads((tmp_path / "comparison.json").read_text()) == result
    for name in ("expected.raw.json", "actual.raw.json", "expected.canonical.json", "actual.canonical.json"):
        assert (tmp_path / name).exists()


@pytest.mark.skipif(os.environ.get("BROWSER_REPLICA_SMOKE") != "1", reason="opt-in real Chromium; BROWSER_REPLICA_SMOKE=1")
def test_real_chromium_frames_shadow_live_and_ax(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"), headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 900, "height": 700}, locale="en-US", timezone_id="UTC")
            page.set_content('<!doctype html><html><body>\n<input value="initial"><iframe srcdoc="<button>child</button>"></iframe><div id="host"></div></body></html>')
            page.eval_on_selector("#host", 'e=>e.attachShadow({mode:"open"}).innerHTML="<button>shadow</button>"')
            page.locator("input").fill("edited")
            first = capture(page, output_dir=tmp_path / "first")
            second = capture(page, output_dir=tmp_path / "second")
            assert compare(first, second)["exact"]
            assert len(first["raw"]["frames"]) == 2
            assert all(frame["ax"] for frame in first["raw"]["frames"])
            encoded = json.dumps(first["canonical"])
            assert '"value": "edited"' in encoded
            assert '"shadowRoot"' in encoded
            assert '"owner": "f0/document/' in encoded
            assert '"backendDOMNodeId": "f0/document/' in encoded
            page.locator("input").fill("corrupted")
            assert not compare(first, capture(page))["exact"]
            page.eval_on_selector("#host", 'e=>{const d=document.createElement("div");document.body.append(d);d.attachShadow({mode:"closed"}).innerHTML="<button>hidden</button>"}')
            closed = capture(page)
            assert not compare(closed, closed)["supported"]
        finally:
            browser.close()


@pytest.mark.skipif(os.environ.get("BROWSER_REPLICA_SMOKE") != "1", reason="opt-in real Chromium; BROWSER_REPLICA_SMOKE=1")
def test_real_cross_origin_process_frame_capture(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"), headless=True, args=["--no-sandbox", "--site-per-process"])
        try:
            context = browser.new_context(viewport={"width": 900, "height": 700}, locale="en-US", timezone_id="UTC")
            def fulfill(route):
                body = '<html><body>parent<iframe src="http://other.test/frame"></iframe></body></html>' if route.request.url.startswith("http://fixture.test/") else '<html><body><button>cross origin</button></body></html>'
                route.fulfill(content_type="text/html", body=body)
            context.route("**/*", fulfill)
            page = context.new_page()
            page.goto("http://fixture.test/")
            first = capture(page, output_dir=tmp_path / "cross-origin")
            second = capture(page)
            assert compare(first, second)["exact"]
            child = first["raw"]["frames"][1]
            assert child["url"] == "http://other.test/frame"
            assert child["cdp_dom"]["documentURL"] == child["url"]
            assert any(node.get("role", {}).get("value") == "button" for node in child["ax"])
            for frame in first["canonical"]["frames"]:
                root = next(node for node in frame["ax"] if node.get("role", {}).get("value") == "RootWebArea")
                assert root["backendDOMNodeId"] == frame["key"] + "/document"
        finally:
            browser.close()
