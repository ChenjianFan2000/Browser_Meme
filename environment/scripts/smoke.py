"""Offline package/browser checks; never contacts a benchmark or an LLM provider."""
from importlib import import_module, metadata
import json
import os
from pathlib import Path
import sys

profile = sys.argv[1]
report = {'profile': profile, 'python': sys.version.split()[0]}
import_module('browsergym.core')
report['browsergym-core'] = metadata.version('browsergym-core')
report['playwright'] = metadata.version('playwright')
if profile == 'core':
    from browsergym.workarena import ATOMIC_TASKS
    report['workarena_atomic_task_types'] = len(ATOMIC_TASKS)
    assert ATOMIC_TASKS
elif profile == 'agentlab':
    import_module('agentlab')
    import torch
    report['agentlab'] = metadata.version('agentlab')
    report['torch'] = torch.__version__
    assert torch.version.cuda is None, 'This environment is intentionally CPU-only.'
elif profile == 'webchore':
    import nltk
    # Fail locally rather than letting upstream import trigger a network download.
    nltk.data.find('tokenizers/punkt_tab')
    workspace = Path('/opt/browser-meme/workspaces/WebChoreArena-542abc538fd9558362119714989166904d82f5f4/BrowserGym')
    os.chdir(workspace)
    sys.path.insert(0, str(workspace))
    from browsergym.webchorearena import ALL_WEBCHOREARENA_TASK_IDS
    report['webchore_registered_tasks'] = len(ALL_WEBCHOREARENA_TASK_IDS)
    assert ALL_WEBCHOREARENA_TASK_IDS
else:
    raise SystemExit(f'Unknown profile: {profile}')

from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<button onclick="document.querySelector(\'output\').textContent=\'ok\'">Run</button><output>pending</output>')
    page.get_by_role('button', name='Run').click()
    assert page.locator('output').inner_text() == 'ok'
    report['chromium'] = browser.version
    report['browser_interaction'] = 'passed'
    browser.close()

report['status'] = 'passed'
result_path = Path(__file__).resolve().parents[2] / f'.runtime/logs/smoke-{profile}.json'
result_path.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
