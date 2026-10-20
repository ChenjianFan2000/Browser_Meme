"""Meaningful integration checks; no learned model or private split is needed."""
from copy import deepcopy
import sys
from pathlib import Path
from threading import Thread
import unittest

from issue_lab.benchmark import apply_delta, delta, score_states
from issue_lab.domain import IssueDomain
from issue_lab.server import IssueServer
from issue_lab.replay import failed_result

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/verienv/websites/issue_lab/sdk/python'))
from issue_lab_sdk import IssueLabClient


class IntegrationTests(unittest.TestCase):
    def test_failed_run_retains_full_denominator(self):
        result = failed_result(['one_step','rollout','drift'], 'synthetic timeout')
        self.assertEqual(len(result['rows']), 48)
        self.assertEqual(result['summary']['one_step']['n'], 24)
        self.assertEqual(result['summary']['rollout']['steps'], 45)
        self.assertTrue(all(not row['valid'] for row in result['rows']))

    def test_native_judge_retains_semantic_distinctions(self):
        original = IssueDomain(11).observe()
        self.assertTrue(score_states(original, original)['exact'])
        for change in ['case', 'space', 'type', 'comment_order', 'visible_order']:
            state = deepcopy(original)
            if change == 'case': state['issues'][0]['title'] = state['issues'][0]['title'].upper()
            elif change == 'space': state['issues'][0]['title'] += ' '
            elif change == 'type': state['issues'][0]['blocked'] = int(state['issues'][0]['blocked'])
            elif change == 'comment_order':
                original['issues'][0]['comments'] = ['first', 'second']
                state = deepcopy(original)
                state['issues'][0]['comments'].reverse()
            else: state['visible_ids'].reverse()
            self.assertFalse(score_states(state, original)['exact'], change)

    def test_sparse_delta_is_lossless(self):
        env = IssueDomain(17)
        before = env.step({'type': 'select_all'})
        after = env.step({'type': 'comment', 'text': ' preserve spaces '})
        self.assertTrue(score_states(apply_delta(before, delta(before, after)), after)['exact'])

    def test_real_http_sdk_reset_and_action(self):
        server = IssueServer(('127.0.0.1', 0), IssueDomain(0))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = IssueLabClient(f'http://127.0.0.1:{server.server_port}')
            self.assertTrue(client.health()['ok'])
            before = client.reset(seed=29, version=2)
            self.assertNotIn('version', before)
            target = next(row['id'] for row in before['issues'] if not row['blocked'])
            client.step({'type': 'select', 'ids': [target]})
            failed = client.step({'type': 'close'})
            self.assertEqual(failed['feedback']['code'], 'reason_required')
            after = client.step({'type': 'close', 'reason': 'done'})
            self.assertTrue(after['feedback']['ok'])
            self.assertEqual(next(row for row in after['issues'] if row['id'] == target)['status'], 'closed')
            self.assertTrue(score_states(client.reset(seed=29, version=2), before)['exact'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
