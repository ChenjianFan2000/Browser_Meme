"""Generate the measured report and standalone figures from frozen results."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json

from issue_lab.benchmark import ROOT, PRIVATE, delta, dump, read
from issue_lab.experiment_plan import CODE_METHODS, DIRECT_METHODS


LABELS = {
    'current':'当前方案：规则注释＋代码', 'verienv_clone':'VeriEnv 行为克隆',
    'worldcoder':'WorldCoder 提示适配', 'patchworld':'PatchWorld 提示适配',
    'gif_mcts':'GIF 单候选适配', 'poe_world':'PoE 属性专家适配',
    'agent2world':'Agent2World code-agent适配', 'luna_direct':'Luna Direct',
    'wma':'WMA 提示适配', 'webdreamer':'WebDreamer 提示适配',
    'webevolver':'WebEvolver 提示适配', 'webworld':'WebWorld 提示适配'}


def main():
    source = read(ROOT/'artifacts/results/summary.json')
    rows = {(r['method'],r['phase'],r['split']):r for r in source['rows']}
    def row(m,p,s): return rows[m,p,s]
    def fraction(m,p,s,key='exact'):
        r = row(m,p,s)
        return f"{r[key]}/{r['n']} ({100*r[key]/r['n']:.1f}%)"
    methods = CODE_METHODS + DIRECT_METHODS
    lines = [
        '# 本地 issue 子域：Luna 派生实验结果', '',
        '日期：2026-10-20。已完成12篇定向文献调研、10个额外主仓库与2个子模块下载、11个项目的原始组件执行检查，以及31次真实 `gpt-6-luna` 子代理学习/预测回合。这里的12个条件是本轮派生实现和提示适配，**不是12个论文原系统的端到端复现或排名**。', '',
        '当前方案开发修正后，一步预测24/24，多步完整状态预测6/12；Luna Direct在相同初始证据下为24/24、6/12。六条新规则证据使当前方案变化测试由3/12提高到12/12，未变化子集保持21/21。当前证据支持可修正性，但没有证明当前代码方案比直接预测更强。', '',
        '## 固定设置与真实运行范围', '',
        '- 自建本地 issue 网页，6条issue、8类动作，可重置；不依赖WebArena、ServiceNow或真实GitLab。',
        '- 学习36条转移；开发16条，代码条件最多提供8条失败反例修正一次；最终一步24条、开放环组合12条（共45步）、规则变化12条；适应仅给6条新转移。',
        '- 每个条件均使用Luna/high。代码7条件各3回合，直接预测5条件各2回合，共31回合。直接预测按48条/36条轨迹批量提交，不是逐步独立API调用；没有给直接条件开发反馈。',
        '- 初次代码模型和直接预测的学习证据相同。修正后的代码额外用过开发反例，单独列出；没有可核验token账单，不声称等token预算。',
        '- 所有预测先保存，随后冻结输入/输出SHA-256再评分。原始产物未手工修正；开放环每步使用上一预测，不插入真实中间状态。',
        '- 每步以独立真实领域状态作答案，原版VeriEnv judge DSL判定规范化状态SHA-256。仅排序issue记录、labels和selected集合，保留评论顺序、visible_ids顺序、大小写、空白和JSON类型。',
        '- “结构合法”指返回完整公开JSON字段和类型；不等于每个枚举值、属性范围或业务规律都正确。完整匹配指标会检查这些值。', '',
        '## 相同初始学习证据的结果', '',
        '以下均为initial版本。多步最终状态与整条轨迹完全正确数在本轮恰好相同；逐步正确数仍另列。百分比只描述这批固定案例。', '',
        '| Luna条件 | 表示 | 一步完整匹配 | 多步完整轨迹 | 多步正确步数 | 结构合法轨迹（全部48条） |',
        '|---|---|---:|---:|---:|---:|']
    for m in methods:
        r = row(m,'initial','rollout')
        valid = sum(row(m,'initial',s)['valid'] for s in ['one_step','rollout','drift'])
        lines.append(f"| {LABELS[m]} | {'代码' if m in CODE_METHODS else '直接预测'} | {fraction(m,'initial','one_step')} | {fraction(m,'initial','rollout','all_steps_exact')} | {r['step_exact']}/{r['steps']} | {valid}/48 |")
    lines += ['', 'WorldCoder条件初稿在完整观察中额外返回了`issue_updates`，这是接口错误；WebDreamer条件有6条多步轨迹返回非字符串评论列表，另有业务字段错误。错误保留在分母中。这些是本次Luna生成/格式适配的失败，不能归因为原论文模型的性能。', '',
              '## 一次开发修正后的代码模型', '',
              '| Luna代码条件 | 一步匹配 | 多步完整轨迹 | 多步正确步数 | 初稿一步→修正后 |',
              '|---|---:|---:|---:|---:|']
    for m in CODE_METHODS:
        r = row(m,'repaired','rollout')
        lines.append(f"| {LABELS[m]} | {fraction(m,'repaired','one_step')} | {fraction(m,'repaired','rollout','all_steps_exact')} | {r['step_exact']}/{r['steps']} | {row(m,'initial','one_step')['exact']}/24 → {row(m,'repaired','one_step')['exact']}/24 |")
    lines += ['', '开发/一步测试使用相同操作模板、不同对象种子，因此24/24只支持这个范围内的参数和状态迁移。未演示的多步序列仍能区分失败；不能把一步满分理解成已解决网页组合泛化。', '',
              '## 规则变化与保留能力', '',
              '代码条件的“变化前”使用repaired模型；直接条件使用initial预测。变化后均只增加六条公开新转移。最后一列只统计未改变语义的21条旧案例。', '',
              '| Luna条件 | 变化前匹配（12条） | 适应后匹配（12条） | 未变化案例：前→后（21条） |',
              '|---|---:|---:|---:|']
    for m in methods:
        before = 'repaired' if m in CODE_METHODS else 'initial'
        lines.append(f"| {LABELS[m]} | {fraction(m,before,'drift')} | {fraction(m,'adapted','drift')} | {row(m,before,'unchanged_v1')['exact']}/21 → {row(m,'adapted','unchanged_v1')['exact']}/21 |")
    lines += ['', 'WorldCoder和Agent2World适配版未推断出“缺关闭原因”的校验先于blocked检查，均在3条组合前提案例上失败。其余多数条件在这个小变化集合上达到上限，说明需要更强的变化与交互证据设计。', '',
              '适应后的模型已学习新规则；拿它预测旧规则下的关闭/筛选案例，本来就可能不一致。原始JSON保留这些成绩，但不把冲突案例下降称为遗忘，也不把旧版rollout当作新版组合测试。', '',
              '## 失败案例给研究带来的信息', '',
              '1. **业务记录正确不代表完整观察正确。** 当前repaired模型在12条组合的最终业务记录上12/12正确，但界面状态9/12、反馈9/12，联合完整匹配只有6/12。关闭筛选列表中的issue后没有重新计算`visible_ids`；失败关闭之后成功加标签又保留旧的`blocked`反馈。',
              '2. **单步开发集没有覆盖所有跨步依赖。** PatchWorld和Agent2World提示适配也在筛选后关闭的读出更新上出错；仅修正孤立转移不会必然消除它。',
              '3. **直接预测也有组合遗漏。** Luna Direct有批量标签只更新部分对象，以及失败后成功反馈未复位的问题。WebWorld提示适配本轮12/12，只是单次样本结果，不能推断其原模型优于其他论文。',
              '4. **变化规则可能证据不足。** 六条适应转移没有直接演示blocked与缺原因同时出现时的优先级，因此9/12与12/12反映了未辨识规则的猜测差异；一次命中不能证明模型已充分识别规则。下一轮应允许主动查询区分这两个假设。', '',
              '逐例证据见 [failure_examples.json](artifacts/results/failure_examples.json)，所有预测见 `artifacts/results/*.test.json`。', '',
              '## 与上游代码的实际集成', '',
              '- VeriEnv：原始判定DSL用于全部统一评分；本地站点提供HTTP、重置与可发现的Python SDK布局，并导出48条私有VeriEnv rinfo任务。没有运行BrowserGym导航或RFT训练。',
              '- PatchWorld：除初稿提示外，实际执行原始BaseWorldModel/validate_model对冻结产物回放。repaired的24条一步转移、adapted的12条变化转移均通过原版与严格检查。初稿6条严格错误（每条通常被验证两次）；原版归一化只报告3条错误。',
              '- 其他项目：原始组件审计11/11成功，实际组件/替代接口逐一列于[UPSTREAM_INTEGRATION.md](UPSTREAM_INTEGRATION.md)。该成功数不是预测成功率。',
              '- GIF条件没有MCTS分支搜索，PoE条件没有概率权重拟合，Agent2World条件没有完整多角色研发链；WMA/WebEvolver/WebWorld没有作者训练权重。它们的完整算法尚未在本地子域复现。',
              '- Code2World已下载并执行原始提示/HTML处理接口检查，但未运行AndroidWorld、专用8B权重或渲染。其截图→HTML目标与本轮JSON业务指标不等价，预测列记“不适用/未运行”，没有替它编造分数。Memento 3未找到可核验官方代码。', '',
              '## 资源与验证', '',
              '31回合的请求/输出字节数、哈希和调度时间记录在[frozen_run.json](artifacts/frozen_run.json)。没有真实token/费用账单。请求导出到产物生成的时间包含等待，不能当作模型纯推理延迟。', '',
              '| 代码条件（repaired） | 45步predict函数总时间 | 每步均值 |',
              '|---|---:|---:|']
    for m in CODE_METHODS:
        r = row(m,'repaired','rollout')
        lines.append(f"| {LABELS[m]} | {1000*r['prediction_seconds']:.3f} ms | {1e6*r['prediction_seconds']/r['steps']:.1f} μs |")
    lines += ['', '以上只计内存中的Python函数调用，含模型内部复制，不含浏览器、网络、学习、修正或判定；直接预测的离线差分应用时间不能与它比作LLM速度。严格UI/API速度对照尚未完成。', '',
              '验证：16项领域/SDK/评分测试通过；31个冻结产物全部完成评分，无进程加载失败或超时；两次重放业务分数一致。原生PatchWorld首轮曾因UTF-8 BOM加载失败，已保存首轮记录并仅修复适配器的解码方式，模型字节未变。', '',
              '当前限制：每个条件只生成一次，测试仅3个对象种子，不做显著性或算法排名；结构化全观察和固定动作接口不检验主动控件发现、视觉定位、隐藏状态、异步过程或真实GitLab。子代理按指令隔离读取，AST白名单不是操作系统安全沙箱。', '',
              '浏览器端到端验收未完成：agent-browser连接超时；备用Chrome MCP被自动审批拒绝，原因为当前策略不允许审批。已完成真实HTTP/SDK验证。', '',
              '## 重放', '',
              '```powershell', 'python -m pytest tests -q', 'python -m issue_lab.upstream_audit',
              'python -m issue_lab.replay replay', 'python -m issue_lab.report', 'python -m issue_lab.server', '```', '',
              '重放无需Luna/API凭据；它使用冻结模型和已提交的直接预测。重新生成模型必须发起新的有记录子代理实验，不能把离线重放称为新的LLM运行。不要覆盖当前冻结产物或重新运行build后混用旧哈希。', '',
              '完整数字：[summary.csv](artifacts/results/summary.csv)；独立图：[PNG](artifacts/results/comparison.png) / [PDF](artifacts/results/comparison.pdf)；下一轮方案：[NEXT_RESEARCH.md](NEXT_RESEARCH.md)。', '']
    (ROOT/'EXPERIMENT_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    examples = []
    truth = {s['id']:s for group in read(PRIVATE/'splits.json').values() for s in group}
    for path in sorted((ROOT/'artifacts/results').glob('*.test.json')):
        result, seen = read(path), set()
        for r in result['rows']:
            key = (r['split'], r['family'])
            if r['final_exact'] or key in seen:
                continue
            seen.add(key)
            i = next(j for j,s in enumerate(r['scores']) if not s['exact'])
            case = truth[r['id']]
            pred = r['predicted'][i] if len(r['predicted'])>i else None
            examples.append({'artifact':path.name,'id':r['id'],'split':r['split'], 'first_error_step':i,
                'action':case['actions'][i],'runtime_error':r['error'], 'predicted':pred,
                'expected':case['expected'][i], 'needed_delta':delta(pred,case['expected'][i]) if isinstance(pred,dict) else None})
    dump(ROOT/'artifacts/results/failure_examples.json',examples)
    make_plot(rows,methods)
    print(json.dumps({'report':'EXPERIMENT_RESULTS.md','conditions':len(methods),'failure_examples':len(examples)}))


def make_plot(rows, methods):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    names = ['Current','VeriEnv clone','WorldCoder prompt','PatchWorld prompt','GIF single candidate',
             'PoE attribute experts','Agent2World code prompt','Luna Direct','WMA prompt',
             'WebDreamer prompt','WebEvolver prompt','WebWorld prompt']
    y = np.arange(len(methods))
    fig, axes = plt.subplots(1,3,figsize=(14,7),sharey=True)
    for ax,split,title in zip(axes[:2],['one_step','rollout'],['Initial: one-step (n=24)','Initial: full rollout (n=12)']):
        values = [100*rows[m,'initial',split]['exact']/rows[m,'initial',split]['n'] for m in methods]
        ax.barh(y,values,color=['#3569a3' if m in CODE_METHODS else '#d08b35' for m in methods])
        for index,v in enumerate(values): ax.text(min(v+1,102),index,f'{v:.1f}'.rstrip('0').rstrip('.'),va='center',fontsize=8)
        ax.set_title(title,fontsize=11)
    before = [100*rows[m,'repaired' if m in CODE_METHODS else 'initial','drift']['exact']/12 for m in methods]
    after = [100*rows[m,'adapted','drift']['exact']/12 for m in methods]
    axes[2].barh(y-.18,before,height=.34,color='#b4c0cf',label='Before change evidence')
    axes[2].barh(y+.18,after,height=.34,color='#347b58',label='After 6 new examples')
    axes[2].set_title('Rule change (n=12)',fontsize=11,y=1.14)
    axes[2].legend(loc='upper center',bbox_to_anchor=(.5,1.10),ncol=1,frameon=False,fontsize=8)
    axes[0].set_yticks(y,names,fontsize=9)
    axes[0].invert_yaxis()
    for ax in axes:
        ax.set_xlim(0,112)
        ax.set_xticks([0,25,50,75,100])
        ax.set_xlabel('Exact match (%)')
        ax.grid(axis='x',alpha=.2)
        ax.set_axisbelow(True)
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Luna transfer pilot — prompts/components, NOT original paper systems',fontsize=13)
    fig.text(.03,.015,'One generated artifact per condition; shared evidence, unequal compute; no statistical ranking. Code before-drift models include one dev repair.',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,.95])
    fig.savefig(ROOT/'artifacts/results/comparison.png',dpi=180)
    fig.savefig(ROOT/'artifacts/results/comparison.pdf')
    plt.close(fig)


if __name__ == '__main__': main()
