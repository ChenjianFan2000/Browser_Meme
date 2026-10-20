"""Public-channel-only presentation. Never opens private supervision or NN.json."""
import hashlib
import html
import itertools
import json
import os
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

OUT = Path(__file__).resolve().parent
EXP = OUT.parent
RUN = EXP/'execution-001'
CASE = RUN/'cases/01-budgeted_two_seller_purchase'
ROOT = OUT.parents[3]
MODEL = ROOT/'harness/sites/discogs/model/pw-complex-v001'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def esc(v):
    return html.escape(str(v))


def link(p, label):
    return '<a href="'+esc(os.path.relpath(p, OUT).replace('\\','/'))+'">'+esc(label)+'</a>'


def image(p, label):
    return '<figure><a href="'+esc(os.path.relpath(p, OUT).replace('\\','/'))+'"><img src="'+esc(os.path.relpath(p, OUT).replace('\\','/'))+'" alt="'+esc(label)+'"></a><figcaption>'+esc(label)+'</figcaption></figure>'


def table(headers, rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


summary = read(EXP/'public-execution-summary.json')
plan = read(RUN/'inputs/model/plan.json')
rules = read(RUN/'inputs/model/rules.json')
notes = {p.stem: read(p) for p in sorted((CASE/'notes').glob('*.json'))}
selection = notes['selection_commitment']
offers = selection['candidate_rows']
eligible = [o for o in offers if o['seller'] != 'demo' and o['currency'] == 'USD' and o['seller_rating'] >= 95]
pairs = sorted((a['price_cents']+b['price_cents'], *sorted([a['listing_id'],b['listing_id']])) for a,b in itertools.combinations(eligible,2) if a['seller'] != b['seller'])
assert selection['candidate_total'] == len(offers) == 7
assert list(pairs[0]) == selection['selected']['key'] == [5863,12,19]
assert summary['passed'] and len(summary['steps']) == 19 and all(s['status'] == 'matched' for s in summary['steps'])
assert len(summary['independent_checks']) == 19 and all(c['passed'] is True for c in summary['independent_checks'])
assert summary['supervision']['consumed_checkpoints'] == 2
assert summary['integrity_errors'] == []

reviews = []
input_hashes = {str(EXP/'public-execution-summary.json'):digest(EXP/'public-execution-summary.json')}
for item in summary['supervision']['reviews']:
    folder = CASE/item['directory']
    packet = read(folder/'request.json')
    decision = read(folder/'decision.json')
    assert digest(folder/'request.json') == decision['request_sha256'] == item['request_sha256']
    assert packet['request_id'] == decision['request_id'] == item['request_id']
    assert decision['reviewer'] == 'gpt-6.1-sol' and decision['decision'] == 'continue'
    assert packet['independent']['decision'] == 'continue'
    assert all(c['passed'] is True for c in packet['independent']['checks'])
    for name, sha in packet['public_evidence_sha256'].items():
        assert digest(folder/name) == sha
    reviews.append({'item':item,'packet':packet,'decision':decision,'folder':folder})
    input_hashes[str(folder/'request.json')] = digest(folder/'request.json')
    input_hashes[str(folder/'decision.json')] = digest(folder/'decision.json')

events = summary['events']
sequence = {}
for s in summary['steps']:
    by_kind = {e['kind']:e['seq'] for e in events if e.get('step') == s['id']}
    assert by_kind['prediction'] < by_kind['action_dispatch'] < by_kind['action_complete']
    sequence[s['id']] = by_kind
gate_order = []
for r in reviews:
    cp = r['item']['checkpoint_id']
    ev = {e['kind']:e['seq'] for e in events if e.get('checkpoint_id') == cp}
    assert ev['intervention_requested'] < ev['intervention_decision'] < ev['checkpoint_granted'] < ev['checkpoint_consumed'] < sequence[r['item']['before_step']]['action_dispatch']
    gate_order.append({'checkpoint':cp,**ev,'next_dispatch':sequence[r['item']['before_step']]['action_dispatch']})

def usd(cents):
    return f'USD {Decimal(cents)/100:.2f}'

final_order = notes['final_public_checkout']['order']
assert final_order['total_cents'] == 5863 and len(final_order['items']) == 2
assert notes['pre_checkout_cart_commitment']['total_cents'] == 5863
assert 'USD 0.00' in summary['final_public_ui']['text'] and summary['final_public_ui']['fields']['checkout_disabled'] == ''

sections = ['<h1>一次带真实评估介入的复杂网页任务</h1>',
'<p class="lead">任务成功：19/19个原生浏览器步骤匹配，19项独立终点检查均为true；两次计划内Solar审阅实际暂停并放行。两个不同卖家的报价合计<b>USD 58.63（5863美分）</b>，低于USD100预算，一次结账生成paid订单。</p>',
'<p>实验：phase1-complex-pw-20261020-1815 / execution-001；模型作者和独立审阅模型均为gpt-6.1-sol。本文只读取主Agent导出的公共执行摘要、冻结计划/规则、公开intervention packet/decision和公开notes；没有读取private-supervision、原始步骤JSON中的后台状态或评估器源码。独立检查的19个布尔结论按公共摘要原样报告，不用模型预测替代真值。</p>',
'<p>'+link(RUN/'task-budgeted_two_seller_purchase.html','完整单任务人类证据')+' · '+link(RUN/'inputs/scripts.py','本次冻结并执行的完整Playwright脚本')+' · '+link(MODEL/'operation-and-intervention.html','作者冻结的操作与介入条件')+' · '+link(EXP/'public-execution-summary.json','仅公共渠道执行摘要')+'</p>',
'<h2>任务要求与复杂性</h2><p>登录demo，经站内搜索进入release221的The Dark Side Of The Moon市场；提交卖家评分≥95%及价格升序。在完整可见结果中排除demo自己的报价，选择两个不同卖家的USD报价，各一件，按（总价、较小listingID、较大listingID）取最小组合，且≤10000美分。首件入车后必须经购物车release链接→详情→Marketplace返回、重新筛选并核对记忆中的第二报价，再入车。第一次加购与最终结账前分别真实暂停。只有独立评价与Solar均允许且状态复核不变，才执行紧邻动作；最终只能点击一次Checkout。</p>',
'<p>复杂性来自跨页面导航、两个不同报价对象、全候选枚举与组合计算、排除自售和预算约束、跨页对象状态记忆、入车与订单副作用验证，以及两次独立监督。它是一个预先公开的源码可见组合演示，不是未见组合泛化测试。</p>',
'<h2>真实候选与选择计算</h2><p>市场页显示7个报价且DOM有7行，未超过默认50行；评分筛选95.0、价格升序均可见。最便宜的demo报价USD21.45被任务约束排除。剩余'+str(len(eligible))+'个合格报价产生'+str(len(pairs))+'个不同卖家组合；从公开行重新计算的最小键为[5863,12,19]。这次报告复算使用公开DOM派生notes；独立评价并未将notes当答案输入。</p>']
offer_rows = []
for o in offers:
    offer_rows.append([str(o['listing_id']),esc(o['seller']),str(o['seller_rating'])+'%',usd(o['price_cents']),esc(o['ships_from']), '排除：demo自售' if o['seller']=='demo' else ('选中' if o['listing_id'] in (12,19) else '其他候选')])
sections += [table(['listing','卖家','评分','单价','发货地','决策'],offer_rows),
'<p><b>listing12：</b>ewright99，96.9%，USD28.12；<b>listing19：</b>jenniferross18，97.3%，USD30.51。2812+3051=5863美分，即<b>USD28.12+USD30.51=USD58.63</b>。预算余量USD41.37。原cart UI不显示quantity，数量必须结合页面自身触发的GET /api/cart实际响应确认各为1，不能只凭两行外观判断。</p>',
'<p>'+link(CASE/'notes/selection_commitment.json','完整候选与组合比较')+' · '+link(CASE/'notes/second_offer_memory_recheck.json','第二报价跨页记忆与回读')+' · '+link(CASE/'notes/pre_checkout_cart_commitment.json','结账前公开cart响应与合计')+'</p>',
'<h2>两次评估介入：实际发生了什么</h2><p>关卡位于UI步骤之外。每次先写公共request和证据哈希，任务线程真实等待独立Solar审阅；独立评价continue不能被Solar单方面替代，Solar continue也不能覆盖独立stop/unknown。放行后Harness还要重新观察/评价，状态变化则停止。下面两个packet中的独立检查均为true，Solar均写continue，事件记录随后grant并consume，再dispatch紧邻UI动作。</p>']
review_text = {
'selection_committed':'首次加购前，Solar从市场截图、DOM和原生href复算七行中的不同卖家组合；排除demo自售，确认12+19=USD58.63，评分均≥95及登录公开响应200。独立公开检查10项全true，包括完整市场、demo认证、初态空cart、预算可行、此前没有业务写入。授权只限listing12的紧邻first_cart_add，明确不授权Checkout。',
'before_checkout':'结账前，Solar看到cart两个卖家和USD30.51/28.12单价、USD58.63合计；UI不显示qty，因此另核对最新浏览器GET/cart响应两listing各qty1，与原选择和第二报价回读相同。公开流量显示恰两次成功加购、此前无checkout。独立公开检查16项全true，包括精确最优pair、跨页历史、无提前订单及无关状态保持。仅授权紧邻一次Checkout，禁止重复或重试。'
}
for r in reviews:
    item,packet,decision,folder = r['item'],r['packet'],r['decision'],r['folder']
    sections += ['<h3>'+esc(item['checkpoint_id'])+' → '+esc(item['before_step'])+'</h3><p>'+review_text[item['checkpoint_id']]+'</p><p>实际审阅等待：<b>'+f"{item['review_elapsed_seconds']:.3f}"+'秒</b>；Solar分类planned_review；decision=continue；status=consumed。request_id='+esc(item['request_id'])+'。</p>',
    '<p>'+link(folder/'request.json','公共request/独立公开判定')+' · '+link(folder/'decision.json','Solar签名字段与理由')+' · '+link(folder/'ui.dom.json','公开DOM')+' · '+link(folder/'ui.png','公开截图')+'</p>',
    image(folder/'ui.png',item['checkpoint_id']+'：本次实际审阅截图'),
    table(['独立关卡check id','公共结果'],[[esc(c['id']),'true'] for c in packet['independent']['checks']])]
sections += ['<h3>事件顺序证明：批准先于写动作</h3>', table(['checkpoint','请求seq','Solar决策seq','grant seq','consume seq','下个UI dispatch seq'],[[esc(g['checkpoint']),g['intervention_requested'],g['intervention_decision'],g['checkpoint_granted'],g['checkpoint_consumed'],g['next_dispatch']] for g in gate_order]),
'<p>第一关：seq352请求→353决策→357grant→361consume→363首次加购dispatch；第二关：583请求→584决策→588grant→592consume→594结账dispatch。两关是实际planned review，不是事后附写说明。全部19个UI步骤也逐一检查prediction seq &lt; dispatch seq &lt; complete seq。</p>',
'<h2>完整19步：冻结预测、脚本与结果对应</h2>']
descriptions = ['打开登录表单','填写用户名demo','填写fixture密码（日志脱敏）','点击Sign in，登录200并到首页','填写站内搜索关键词','提交搜索，出现唯一release221卡片','点击release221，读Tracklist','点击Marketplace进入报价页','填写最低评分95.0','选择价格升序','Apply后确认7行完整候选、排序与评分；保存组合计算','第一关实际通过后，原生点击listing12加购一次；cart响应201/GET200，qty1、2812美分','从cart的release链接回详情','从详情Marketplace链接回报价页','重新填写95.0','重新选价格升序','重新Apply，listing19对象、价格与卖家等记忆回读一致','原生点击listing19加购一次；cart两对象各qty1、总5863美分','第二关实际通过后，点击一次Checkout；响应200、paid订单121、空cart']
step_rows=[]
mapping=[]
for index,(spec,actual,description) in enumerate(zip(plan['cases'][0]['steps'],summary['steps'],descriptions),1):
    assert spec['id']==actual['id']
    seq=sequence[spec['id']]
    mapping.append({'step':spec['id'],'rule_ids':spec['rule_ids'],'prediction':spec['expect'],'invariants':spec.get('invariants',[]),'status':actual['status'],'event_sequence':seq})
    step_rows.append([index,esc(spec['id']),esc(', '.join(spec['rule_ids'])),esc(description),'matched',f"{actual['elapsed_seconds']:.3f}",f"{seq['prediction']}→{seq['action_dispatch']}→{seq['action_complete']}"])
sections += [table(['步','stepID','规则','实际过程','监控','步骤秒','预测→dispatch→完成seq'],step_rows),
'<p>关键代码边界：<code>h.checkpoint("selection_committed")</code>紧邻<code>with h.step("first_cart_add")</code>；<code>h.checkpoint("before_checkout")</code>紧邻<code>with h.step("checkout")</code>。所有动作使用原生Playwright定位器和滚动确认；跨页记忆、pair比较与公开响应通过h.note留存，不开放后台读取能力。</p>',
'<p>'+link(RUN/'inputs/scripts.py','执行冻结脚本')+' · '+link(RUN/'inputs/model/plan.json','19步完整预测/不变式/关卡计划')+' · '+link(RUN/'inputs/model/rules.json','27条冻结规则')+' · '+link(OUT/'public-evidence.json','本说明的公共证据摘要与映射')+'</p>',
'<h2>最终结果与独立终点</h2><p>浏览器实际checkout响应和公开note：order121，status=paid，currency=USD，total_cents5863；items恰含listing12/2812美分/qty1和listing19/3051美分/qty1。随后页面显示Your cart is empty与USD0.00，Checkout disabled；原站点alert为“Checkout complete (order created).”。这些公开响应可直接复核；原状态持久化和无关副作用则引用独立评价返回的布尔结果。</p>',
table(['独立终点check id','公共结果'],[[esc(c['id']),'true'] for c in summary['independent_checks']]),
'<p>19项检查包含精确订单/items、两listing状态变化、旧记录/无关状态保持、仅两次qty1入车及一次checkout、导航历史和实际cart读回。本文没有读取私有后台快照来重建这些结论，也不把notes或模型断言当独立真值。integrity_errors=[]，activation_allowed=true仅适用于本次明确任务和固定运行。</p>',
'<h2>实际耗时与未发生的异常分支</h2>',table(['项目','实际值'],[['全任务实际耗时','196.796秒'],['两次review等待合计','128.423秒'],['其他浏览器/记录/管理开销合计','68.373秒'],['planned review实际使用','2/2；最多3次预算'],['UI动作与步骤','19 dispatched / 19 completed / 19 matched'],['实际故障诊断/重试','本业务未发生故障诊断；无自动重复写入']]),
'<p>240秒/次、最多3次review、单case900秒是冻结上限，不是实际耗时。全程包含review等待；68.373秒差值还含记录与管理开销，不能称纯网页净速度。本次只有一个预先公开任务、一次成功实测；没有速度对照、泛化测试或稳健性统计，token/费用未提供保持null。</p>',
'<p>本次已实际验证的是两个planned review的continue→grant→consume路径。locator不唯一、时序超时、站点实现拒绝、预算不足、报价变价、写入结果不明、Solar/独立拒绝或unknown、决策陈旧/超时、状态复核改变等，仅由脚本、协议或通用组件检查覆盖，本业务中未触发，不能写成已经历并恢复。冻结策略均为diagnose_and_stop；未知Add/Checkout结果不自动重试，修订必须另版本/新运行。</p>',
'<h2>范围与离线证据</h2><p>源码使用沿用独立Solar第一阶段完整审阅：110文件登记，其中99文本实现/配置/说明已读、1锁元数据、6装饰资源登记、4任务/测试/外部同步内容排除。并非操作系统强隔离或浏览器独立学习。本任务采用原网站已可执行的静态login/cart-add/cart-read/checkout，避开已知afterFiles动态API遮挡；不代表membership、seller或动态删除被修复，也不把上一轮失败改为成功。</p>',
'<p>本页面嵌入的是本地公开关卡截图，CSS内联，无在线站点/CDN/JS依赖。'+link(RUN/'task-budgeted_two_seller_purchase.html','完整人类任务页')+'可继续查看原始动作证据；'+link(MODEL/'operation-and-intervention.html','完整中文操作和异常介入条件')+'保留所有设计分支。冻结模型/运行文件未修改，本文仅新增solar-presentation目录。</p>']
payload={'source_channels':'public summary, frozen public plans/rules, public intervention packets/decisions and public notes only','run':'execution-001','metrics':summary['metrics'],'independent_checks':summary['independent_checks'],'supervision':summary['supervision'],'event_gate_order':gate_order,'step_rule_check_mapping':mapping,'candidate_count':len(offers),'eligible_count':len(eligible),'pair_count':len(pairs),'recomputed_optimum':pairs[0],'final_public_order':final_order,'input_hashes':input_hashes,'private_inputs_read':False,'frozen_artifacts_modified':False,'new_business_actions':0}
(OUT/'public-evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>复杂网页任务：19步与两次真实介入</title><style>body{font:16px/1.75 system-ui,sans-serif;max-width:1220px;margin:30px auto;padding:0 20px;color:#182338}.lead{background:#edf6f0;border-left:4px solid #307a45;padding:16px}h1{font-size:28px}h2{margin-top:38px}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}td,th{border:1px solid #d4dce6;padding:8px;vertical-align:top;overflow-wrap:anywhere}th{background:#eef2f6}a{color:#1958ac}figure{margin:18px 0}img{max-width:100%;height:auto;border:1px solid #ddd}figcaption{font-size:13px;color:#526071}code{background:#eef2f6}</style><body>'+'\n'.join(sections)+'</body></html>'
(OUT/'report.html').write_text(page,encoding='utf-8')

class Assets(HTMLParser):
    def __init__(self):
        super().__init__();self.urls=[];self.resources=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src'):self.urls.append(value)
            if key=='src':self.resources.append(value)

parser=Assets();parser.feed(page)
missing=[u for u in parser.urls if not urlsplit(u).scheme and not (OUT/unquote(urlsplit(u).path)).exists()]
remote=[u for u in parser.resources if urlsplit(u).scheme in ('http','https')]
assert not missing and not remote
(OUT/'presentation-checks.json').write_text(json.dumps({'public_input_only':True,'frozen_files_modified':False,'report_sha256':digest(OUT/'report.html'),'local_assets_and_links_checked':len(parser.urls),'missing_local_targets':missing,'remote_runtime_resources':remote,'19_prediction_dispatch_complete_order_valid':True,'two_checkpoint_before_dispatch_orders_valid':True,'request_decision_evidence_hashes_match':True,'money_units':'2812+3051=5863 cents = USD28.12+USD30.51=USD58.63'},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'steps':19,'checks':19,'reviews':2,'candidate_rows':len(offers),'eligible':len(eligible),'pairs':len(pairs),'total_usd':usd(5863),'local_links_assets':len(parser.urls),'missing':missing,'report':str(OUT/'report.html')},ensure_ascii=False))
