"""Browser-free controls for the v6 joint signature and checkpoint final gate.

The raw DOM/CDP/AX records below are synthetic protocol-shaped fixtures. They
exercise the actual v6 canonicalizer and Runtime.finish_stability, not capture.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


RUNTIME_PATH = (Path(__file__).resolve().parents[1] / 'runtime_versions' /
                'evaluation-playwright-semantics-v6')
ORIGIN = 'http://generic-fixture.test:4310'


def load_runtime_module(name):
    spec = importlib.util.spec_from_file_location(name, RUNTIME_PATH / (name + '.py'))
    if spec is None or spec.loader is None:
        raise RuntimeError('v6 runtime module has not been prepared: ' + name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class PlaywrightSemanticsStabilityUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pin the actual v6 dependencies even if another test imported an older
        # runtime's bare module names. Restore the import state after this class.
        cls.module_patch = patch.dict(sys.modules, {})
        cls.module_patch.start()
        cls.addClassCleanup(cls.module_patch.stop)
        for name in ('observation', 'script_policy', 'unix_bridge', 'trees', 'settle'):
            load_runtime_module(name)
        cls.collector = load_runtime_module('playwright_semantics')
        cls.runtime_module = load_runtime_module('browser_runtime')

    def snapshot(self):
        text = {'nodeType': 3, 'nodeName': '#text', 'text': 'Save', 'children': []}
        button = {'nodeType': 1, 'nodeName': 'BUTTON',
                  'namespaceURI': 'http://www.w3.org/1999/xhtml',
                  'attributes': {'type': 'button'},
                  'live': {'focused': True, 'disabled': False}, 'urls': {},
                  'children': [text]}
        body = {'nodeType': 1, 'nodeName': 'BODY',
                'namespaceURI': 'http://www.w3.org/1999/xhtml',
                'attributes': {}, 'live': {'focused': False}, 'urls': {},
                'children': [button]}
        document = {'nodeType': 9, 'nodeName': '#document', 'children': [body]}
        cdp_document = {'nodeId': 10, 'backendNodeId': 100, 'nodeType': 9,
                        'nodeName': '#document', 'children': [
                            {'nodeId': 11, 'backendNodeId': 101, 'nodeType': 1,
                             'nodeName': 'BODY', 'children': [
                                 {'nodeId': 12, 'backendNodeId': 102, 'nodeType': 1,
                                  'nodeName': 'BUTTON', 'children': [
                                      {'nodeId': 13, 'backendNodeId': 103,
                                       'nodeType': 3, 'nodeName': '#text',
                                       'nodeValue': 'Save'}]}]}]}
        ax = [
            {'nodeId': 'ax-document', 'ignored': False,
             'role': {'type': 'internalRole', 'value': 'RootWebArea'},
             'name': {'type': 'computedString', 'value': 'Generic fixture'},
             'backendDOMNodeId': 100, 'frameId': 'cdp-main',
             'childIds': ['ax-button'], 'properties': []},
            {'nodeId': 'ax-button', 'parentId': 'ax-document', 'ignored': False,
             'role': {'type': 'role', 'value': 'button'},
             'name': {'type': 'computedString', 'value': 'Save'},
             'backendDOMNodeId': 102,
             'properties': [{'name': 'focusable', 'value': {'type': 'boolean', 'value': True}},
                            {'name': 'focused', 'value': {'type': 'boolean', 'value': True}}]},
        ]
        raw = {'schema': 'replica-trees/v1',
               'environment': {'browser_version': 'synthetic-unit-fixture',
                               'viewport': {'width': 1024, 'height': 768}},
               'frames': [{'key': 'f0', 'parent': None, 'owner': None,
                           'url': ORIGIN + '/edit', 'name': '',
                           'cdp_frame_id': 'cdp-main', 'dom': document,
                           'activeElementPath': 'document/children/0/children/0',
                           'cdp_dom': cdp_document, 'ax': ax}], 'unsupported': []}
        semantics = {'schema': self.collector.SCHEMA,
                     'policy': deepcopy(self.collector.POLICY), 'status': 'confirmed',
                     'frames': [{'key': 'f0', 'parent': None, 'owner': None,
                                 'url': ORIGIN + '/edit', 'name': '', 'root': 'body',
                                 'snapshot': '- button "Save"'}], 'unsupported': []}
        return {'schema': 'replica-trees/v1', 'raw': raw, 'semantics': semantics}

    def runtime_with_pending_sample(self, snapshot):
        runtime = self.runtime_module.Runtime.__new__(self.runtime_module.Runtime)
        sample_hash = digest(self.collector.signature_payload(snapshot))
        runtime.pending_stability = {
            'version': 'single-lane-dom-ax-playwright/v2', 'enabled': True,
            'status': 'stable', 'started_monotonic': 100.0,
            'deadline_monotonic': 110.0,
            'samples': [{'canonical_sha256': sample_hash},
                        {'canonical_sha256': sample_hash}],
        }
        runtime.pending_requests = {}
        runtime.capture_unconfirmed = None
        runtime.persist_stability = Mock()
        runtime.log = Mock()
        return runtime

    def test_joint_signature_changes_when_only_semantics_changes(self):
        baseline = self.snapshot()
        changed = deepcopy(baseline)
        changed['semantics']['frames'][0]['snapshot'] = '- button "Apply"'
        left = self.collector.signature_payload(baseline)
        right = self.collector.signature_payload(changed)
        self.assertEqual(baseline['raw'], changed['raw'])
        self.assertEqual(left['dom_ax'], right['dom_ax'])
        self.assertEqual(left['unsupported'], [])
        self.assertEqual(digest(left), digest(self.collector.signature_payload(deepcopy(baseline))))
        self.assertNotEqual(digest(left), digest(right))

    def test_joint_signature_still_retains_full_dom_and_native_ax(self):
        baseline = self.snapshot()
        expected = digest(self.collector.signature_payload(baseline))
        changes = []
        dom_change = deepcopy(baseline)
        dom_change['raw']['frames'][0]['dom']['children'][0]['children'][0]['live']['disabled'] = True
        changes.append(('dom_live_property', dom_change))
        ax_change = deepcopy(baseline)
        ax_change['raw']['frames'][0]['ax'][1]['ignored'] = True
        changes.append(('native_ax_ignored', ax_change))
        for label, changed in changes:
            with self.subTest(change=label):
                self.assertEqual(baseline['semantics'], changed['semantics'])
                self.assertNotEqual(expected, digest(self.collector.signature_payload(changed)))

    def test_final_checkpoint_unchanged_joint_snapshot_is_stable(self):
        snapshot = self.snapshot()
        runtime = self.runtime_with_pending_sample(snapshot)
        record = runtime.pending_stability
        with patch.object(self.runtime_module.time, 'monotonic', return_value=101.0):
            runtime.finish_stability(deepcopy(snapshot))
        self.assertEqual(record['status'], 'stable')
        self.assertEqual(record['checkpoint_verification_sha256'], record['samples'][-1]['canonical_sha256'])
        self.assertIsNone(runtime.capture_unconfirmed)
        self.assertIsNone(runtime.pending_stability)
        runtime.persist_stability.assert_called_once_with(record)
        runtime.log.assert_called_once_with({'kind': 'capture_stability', **record})

    def test_final_checkpoint_semantics_only_change_is_unconfirmed(self):
        snapshot = self.snapshot()
        runtime = self.runtime_with_pending_sample(snapshot)
        record = runtime.pending_stability
        changed = deepcopy(snapshot)
        changed['semantics']['frames'][0]['snapshot'] = '- button "Save" [disabled]'
        self.assertEqual(snapshot['raw'], changed['raw'])
        with patch.object(self.runtime_module.time, 'monotonic', return_value=101.0):
            runtime.finish_stability(changed)
        self.assertEqual(record['status'], 'unconfirmed')
        self.assertEqual(record['reason'], 'changed_after_stability_before_checkpoint')
        self.assertNotEqual(record['checkpoint_verification_sha256'], record['samples'][-1]['canonical_sha256'])
        self.assertIs(runtime.capture_unconfirmed, record)
        self.assertIsNone(runtime.pending_stability)
        runtime.persist_stability.assert_called_once_with(record)
        runtime.log.assert_called_once_with({'kind': 'capture_stability', **record})


if __name__ == '__main__':
    unittest.main()
