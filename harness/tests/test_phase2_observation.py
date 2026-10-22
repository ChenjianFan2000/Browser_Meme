from harness.phase2.observation import public_dom, public_response


def test_dom_preserves_ui_but_excludes_inline_scripts_and_event_handlers():
    output = public_dom('<html><script>PRIVATE_CODE</script><button onclick="PRIVATE_HANDLER">Open</button>'
                        '<input type="password" value="CREDENTIAL"><a href="javascript:PRIVATE_CODE">Link</a>'
                        '<iframe srcdoc="PRIVATE_INLINE_HTML"></iframe></html>')
    assert 'PRIVATE_' not in output
    assert 'CREDENTIAL' not in output
    assert '<button>Open</button>' in output
    assert '[REDACTED]' in output


def test_network_excludes_scripts_and_maps_and_redacts_nested_credentials():
    for kind, url, media in [("script", "/asset", "text/plain"),
                             ("fetch", "/asset", "application/javascript"),
                             ("fetch", "/asset.map", "application/json")]:
        row = public_response(url, "GET", 200, media, b"PRIVATE_CODE", kind)
        assert 'body' not in row
        assert row['body_omitted'] == 'client_code_excluded_by_protocol'
    row = public_response('/response', 'POST', 200, 'application/json',
                          b'{"item":{"title":"Visible"},"access_token":"CREDENTIAL"}', 'fetch')
    assert row['body']['item']['title'] == 'Visible'
    assert row['body']['access_token'] == '[REDACTED]'


def test_html_response_does_not_export_hydration_script():
    row = public_response('/page', 'GET', 200, 'text/html',
                          b'<main>Visible</main><script type="application/json">PRIVATE_STATE</script>', 'document')
    assert row['body'] == '<main>Visible</main>'
