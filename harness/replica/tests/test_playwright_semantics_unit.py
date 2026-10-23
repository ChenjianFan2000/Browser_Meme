"""Ordinary unit controls for the separately registered Playwright semantics.

No browser, target website, model, private oracle or historical case is opened.
These synthetic strings test preservation/normalization, not browser AX capture.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


MODULE_PATH = (Path(__file__).resolve().parents[1] / 'runtime_versions' /
               'evaluation-playwright-semantics-v6' / 'playwright_semantics.py')
SOURCE = 'http://source.test:4310'
REPLICA = 'http://replica.test:4410'
ROOTS = {SOURCE: '@site', REPLICA: '@site'}
SCHEMA = 'playwright-script-semantics/v1'


def load_module():
    spec = importlib.util.spec_from_file_location('replica_playwright_semantics_unit_target', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError('v6 collector module has not been prepared')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def snapshot_url_value(text):
    values = []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*- /url: (.+)', line)
        if match:
            value = match.group(1)
            values.append(json.loads(value) if value.startswith('"') else value)
    return values


class PlaywrightSemanticsUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_path = list(sys.path)
        sys.path.insert(0, str(MODULE_PATH.parent))
        cls.collector = load_module()

    @classmethod
    def tearDownClass(cls):
        sys.path[:] = cls.previous_path

    def record(self, snapshot='- button "Save"', *, origin=SOURCE):
        return {'schema':SCHEMA, 'policy':deepcopy(self.collector.POLICY),
                'status':'confirmed', 'frames':[{
                    'key':'f0', 'parent':None, 'owner':None, 'url':origin + '/feed',
                    'name':'', 'root':'body', 'snapshot':snapshot}], 'unsupported':[]}

    def canonical(self, record):
        return self.collector.canonical_semantics(record, ROOTS)

    def assert_not_confirmed(self, record):
        try:
            result = self.canonical(record)
        except ValueError:
            return
        self.assertNotEqual(result.get('status'), 'confirmed')

    def test_only_explicit_url_field_changes_not_business_origin_or_nested_query(self):
        link = SOURCE + '/next?literal=' + SOURCE + '/business#tail'
        name = '- link "Business text ' + SOURCE + '/keep"'
        text = '  - text: ' + SOURCE + '/also-keep'
        snapshot = name + '\n  - /url: ' + link + '\n' + text
        actual = self.collector.normalize_snapshot_urls(snapshot, ROOTS)
        self.assertIn(name, actual)
        self.assertIn(text, actual)
        self.assertEqual(snapshot_url_value(actual), ['@site/next?literal=' + SOURCE + '/business#tail'])

    def test_url_mapping_requires_origin_boundary(self):
        cases = [
            (SOURCE, '@site'),
            (SOURCE + '/next', '@site/next'),
            (SOURCE + '?q=1', '@site?q=1'),
            (SOURCE + '#fragment', '@site#fragment'),
            (SOURCE + '.evil/path', SOURCE + '.evil/path'),
            (SOURCE + '0/path', SOURCE + '0/path'),
            ('https://source.test:4310/path', 'https://source.test:4310/path'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                actual = self.collector.normalize_snapshot_urls('- link "Link"\n  - /url: ' + raw, ROOTS)
                self.assertEqual(snapshot_url_value(actual), [expected])

    def test_quoted_url_is_decoded_and_only_its_origin_is_mapped(self):
        raw = SOURCE + '/path?label="quoted"&next=' + SOURCE + '/literal'
        snapshot = '- link "Complex"\n  - /url: ' + json.dumps(raw)
        actual = self.collector.normalize_snapshot_urls(snapshot, ROOTS)
        self.assertEqual(snapshot_url_value(actual), ['@site/path?label="quoted"&next=' + SOURCE + '/literal'])

    def test_unknown_or_malformed_url_escapes_fail_closed(self):
        malformed = [
            '"http://source.test:4310/\\q"',
            '"http://source.test:4310/\\x41"',
            '"http://source.test:4310/unterminated',
            '"http://source.test:4310/path" trailing',
        ]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.collector.normalize_snapshot_urls('- link "Bad"\n  - /url: ' + value, ROOTS)

    def test_same_semantics_normalizes_both_explicit_frame_and_link_urls(self):
        left = self.record('- link "Continue"\n  - /url: ' + SOURCE + '/next')
        right = self.record('- link "Continue"\n  - /url: ' + REPLICA + '/next', origin=REPLICA)
        self.assertEqual(self.canonical(left), self.canonical(right))

    def test_explicit_executable_urls_project_body_case_and_leading_space_only(self):
        expected = self.canonical(self.record(
            '- link "Continue"\n  - /url: javascript:unitFirst()'))
        self.assertEqual(snapshot_url_value(expected['frames'][0]['snapshot']),
                         ['javascript:[REDACTED_EXECUTABLE_URL]'])
        values = [
            'javascript:unitSecond()',
            'JAVASCRIPT:unitThird()',
            ' \tJaVaScRiPt:unitFourth("quoted")',
        ]
        for raw_url in values:
            with self.subTest(raw_url=raw_url):
                record = self.record('- link "Continue"\n  - /url: ' + json.dumps(raw_url))
                original = deepcopy(record)
                self.assertEqual(expected, self.canonical(record))
                self.assertEqual(record, original)  # Projection cannot rewrite raw evidence.

    def test_javascript_in_business_names_and_text_remains_exact(self):
        pairs = {
            'name': ('- link "javascript:unitFirst()"',
                     '- link "javascript:unitSecond()"'),
            'text': ('- text: javascript:unitFirst()',
                     '- text: javascript:unitSecond()'),
        }
        for field, (left, right) in pairs.items():
            with self.subTest(field=field):
                left_snapshot = left + '\n  - /url: javascript:unitFirst()'
                right_snapshot = right + '\n  - /url: javascript:unitSecond()'
                left_normal = self.canonical(self.record(left_snapshot))
                right_normal = self.canonical(self.record(right_snapshot))
                self.assertNotEqual(left_normal, right_normal)
                self.assertIn(left, left_normal['frames'][0]['snapshot'])
                self.assertIn(right, right_normal['frames'][0]['snapshot'])

    def test_non_executable_url_differences_are_preserved_exactly(self):
        pairs = {
            'path': (SOURCE + '/first', SOURCE + '/second'),
            'query': (SOURCE + '/next?q=1', SOURCE + '/next?q=2'),
            'fragment': (SOURCE + '/next#first', SOURCE + '/next#second'),
            'javascript_query_text': (SOURCE + '/next?q=javascript:unitFirst()',
                                      SOURCE + '/next?q=javascript:unitSecond()'),
            'different_scheme': ('javascriptx:unitFirst()', 'javascriptx:unitSecond()'),
        }
        for field, (left_url, right_url) in pairs.items():
            with self.subTest(field=field):
                left = self.record('- link "Continue"\n  - /url: ' + json.dumps(left_url))
                right = self.record('- link "Continue"\n  - /url: ' + json.dumps(right_url))
                self.assertNotEqual(self.canonical(left), self.canonical(right))
                expected_left = '@site' + left_url[len(SOURCE):] if left_url.startswith(SOURCE) else left_url
                self.assertEqual(snapshot_url_value(self.canonical(left)['frames'][0]['snapshot']),
                                 [expected_left])

    def test_each_frame_topology_field_remains_significant(self):
        baseline = self.record()
        baseline['frames'].append({'key':'f1', 'parent':'f0',
            'owner':'f0/document/children/1/children/1/children/2',
            'url':SOURCE + '/child', 'name':'details', 'root':'body', 'snapshot':'- button "Child"'})
        changes = {
            'key':'f2', 'parent':None,
            'owner':'f0/document/children/1/children/1/children/3',
            'url':SOURCE + '/other-child', 'name':'other-details', 'root':'frameset',
        }
        expected = self.canonical(baseline)
        for field, value in changes.items():
            with self.subTest(field=field):
                actual = deepcopy(baseline)
                actual['frames'][1][field] = value
                try:
                    normalized = self.canonical(actual)
                except ValueError:
                    continue  # Invalid topology may be rejected instead of compared.
                self.assertNotEqual(expected, normalized)

    def test_meaningful_snapshot_differences_cannot_be_normalized_away(self):
        pairs = {
            'role':('- button "Save"', '- link "Save"'),
            'name':('- button "Save"', '- button "Apply"'),
            'disabled':('- button "Save"', '- button "Save" [disabled]'),
            'checked':('- checkbox "Enabled"', '- checkbox "Enabled" [checked]'),
            'expanded':('- button "Details"', '- button "Details" [expanded]'),
            'order':('- button "First"\n- button "Second"', '- button "Second"\n- button "First"'),
            'visibility':('- button "Visible"\n- button "Second"', '- button "Second"'),
            'input_value':('- textbox "Query": alpha', '- textbox "Query": beta'),
        }
        for change, (left, right) in pairs.items():
            with self.subTest(change=change):
                self.assertNotEqual(self.canonical(self.record(left)), self.canonical(self.record(right)))

    def test_missing_schema_unknown_status_and_unsupported_are_never_confirmed(self):
        missing = self.record()
        missing.pop('schema')
        wrong = self.record()
        wrong['schema'] = 'some-other-format/v1'
        status = self.record()
        status['status'] = 'not_requested'
        unsupported = self.record()
        unsupported['unsupported'] = [{'kind':'name_truncated', 'frame':'f0'}]
        for name, record in [('missing', missing), ('wrong', wrong), ('status', status), ('unsupported', unsupported)]:
            with self.subTest(name=name):
                self.assert_not_confirmed(record)

    def test_truncated_data_url_is_never_confirmed(self):
        self.assert_not_confirmed(self.record('- link "Data"\n  - /url: data:text/html,possibly-truncated'))

    def test_sanitize_record_does_not_mutate_input_and_removes_secret(self):
        secret = 'GENERIC_UNIT_PASSWORD_CANARY_6917'
        record = self.record('- textbox "Password": ' + secret)
        before = deepcopy(record)
        sanitized = self.collector.sanitize_record(record, [secret])
        self.assertEqual(record, before)
        self.assertNotIn(secret, json.dumps(sanitized))
        self.assertIn('Password', sanitized['frames'][0]['snapshot'])

    def test_policy_explicitly_declares_default_mode_version_and_long_name_guard(self):
        policy_text = json.dumps(self.collector.POLICY, sort_keys=True).lower()
        self.assertIn('1.62.0', policy_text)
        self.assertIn('default', policy_text)
        self.assertIn('900', policy_text)
        self.assertRegex(policy_text, r'long.?name|name.?length|name.?trunc|901|oversiz')


if __name__ == '__main__':
    unittest.main()
