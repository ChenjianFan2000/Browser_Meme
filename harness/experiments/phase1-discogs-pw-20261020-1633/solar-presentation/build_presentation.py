"""Read-only compilation of Solar's Chinese evidence presentation.

Reads public plans, source-review manifests, actual results and public diagnosis.
Never imports evaluators or starts browsers. Outputs only in this directory.
"""
import collections
import hashlib
import html
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
EXPERIMENT = OUT.parent
ROOT = OUT.parents[3]
MODELS = ROOT / 'harness/sites/discogs/model'
SOURCE = ROOT / 'veri_env/external/VeriEnv-main/websites/discogs'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def link(path, label=None):
    path = Path(path)
    href = os.path.relpath(path, OUT).replace('\\', '/')
    return f'<a href="{html.escape(href)}">{html.escape(label or path.name)}</a>'


def table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>'


review = read(MODELS / 'pw-extension-v002/source_review.json')
counts = dict(collections.Counter(f['status'] for f in review['files']))
assert len(review['files']) == 110 and sum(counts.values()) == 110
assert all(f.get('sha256') for f in review['files'])
manifest_rows = []
for f in review['files']:
    manifest_rows.append([link(SOURCE / f['path'], f['path']), html.escape(f['status']), html.escape(f.get('summary', f.get('reason', ''))), f.get('sha256', '')])

rules = read(MODELS / 'pw-extension-v002/rules.json')
plans = {suite: read(MODELS / rev / 'plan.json') for suite, rev in [('anchor', 'pw-v002'), ('extension', 'pw-extension-v002')]}
mapping = []
for rule in rules:
    entries = []
    for suite, plan in plans.items():
        for case in plan['cases']:
            for step in case['steps']:
                if rule['id'] in step['rule_ids']:
                    entries.append({'suite': suite, 'case': case['id'], 'step': step['id'], 'branches': step['expect'], 'invariants': step.get('invariants', [])})
    mapping.append({'rule_id': rule['id'], 'source_refs': rule['source_refs'], 'script': {'anchor': 'pw-v002/scripts.py', 'extension': 'pw-extension-v002/scripts.py'}, 'entries': entries, 'claim': 'Source rule plus specified observed branch evidence only; never whole-rule verified.'})

runs = []
for folder in sorted(EXPERIMENT.iterdir()):
    if not folder.is_dir() or not folder.name.startswith(('anchor-', 'extension-')):
        continue
    results = []
    for p in sorted((folder / 'cases').glob('*/result.json')):
        d = read(p)
        results.append({'case_id': d['id'], 'passed': d['passed'], 'status': d['status'], 'steps': [{'id': s['id'], 'status': s['status']} for s in d.get('steps', [])], 'path': os.path.relpath(p, ROOT).replace('\\', '/')})
    expected = 8 if folder.name.startswith('anchor-') else 12
    matched = sum(s['status'] == 'matched' for c in results for s in c['steps'])
    summary_path = folder / 'summary.json'
    summary = read(summary_path) if summary_path.exists() else {}
    metrics = summary.get('metrics', {})
    if metrics:
        assert metrics['passed_cases'] == sum(c['passed'] for c in results)
        assert metrics['matched_steps'] == matched
    runs.append({'run_id': folder.name, 'expected_cases': expected, 'completed_results': len(results), 'complete': len(results) == expected, 'task_passed': sum(c['passed'] for c in results), 'matched_steps': matched, 'cases': results, 'summary_metrics': metrics, 'integrity_errors': summary.get('integrity_errors'), 'activation_allowed': summary.get('activation_allowed'), 'summary_sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest() if summary_path.exists() else None, 'note': 'anchor-initial-001 is infrastructure-only with zero UI actions; not model outcome' if folder.name == 'anchor-initial-001' else ''})

checkout_dir = EXPERIMENT / 'anchor-repair-001/cases/07-checkout'
checkout = read(checkout_dir / 'result.json')
initial = read(checkout_dir / 'initial.json')
final = read(checkout_dir / 'final.json')
assert checkout['passed']
checkout_plan = next(c for c in plans['anchor']['cases'] if c['id'] == 'checkout')
step_rows = []
step_data = []
descriptions = {
 'login_open': '打开登录表单；确认Sign in；业务表哈希不变。',
 'login_username': '确认并滚动原生用户名输入框，填公开demo用户名；回读值等于demo。',
 'login_password': '确认并滚动密码输入框，填本地公开fixture密码；证据脱敏；业务不变。',
 'login_submit': '点击Sign in；浏览器POST /api/auth/login=200；到首页且显示Trending Releases。',
 'marketplace_open': '导航release221市场；读到Marketplace listings。SSR后端查询不等同浏览器已观测网络。',
 'cart_add': '定位href=/cart?add=1并滚动点击；POST /api/cart/items=201；一行qty1、7251分；原页面显示USD72.51。',
 'checkout': '确认Checkout后点击；POST /api/checkout=200；付费订单121、item listing1/7251美分/qty1，UI及DB空车。'
}
for index, (spec, actual) in enumerate(zip(checkout_plan['steps'], checkout['steps']), 1):
    assert spec['id'] == actual['id']
    evidence_path = checkout_dir / f'{index:02d}.json'
    step_data.append({'id': spec['id'], 'rule_ids': spec['rule_ids'], 'prediction': spec['expect'], 'invariants': spec['invariants'], 'actual': actual, 'evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest()})
    step_rows.append([str(index), html.escape(spec['id']), html.escape(', '.join(spec['rule_ids'])), descriptions[spec['id']], html.escape(actual['status']), link(evidence_path, '预测/前后观察') + ' · ' + link(checkout_dir / f'{index:02d}.png', '截图')])

excluded = [f for f in review['files'] if f['status'] == 'excluded_content_not_read']
payload = {'scope': 'source-visible phase1 local derived experiment; not browser-only learning or official benchmark', 'source_count': 110, 'source_review_categories': counts, 'excluded': excluded, 'rules_count': len(rules), 'rule_source_script_check_mapping': mapping, 'runs': runs, 'checkout': {'run': 'anchor-repair-001', 'case': 'checkout', 'steps': step_data, 'independent_checks': checkout['independent_checks'], 'initial_cart_count': initial['backend']['cart_count'], 'initial_demo_order_count': initial['backend']['order_count'], 'final_demo_order_count': final['backend']['order_count'], 'final_order': final['backend']['latest_demo_order'], 'final_order_items': final['backend']['latest_demo_order_items'], 'final_listing1': next(x for x in final['backend']['listings'] if x['id'] == 1)}, 'repeat_runs_complete': len([r for r in runs if 'repeat' in r['run_id'] and r['complete']]), 'tokens': None, 'billing': None}
(OUT / 'evidence.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(OUT / 'rule-source-script-check-mapping.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

sections = ['<h1>Discogs第一阶段：源码规则与真实网页证据</h1>', '<p>独立实验模型：gpt-6.1-sol（独立上下文）。本说明由模型作者读取固定公开任务、自己的模型产物、真实运行结果与独立公开部署诊断编写；没有读取私有评估器实现，没有启动浏览器或改网站。主Agent调度运行，独立评估器给出业务终点真值。</p>', '<p>这是源码可见阶段的本地派生开发与回归，不能称为第二阶段浏览器独立学习、冻结首次泛化、完整浏览器基准复现或严格速度对照。网页规则作者的预期匹配与独立业务目标通过分别统计。</p>', '<h2>源码使用范围与实际审阅数量</h2>', '<p>原始站点共110文件；本轮逐文件字节哈希完整。99个文本实现、配置或说明文件已阅读并记录摘要；1个依赖锁文件只检查顶层元数据；6个装饰资源只登记；4个明确排除。不能将110个哈希、文件枚举或99个已读文件等同全站语义完全理解。</p>']
sections += [table(['类别', '精确数量', '证据含义'], [['文本实现/配置/说明已读', '99', '前端页面、组件、API路由与状态；后端路由、权限、schema、ORM、session、seed、迁移、运行配置及SDK'], ['package-lock顶层元数据', '1', '依赖元数据检查；未阅读第三方包实现'], ['装饰资源登记', '6', '5个SVG和1个favicon；不声明业务阅读理解'], ['明确不读内容', '4', 'task_instructions.json、generate_task_instructions.py、smoke_check.sh、linear_sync.py；仅opaque字节哈希']]), '<p>代码阅读覆盖完整页面/组件与前后端调用链、验证模式、数据模型、事务关闭/提交、迁移和运行配置。任务与测试材料排除用于避免导入答案；Linear外部同步不参与站点业务。逐文件摘要和哈希：' + link(MODELS / 'pw-extension-v002/source_review.json') + '；原稿四个排除项补审计：' + link(MODELS / 'pw-v001-audit-supplement.json') + '。</p>', '<h2>实际运行与固定失败分母</h2>']
runrows = []
for r in runs:
    denominator = r['summary_metrics'].get('step_denominator', 44 if r['expected_cases'] == 8 else 66)
    seconds = r['summary_metrics'].get('elapsed_seconds')
    runrows.append([html.escape(r['run_id']), f"{r['task_passed']}/{r['expected_cases']}", f"{r['matched_steps']}/{denominator}", f'{seconds:.3f}' if seconds is not None else '未提供', link(EXPERIMENT / r['run_id'] / 'report.html', '报告') if (EXPERIMENT / r['run_id'] / 'report.html').exists() else '报告待生成', html.escape(r['note'])])
sections += [table(['运行', '业务目标通过/固定分母', '预测匹配/全部步骤', '实际秒', '证据', '限制'], runrows), '<p>四次冻结重放已全部完成，顺序为anchor-repeat-001→extension-repeat-001→anchor-repeat-002→extension-repeat-002。原8每次4/8业务通过、39/44预测匹配；扩展12每次8/12业务通过、53/66预测匹配；四轮integrity_errors均为空，activation_allowed均为false。保留全部8个失败目标，不因重复稳定而宣布完整能力达标。</p>', '<p>初稿与修订运行是开发/适应，不得重算为未见首次泛化。每例恢复同一冻结业务基线与新浏览器上下文；两次顺序重放只表明这些具体成功和失败可重复，不能当新任务样本或全站覆盖。计时包含等待、回读和记录，是单方法运行耗时，没有对照组，不能宣称严格速度优势。Token和费用接口未提供，保持null。</p>', '<p>四轮原始summary：' + ' · '.join(link(EXPERIMENT / name / 'summary.json', name) for name in ('anchor-repeat-001', 'extension-repeat-001', 'anchor-repeat-002', 'extension-repeat-002')) + '。本HTML不依赖在线站点、CDN、JavaScript或远程图片；原始JSON/截图/trace和单任务页面通过本地相对链接访问。</p>', '<h2>源码支持、实测分支和未验证项</h2>', table(['范围', '证据级别与边界'], [['登录、标题搜索、release221详情、listing1加购、单品结账', '真实UI对应分支通过独立检查并重放；不代表全部认证错误/目录对象/并发/库存分支都验证'], ['Cookie接受后reload、Rock导航、空搜索、无匹配搜索、市场空过滤/降序/组合过滤、匿名入车登录返回', '扩展具体公开实例成功且重放；不外推全部参数'], ['重复入车中间状态', '真实两次201，qty1→2、7251→14502美分；独立中间检查通过；完整删除恢复流程失败'], ['collection/wantlist幂等、重复本地计数与reload、登出后门禁', '后端源码支持，但当前UI首个动态POST404阻断；不能标为这些完整流程已验证'], ['卖家创建/停用、购物车删除', '卖家搜索与购物车删除当前UI实际404；listing停用未达到，不写实测404；seller错误分支预测可匹配，仍不是卖家任务成功'], ['API-only拒绝、边界、权限/ownership、nullable PATCH、混币、多项/失效checkout、并发与上限', '源码审查或待验证；缺少UI入口的API不冒充UI验证']]), '<h2>原始网站的真实限制</h2>', '<p>独立部署者核对110个源文件一致与生产路由清单，确认原Next通配重写位于afterFiles，先于动态handler，把动态请求发送到FastAPI未实现的/api前缀。静态登录、入车和结账handler可命中。真实收藏/想要POST、卖家搜索GET、购物车删除DELETE返回404。模型修订只能正确等待与报告反例，不能靠换选择器或绕过UI修复原站点。此诊断限当前Windows/Node24.5生产，未声称Docker/Node22实测。</p>', '<p>公开独立因果诊断：' + link(ROOT / '.runtime/phase1-discogs-pw-20261020-1633/diagnostics/anchor-initial-002-routing/DIAGNOSIS.md') + '。通用代理源码另有丢query潜在问题；当前先被重写遮挡，未实测解除遮挡后的422。其他源码限制包括无注册UI、移除收藏UI、listing编辑UI、订单历史/评论写入/目录编辑，newsletter和部分导航为占位；这些不能凭外观声明已实现。</p>', '<h2>成功结账：完整7步</h2>', '<p>下表逐步说明保留anchor-repair-001/checkout修订回归证据；最终冻结重放可从' + link(EXPERIMENT / 'anchor-repeat-002/task-checkout.html', 'anchor-repeat-002/task-checkout.html') + '查看，业务结论同样通过。七步均保留动作前预测、原生定位确认与滚动、动作、等待、回读、截图和trace。matched仅是步骤监控，最终业务结论由独立检查确定。</p>', table(['序号', '步骤ID', '规则', '真实动作与观察', '监控', '原始证据'], step_rows), '<p>修订回归示例：初态demo订单2个、空购物车；入车后7251美分；结账后demo订单3个，新订单121=paid/USD 72.51（7251美分），order_item249指向listing1、单价7251美分、quantity1。listing1从active变sold而库存quantity仍2；该站源码按整listing售出，不是减库存。最终DB/UI购物车为空。</p>', table(['独立检查ID', '结果', '意义'], [[html.escape(c['id']), '通过' if c['passed'] else '失败', html.escape(c.get('detail', ''))] for c in checkout['independent_checks']]), '<p>修订回归完整展示：' + link(EXPERIMENT / 'anchor-repair-001/task-checkout.html', 'generated task-checkout.html') + '；' + link(checkout_dir / 'result.json', '独立终点结果') + '；' + link(checkout_dir / 'trace.zip', 'Playwright trace') + '；执行脚本' + link(MODELS / 'pw-v002/scripts.py') + '。</p>', '<h2>规则—源码—脚本—检查对应</h2>', '<p>24条规则保留源码引用和来源状态。每个计划step引用规则ID、脚本按同ID调用h.step；branch checks与invariants在动作前冻结。独立评估不读取这些预测。完整可机读映射：' + link(OUT / 'rule-source-script-check-mapping.json') + '；' + link(OUT / 'evidence.json') + '。</p>']
maprows = []
for m in mapping:
    maprows.append([m['rule_id'], '<br>'.join(html.escape(s) for s in m['source_refs']), '<br>'.join(html.escape(f"{e['suite']}:{e['case']}/{e['step']}") for e in m['entries']) or '当前公开套件无执行项；源码支持/待验证', str(sum(len(b['checks']) + len(e['invariants']) for e in m['entries'] for b in e['branches']))])
sections += [table(['规则ID', '源码/独立证据', '脚本中的case/step', '关联检查数'], maprows)]
# Independent review errata are presentation supplements, never edits to frozen models.
proxy_specs = [
 ('auth/login/route.ts', 'POST /api/auth/login → /auth/login', 'AUTH-LOGIN', 'JSON不合法400；后端拒绝状态/文本透传；成功写httpOnly/lax token cookie并返回ok。', '静态路径：实际有效登录200、无效凭据400。'),
 ('auth/logout/route.ts', 'POST /api/auth/logout', 'AUTH-LOGOUT', '无后端调用；返回ok并设置cookie maxAge=0。', '静态路径；本公开signout任务被此前membership阻断，登出分支未实测。'),
 ('auth/register/route.ts', 'POST /api/auth/register → /auth/register', 'AUTH-REGISTER', 'JSON不合法400；后端注册状态/响应透传，不自动登录。', '静态路径；无注册UI，未作UI验证。'),
 ('backend/[...path]/route.ts', 'GET/POST/PUT/PATCH/DELETE /api/backend/* → /*', 'SELL-SEARCH-PROXY / RUNTIME', '转发显式Authorization等请求头，不把cookie转bearer；只拼path而丢query。', '动态catch-all：实际搜索首先被rewrite转到后端/api/backend/search而404。解除遮挡后丢q可能422，尚未实测。'),
 ('cart/route.ts', 'GET /api/cart → /cart', 'CART-READ / AUTH-GATE', 'backendFetch附cookie bearer；状态及JSON文本透传。', '静态路径：已实际200读空/非空cart。'),
 ('cart/items/route.ts', 'POST /api/cart/items → /cart/items', 'CART-ADD / AUTH-GATE', 'JSON不合法400；其余后端状态透传；数量/active检查在后端。', '静态路径：已实际201加购及匿名401登录返回。'),
 ('cart/items/[id]/route.ts', 'DELETE /api/cart/items/id → /cart/items/id', 'CART-REMOVE', 'backendFetch附bearer、原始状态透传；后端只删除当前用户row。', '动态路径：扩展10/09.json已实际DELETE404，qty2与14502美分仍在。'),
 ('checkout/route.ts', 'POST /api/checkout → /checkout', 'CHECKOUT / AUTH-GATE', 'backendFetch附bearer；后端拒绝/OrderOut响应透传。', '静态路径：已实际200单项checkout；其他拒绝/并发分支未实测。'),
 ('me/collection/route.ts', 'GET /api/me/collection → /me/collection', 'MEM-COLLECTION / AUTH-GATE', 'backendFetch附bearer；当前用户ReleaseCard数组或401透传。', '静态路径；任务未到列表回读，不能凭静态路由推断当作UI成功。'),
 ('me/collection/[id]/route.ts', 'POST/DELETE /api/me/collection/id → /me/collection/id', 'MEM-COLLECTION / AUTH-GATE', '后端POST existing幂等、缺release404；DELETE absent仍ok；当前用户隔离。', '动态路径：POST已实测404；DELETE同路由遮挡为源码/独立诊断推断，未额外操作。'),
 ('me/wantlist/route.ts', 'GET /api/me/wantlist → /me/wantlist', 'MEM-WANTLIST / AUTH-GATE', 'backendFetch附bearer；当前用户ReleaseCard数组或401透传。', '静态路径；任务未到列表回读，不声称UI成功。'),
 ('me/wantlist/[id]/route.ts', 'POST/DELETE /api/me/wantlist/id → /me/wantlist/id', 'MEM-WANTLIST / AUTH-GATE', '后端POST existing幂等、缺release404；DELETE absent仍ok；当前用户隔离。', '动态路径：POST已实测404；DELETE被同机制遮挡是推断，未额外操作。'),
 ('me/listings/route.ts', 'GET/POST /api/me/listings → /me/listings', 'SELL-MANAGE / SELL-CREATE / AUTH-GATE', 'GET当前用户所有状态listing；POST JSON校验/创建拒绝状态透传。', '静态路径：卖家页GET已实际200；搜索阻断，未实际创建POST。'),
 ('me/listings/[id]/route.ts', 'PATCH/DELETE /api/me/listings/id → /me/listings/id', 'SELL-UPDATE / SELL-MANAGE', 'PATCH JSON不合法400；backend ownership缺失404；DELETE本意soft inactive。', '动态路径：同机制遮挡是源码/独立诊断推断；未实际PATCH/DELETE，不得写实测404。'),
]
proxy_map = []
proxy_rows = []
for relative, endpoint, ids, semantics, reachability in proxy_specs:
    source_path = SOURCE / 'frontend/src/app/api' / relative
    line_count = len(source_path.read_text(encoding='utf-8').splitlines())
    proxy_map.append({'file': 'frontend/src/app/api/' + relative, 'source_lines': [1, line_count], 'endpoint': endpoint, 'rule_ids': ids.split(' / '), 'semantics': semantics, 'observed_or_inferred_reachability': reachability})
    proxy_rows.append([link(source_path, relative + f':1-{line_count}'), html.escape(endpoint), html.escape(ids), html.escape(semantics), html.escape(reachability)])
supplement = {'frozen_artifacts_changed': False, 'reference_errata': [{'rule_id': 'CART-ADD', 'frozen_reference': 'backend/app/schemas/cart.py:29-31', 'correct_reference': 'backend/app/schemas/cart.py:27-30', 'reason': 'CartAddIn starts at27; EOF30.'}, {'rule_id': 'RUNTIME', 'frozen_reference': 'frontend/package.json:1-30', 'correct_reference': 'frontend/package.json:1-26', 'reason': 'EOF26.'}], 'proxy_route_map': proxy_map, 'logout_unverified_branch': {'source': 'frontend/src/components/LogoutButton.tsx:14-22', 'statement': 'await fetch does not check res.ok: any resolved non2xx still refresh/push home; cookie clearing follows only successful original logout route semantics. Network rejection exits before refresh/push but finally clears busy. None of these failure branches was executed.'}}
(OUT / 'audit-supplement.json').write_text(json.dumps(supplement, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
sections += ['<h2>独立审计补充：引用勘误与API逐路由映射</h2>', '<p>以下只补展示说明，冻结模型/规则/脚本/适配器均未改。两处越EOF引用纠正为：CART-ADD的CartAddIn应引用backend/app/schemas/cart.py:27–30（文件总30行），RUNTIME的frontend/package.json应引用1–26（总26行）。原冻结文本保留，不能把无效31/30行当作额外源码证据。</p>', '<p>原审阅清单部分proxy条目只有通用摘要和空rule_ids；下面补全14个实际Next route文件与认证、转发、拒绝语义及规则的对应。它是后续审计补充，不追溯伪装为初稿已有映射。backendFetch的cookie→bearer语义在frontend/src/lib/backend.ts:13–22；不能套用于直接转发headers的通用catch-all。</p>', table(['源码文件/有效行', 'UI路径→后端', '对应规则', '源码语义/拒绝', '当前实测或推断'], proxy_rows), '<p>注销另有待实测错误分支：LogoutButton.tsx:14–22只await fetch、不检查res.ok；若HTTP拒绝但promise已resolve，仍router.refresh/push首页，不能凭导航首页证明cookie被清除。cookie maxAge=0属于成功执行原logout route的语义。网络promise reject则在refresh/push前退出，finally释放busy。这里均为源码支持，未实施额外错误注入或声称已验证。</p>', '<p>逐路由补充与引用勘误可机读文件：' + link(OUT / 'audit-supplement.json') + '。</p>', '<details><summary>全部110个文件的审阅分类、摘要和哈希</summary>' + table(['文件', '状态', '摘要/排除理由', 'SHA256'], manifest_rows) + '</details>']
page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Solar网页模型证据说明</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1300px;margin:36px auto;padding:0 20px;color:#172033}h1{font-size:28px}h2{margin-top:38px}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}th,td{border:1px solid #d7dce4;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eef2f7}a{color:#1751ad}details{margin:30px 0}</style><body>' + '\n'.join(sections) + '</body></html>'
page = page.replace('paid/USD7251分', 'paid/USD 72.51（7251美分）')
(OUT / 'report.html').write_text(page, encoding='utf-8')
print(json.dumps({'source_categories': counts, 'rules': len(rules), 'runs': len(runs), 'checkout_steps': len(step_data), 'output': str(OUT / 'report.html')}, ensure_ascii=False))
