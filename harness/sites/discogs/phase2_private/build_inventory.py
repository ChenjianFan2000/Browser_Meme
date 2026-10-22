"""Build the private inventory and per-case initial databases, never start services."""
import hashlib
import json
from pathlib import Path
import sqlite3
ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime/phase2-discogs-20261021-01'
OUT = ROOT / 'harness/experiments/phase2-discogs-20261021-01/private'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    baseline = RUNTIME / 'data/baseline.db'
    cases=[]
    with sqlite3.connect(baseline.resolve().as_uri()+'?mode=ro',uri=True) as db:
        demo=db.execute("select id from users where username='demo'").fetchone()[0]
        releases=db.execute('select id,title from releases where id between 1 and 20 order by id').fetchall()
        listings=db.execute("select m.id,m.release_id,r.title from marketplace_listings m join releases r on r.id=m.release_id where m.status='active' order by m.id limit 10").fetchall()
    for i,(rid,title) in enumerate(releases[:10]):
        kind='collection' if i%2==0 else 'wantlist'
        cases.append(dict(id=f'P{i+1:02}',split='new_parameter',kind='membership_add',table=kind+'_items',release_id=rid,title=title,entry=f'/release/{rid}',goal=f'将唱片 {title}（#{rid}）加入自己的'+('收藏' if kind=='collection' else '愿望单')+'，并确认结果。',seed={'membership':'absent'}))
    for i,(lid,rid,title) in enumerate(listings):
        remove=i>=5
        cases.append(dict(id=f'S{i+1:02}',split='new_state',kind='cart_remove' if remove else 'cart_increment',listing_id=lid,release_id=rid,title=title,entry='/cart' if remove else f'/sell/release/{rid}',goal=(f'从自己的购物车移除唱片 {title}（报价#{lid}），保留其他内容。' if remove else f'将报价#{lid}（{title}）再加入购物车一次，保留已有数量与其他内容。'),seed={'cart_quantity':i+1}))
    for i,(rid,title) in enumerate(releases[10:15]):
        kind='collection' if i%2==0 else 'wantlist'
        cases.append(dict(id=f'B{i+1:02}',split='rejection_boundary',kind='membership_idempotent',table=kind+'_items',release_id=rid,title=title,entry=f'/release/{rid}',goal=f'再次将已存在的唱片 {title}（#{rid}）加入自己的'+('收藏' if kind=='collection' else '愿望单')+'，检查是否产生重复记录。',seed={'membership':'present'}))
    for i,quantity in enumerate([0,-1,100,101,1000]):
        rid,title=releases[15+i]
        cases.append(dict(id=f'B{i+6:02}',split='rejection_boundary',kind='listing_reject',release_id=rid,title=title,quantity=quantity,entry='/sell',goal=f'在卖家页面选择唱片 {title}（#{rid}），其他字段使用页面默认值，将数量设为{quantity}并提交上架，确认是否被拒绝及是否留下上架记录。',seed={}))
    target=RUNTIME/'private/initial_states';target.mkdir(parents=True,exist_ok=True)
    for case in cases:
        path=target/(case['id']+'.db')
        if path.exists(): raise RuntimeError('Refuse inventory rebuild over initial state')
        with sqlite3.connect(baseline.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(path) as db:
            source.backup(db)
            if 'membership' in case['seed']:
                table=case['table']; db.execute(f'delete from {table} where user_id=? and release_id=?',(demo,case['release_id']))
                if case['seed']['membership']=='present': db.execute(f'insert into {table}(user_id,release_id) values (?,?)',(demo,case['release_id']))
            if 'cart_quantity' in case['seed']:
                db.execute('insert into cart_items(user_id,listing_id,quantity) values (?,?,?)',(demo,case['listing_id'],case['seed']['cart_quantity']))
                # A distractor protects against clearing the whole cart.
                other=next(row[0] for row in listings if row[0]!=case['listing_id'])
                db.execute('insert into cart_items(user_id,listing_id,quantity) values (?,?,?)',(demo,other,2))
            db.commit()
        case.update(initial_db=str(path.relative_to(ROOT)),initial_sha256=sha(path),validation='source_supported_ui_unverified',dynamic_route_blocker_retained=True)
    record=dict(run_id='phase2-discogs-20261021-01',version=1,status='inventory_locked_not_execution_ready',denominator=30,split_counts={'new_parameter':10,'new_state':10,'rejection_boundary':10},seed=20261021,repetitions=1,account_fixture='public ordinary demo fixture; obtain credentials from UI',cases=cases,unknowns=['All 30 UI reachability checks pending; prior dynamic-route blocker must be measured unchanged.','New parameter/state novelty relative to exploration must be audited after learner freeze; overlap invalidates novelty label, never removes denominator.','No score or true freeze-generalization claim until protocol and learner versions are frozen.'])
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'cases.private.json').open('x',encoding='utf8') as f: json.dump(record,f,ensure_ascii=False,indent=2)
    reserve=dict(status='reserved_not_disclosed_to_learner',templates=['filter_then_select_then_cart_then_checkout','search_then_wantlist_then_collection','create_listing_then_marketplace_verify_then_deactivate'],partition='Stage 3 only. Audit exploration traces before claiming an unseen composition; abort novelty claim for demonstrated template.')
    with (OUT/'phase3-reserve.private.json').open('x',encoding='utf8') as f: json.dump(reserve,f,indent=2)
    print(json.dumps({'denominator':len(cases),'inventory_sha256':sha(OUT/'cases.private.json'),'services_started':False,'ui_runs':0}))
if __name__=='__main__': main()
