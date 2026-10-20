"""Materialize this version's source-reviewed model documentation; never executes site code."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
SRC = ROOT / 'veri_env/external/VeriEnv-main/websites/discogs'
rules = []


def rule(id, statement, refs, preconditions, branches, forbidden, ui='native UI'):
    rules.append(dict(id=id, statement=statement, source_refs=refs, preconditions=preconditions,
                      branches=branches, forbidden_side_effects=forbidden,
                      status='source_supported_browser_unverified', interface=ui,
                      browser_evidence=[], check_ids=[id + '-endpoint', id + '-invariants']))


rule('AUTH-LOGIN', 'Username or email login issues a bearer JWT on success; the UI stores it in an httpOnly sameSite=lax cookie and replaces the URL with next or /.',
     ['backend/app/api/auth.py:38-45','frontend/src/app/api/auth/login/route.ts:5-27','frontend/src/app/login/LoginClient.tsx:9-49'],
     ['username_or_email and password supplied'], ['valid: 200 token / UI {ok:true}', 'unknown user or wrong password: 400 Invalid credentials, visible raw error, remain login'],
     ['no account, cart, order, catalog or membership changes', 'failed fresh login must not create authenticated session'])
rule('AUTH-GATE', 'All account mutations/reads require current user resolved from a valid JWT subject; UI 401 redirects preserve return target.',
     ['backend/app/api/deps.py:13-31','frontend/src/components/ReleaseActions.tsx:23-36','frontend/src/app/cart/CartClient.tsx:38-79','frontend/src/app/me/collection/page.tsx:15-34','frontend/src/app/sell/page.tsx:46-61'],
     ['authenticated account operations'], ['missing bearer: framework 401', 'invalid/expired JWT: 401 Invalid or expired token', 'missing user: 401 User not found', 'anonymous collection click: login?next=/release/id; login does not replay collection POST', 'anonymous cart add: login returns to /cart?add=id, then retries add'],
     ['refusals change no business state'])
rule('AUTH-LOGOUT', 'Sign out clears the cookie then refreshes/pushes home; it does not invalidate JWT server-side.',
     ['frontend/src/components/LogoutButton.tsx:10-26','frontend/src/app/api/auth/logout/route.ts:5-8','frontend/src/components/Header.tsx:9-11'],
     ['cookie-backed UI session'], ['sign out: cookie expiry and home', 'Header treats cookie presence as signed in without validating it'], ['no business state mutations'])
rule('AUTH-REGISTER', 'API registration validates schema and exact username/email uniqueness, hashes password, creates a user; there is no registration page.',
     ['backend/app/api/auth.py:18-35','backend/app/schemas/user.py:9-18','backend/app/models/user.py:12-33'],
     ['username length 3..50; valid email; password length 8..128; optional display_name <=120'], ['201 UserOut, no token', '400 Username already taken', '400 Email already registered', '422 schema refusal'], ['no other users or business records change'], 'API only; not UI validation')
rule('CAT-SEARCH', 'Search trims q, matches title or main artist using case-insensitive SQL substring pattern, sorts year descending/null last then title, limits 30; it does not search genre/style/label.',
     ['backend/app/api/catalog.py:351-377','frontend/src/app/search/page.tsx:12-37','frontend/src/components/Header.tsx:22-36'],
     ['q string'], ['empty/whitespace: []', 'match: release cards', 'no match: empty grid without explicit no-result sentence', 'SQL %/_ act as wildcards'], ['no database changes'])
rule('CAT-DETAIL', 'Release detail returns joined metadata, ordered tracks and current global collection/want counts plus active listing count/minimum price.',
     ['backend/app/api/catalog.py:274-348','frontend/src/app/release/[id]/page.tsx:20-180'],
     ['integer release id'], ['exists: metadata, tracklist, optional notes and actions', 'missing: API 404 Release not found; apiGet throws; exact Next error UI pending'], ['read does not mutate tables'])
rule('CAT-HOME', 'Home ranks most wanted (6), latest created (8), and highest order-item prices in last 31 days (6); promo tiles link home, featured banner links seeded title if available.',
     ['backend/app/api/catalog.py:82-174','frontend/src/app/page.tsx:10-178'], ['catalog accessible'],
     ['rankings data-dependent, ties not fully stable', 'newsletter Subscribe has no handler/form action; app store mockups are display only'], ['no newsletter subscription or database mutation from placeholder controls'])
rule('CAT-GENRE', 'Genre overview includes alphabetic styles, most-collected and earliest-year cards, decade and contributor aggregates, recent-sales ranking. Its navigation links lead to text search, not true genre-filtered search.',
     ['backend/app/api/catalog.py:177-271','frontend/src/app/genre/[slug]/page.tsx:48-191'], ['existing slug'],
     ['known slug: overview', 'unknown: API 404 Genre not found; exact Next error UI pending', 'style/release/artist links are q text searches', 'artist tiles are placeholders'], ['no catalog/business mutations'])
for kind, rid, begin, end, model in [('collection','MEM-COLLECTION',41,81,'collection'),('wantlist','MEM-WANTLIST',84,124,'wantlist')]:
    rule(rid, f'{kind} GET returns current user release cards; POST is idempotent; DELETE removes only current user membership and succeeds when absent. UI only exposes add and list, no remove control.',
         [f'backend/app/api/account.py:{begin}-{end}',f'backend/app/models/{model}.py:12-25',f'frontend/src/app/me/{kind}/page.tsx:15-58','frontend/src/components/ReleaseActions.tsx:23-66'],
         ['valid session', 'POST requires existing release'], ['GET 200 array, empty allowed', 'POST 200 {ok:true}, existing no-op', 'POST unknown release 404', 'DELETE 200 {ok:true} even absent', 'UI 401 login gate'],
         ['other users/membership kind and all catalog/cart/order/listing rows unchanged'])
rule('MEM-UI-COUNT', 'Successful Add to Collection/Wantlist always increments its local component count, including duplicate POST no-op; the separate summary remains its server-rendered value until navigation/reload.',
     ['frontend/src/components/ReleaseActions.tsx:20-36','frontend/src/app/release/[id]/page.tsx:83-108','backend/app/api/account.py:65-74','backend/app/api/account.py:108-117'],
     ['authenticated duplicate add'], ['first add: one durable membership', 'repeat add: local count +1 again; durable count unchanged', 'reload: counts recomputed from backend'], ['duplicates must not create another membership'])
rule('MKT-FILTER', 'Marketplace exposes only active listings for a release; text filters are exact equality, rating is minimum, sorting is price_asc/price_desc/newest with documented secondary keys.',
     ['backend/app/api/marketplace.py:15-90','frontend/src/app/sell/release/[id]/page.tsx:18-173'],
     ['valid release', 'sort enum; API limit 1..200 default50, offset>=0'], ['matching: total before pagination + rows', 'none: No listings match these filters.', 'unknown release 404', 'bad sort/nonnumeric rating/pagination 422 -> server page error', 'UI has no pagination or quantity control and renders at most default 50'], ['no state changes from filtering/sorting'])
rule('CART-ADD', 'Add requires active listing and positive quantity; an existing user/listing row accumulates quantity capped at 99; a new row is not capped by the route. No stock or seller-self-purchase check exists.',
     ['backend/app/api/account.py:161-179','backend/app/schemas/cart.py:29-31','backend/app/models/cart.py:12-28','frontend/src/app/cart/CartClient.tsx:57-79'],
     ['valid session', 'listing id and integer quantity'], ['201 CartOut with totals', '404 Listing not found for missing/inactive/sold', '400 Quantity must be >= 1', '422 invalid payload types', 'UI always adds one via /cart?add=id and replaces /cart', 'UI ignores non-401 add refusal then loads cart'], ['no order or stock decrement; no other users cart changes'])
rule('CART-READ', 'Cart joins current listing price, calculates sum(price*cart quantity), returns currency USD, latest-added first. UI hides quantity and displays unit prices alongside total.',
     ['backend/app/api/account.py:127-158','frontend/src/app/cart/CartClient.tsx:97-160'], ['valid session'], ['200 CartOut including empty', 'empty UI message and Checkout disabled', 'same listing twice yields one visible row but doubled total'], ['read never creates orders or changes listing'])
rule('CART-REMOVE', 'Remove deletes only the logged-in user cart row by cart_item_id, then UI reloads; absent/other-user IDs are successful no-ops.',
     ['backend/app/api/account.py:182-186','frontend/src/app/cart/CartClient.tsx:120-150'], ['valid session'], ['200 {ok:true}, item gone after reload', 'empty cart checkout disabled'], ['no listing/order changes; other users cart unchanged'])
rule('CHECKOUT', 'Checkout snapshots current listing prices and cart quantities into one paid USD order, marks each entire listing sold, leaves listing.quantity unchanged, clears only buyer cart, commits once.',
     ['backend/app/api/account.py:189-229','backend/app/db/session.py:17-22','frontend/src/app/cart/CartClient.tsx:162-180','backend/app/models/order.py:12-40'],
     ['valid session', 'nonempty cart, every listing still active'], ['200 OrderOut with item price/quantity snapshots', '400 Cart is empty', '400 A listing in your cart is no longer available; session closes without commit, pending flushed order should roll back', 'UI reload then alert Checkout complete (order created).', 'UI has no order history/detail page'],
     ['no listing quantity decrement', 'no changes to unrelated listings/orders/cart/memberships/catalog', 'refusal must not leave partial order or sold statuses'])
rule('SELL-CREATE', 'Authenticated seller creates active listing for existing release. Schema accepts arbitrary nonempty conditions, positive cents, three-character currency, origin 1..80, optional comments and qty1..99. UI fixes currency USD.',
     ['backend/app/api/account.py:263-285','backend/app/schemas/sell.py:6-15','frontend/src/app/sell/page.tsx:215-250'],
     ['selected release in UI', 'valid session and schema'], ['201 {id}', '404 Release not found', '422 schema error, no new listing', 'UI create disabled when no selected or cents<=0; invalid qty still submits', 'UI price field represents cents, not dollars'], ['no modifications to existing listings or other business tables'])
rule('SELL-MANAGE', 'My Listings includes all own statuses sorted newest first; Deactivate is soft deletion (inactive), including already inactive/sold own rows. Missing/non-owned returns 404.',
     ['backend/app/api/account.py:232-260','backend/app/api/account.py:302-309','frontend/src/app/sell/page.tsx:254-311'],
     ['valid session; owned listing to deactivate'], ['GET 200 {items:[...]} omits comments', 'DELETE 200 {ok:true}, row retained and visible inactive', 'DELETE missing/non-owned 404 Listing not found'], ['no physical row deletion; no changes to other sellers listings or orders/cart'])
rule('SELL-UPDATE', 'API PATCH updates explicitly supplied schema fields on owned listing; status permits active/inactive, even reactivating sold. Fields nullable in schema can reach non-null SQL columns and cause DB failure.',
     ['backend/app/api/account.py:288-299','backend/app/schemas/sell.py:18-25','backend/app/models/marketplace.py:21-31'],
     ['valid session; own listing; schema-valid partial body'], ['200 {ok:true}', '404 missing/non-owned', '422 out-of-range or invalid status', 'explicit null non-null-column fields: potential SQL 500 rollback, browser unverified'], ['no other listing changes'], 'API only; UI provides no edit/reactivate control')
rule('SELL-SEARCH-PROXY', 'Seller search uses /api/backend/search?q=..., but generic proxy builds upstream URL from path only and drops query. Backend search requires q, so expected 422 prevents selection/creation through normal seller search.',
     ['frontend/src/app/sell/page.tsx:95-109','frontend/src/app/api/backend/[...path]/route.ts:5-20','backend/app/api/catalog.py:351-354'],
     ['original proxy route wins Next routing'], ['expected 422 missing q; visible JSON error; selected remains unset', 'if runtime routing differs record counterexample and revise; do not bypass UI with API/DOM injected state'], ['failed search must not create listing'])
rule('UI-CONSENT', 'Accept All Cookies writes localStorage acceptance and hides banner; Cookie Settings has no handler.',
     ['frontend/src/components/CookieBanner.tsx:5-40'], ['banner visible in fresh storage'], ['accept: hidden, remains hidden on reload when storage works', 'storage unavailable: hide current mount but return later', 'settings: no implemented transition'], ['no backend business changes'])
rule('UI-NAV', 'Desktop menus reveal on hover. Header has catalog search, cart, account and sell/genre links. Footer/community links mostly target unimplemented routes, social links are #.',
     ['frontend/src/components/Header.tsx:38-211','frontend/src/components/Footer.tsx:26-98'], ['desktop viewport for hidden md:flex nav'], ['known route navigation', 'unimplemented /forum /blog /about /careers /api /help /shipping /guides /get-started /add-release /terms /privacy /cookies expected Next404', 'no mobile dropdown alternative supplied'], ['no implied business capability for dead links'])
rule('DATA-MODEL', 'Users UUID PK, releases/artists/labels/genres/styles integer PK; releases link tracks, artists with roles, labels, genres, styles, formats; membership composite keys and cart uniqueness constrain duplicates. Comments table exists but no comment API or functional comment UI.',
     ['backend/app/models/release.py:22-133','backend/app/models/cart.py:12-28','backend/app/models/collection.py:12-25','backend/app/models/wantlist.py:12-25','backend/app/models/comment.py:12-30','backend/alembic/versions/7c69fa412e18_init_schema.py:21-235','backend/alembic/versions/c798e9346a24_add_genre_description.py:21-24'],
     ['migrated schema'], ['SQL relation declarations do not prove SQLite FK enforcement; engine has no PRAGMA listener', 'no mutation APIs for catalog, comments, profile or order cancellation'], ['UI interactions must not modify read-only catalog/comment entities'])
rule('RUNTIME', 'Original Next16.1.1/React19.2.3 frontend reads API_INTERNAL_URL first and no-store catalog fetches; backend settings default SQLite and 24h JWT. Actual runtime manifest controls versions/ports, not conflicting README values.',
     ['frontend/package.json:1-30','frontend/src/lib/api.ts:1-26','frontend/src/lib/backend.ts:3-22','backend/app/core/config.py:6-32','backend/app/main.py:11-26','ports.json:1-8','start_servers.sh:15-37'],
     ['correct frontend/backend deployment'], ['SQL session closes on every request', 'no database writes from public reads', 'external Unsplash image failures separate from local business correctness', 'generic proxy forwards explicit Authorization but does not attach cookie JWT; dedicated account proxies do'], ['do not expose JWT/password hashes in evidence'])

def dump(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

dump('rules.json', rules)
review=[]
excluded={'task_instructions.json','scripts/generate_task_instructions.py','scripts/linear_sync.py','scripts/smoke_check.sh'}
for p in sorted(SRC.rglob('*')):
    if not p.is_file() or any(x in p.parts for x in ('.git','node_modules','.next','__pycache__','.venv')): continue
    rel=p.relative_to(SRC).as_posix()
    if rel in excluded:
        review.append({'path':rel,'status':'excluded','reason':'upstream tasks/answers, external sync, or smoke test; not learner input'}); continue
    refs=[r['id'] for r in rules if any(s.startswith(rel+':') for s in r['source_refs'])]
    if p.suffix in ('.ico','.svg'):
        status='asset_inventory_only'; summary='Static decorative asset; no business semantics inferred.'
    elif rel.endswith('package-lock.json'):
        status='dependency_metadata_inspected'; summary='Lock metadata only; individual dependency implementation not reviewed.'
    else:
        status='read'; summary=('Source supports '+', '.join(refs)) if refs else 'Supporting type/export/config/proxy; no independent business rule beyond linked module behavior.'
    review.append({'path':rel,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'lines':len(p.read_text(encoding='utf-8',errors='replace').splitlines()),'status':status,'summary':summary,'rule_ids':refs})
summaries={
 'backend/app/db/seed.py':'Reviewed seed control flow: destructive table clearing, 30 users, 220 generated plus DSOTM release, 24 initial DSOTM offers, memberships/comments and historical orders; seeded orders do not mark listings sold. Faker/random seeded but UUID/time/bcrypt remain variable.',
 'backend/app/api/router.py':'Includes auth/account/catalog/marketplace at root; healthz returns ok. No API router for comments, catalog mutation, order history or profile editing.',
 'backend/app/api/deps.py':'OAuth2 bearer dependency decodes JWT, requires UUID sub and existing user; distinguishes malformed/expired token and missing user.',
 'backend/app/services/auth.py':'bcrypt UTF-8 hashes/checks; JWT sub/iat/exp using configured algorithm, secret and TTL; decode maps JOSE errors to ValueError.',
 'backend/app/db/session.py':'Engine uses pool_pre_ping and SQLite check_same_thread=False; no PRAGMA FK listener; sessions autocommit/autoflush false and always close.',
 'backend/app/db/base.py':'DeclarativeBase root shared by all ORM tables.',
 'backend/app/models/__init__.py':'Exports every ORM class so Alembic metadata includes catalog joins, comments, memberships, listings, cart and orders.',
 'backend/app/core/logging.py':'basicConfig INFO timestamp/level/logger/message; no middleware that alters transaction behavior.',
 'backend/alembic/env.py':'Requires DATABASE_URL or SQLALCHEMY_URL; imports models metadata and runs offline/online migrations with compare_type.',
 'backend/alembic.ini':'Alembic script path and logging; deliberately unusable placeholder URL superseded by env.py.',
 'backend/alembic/script.py.mako':'Migration template only, upgrade/downgrade placeholders; no application branch.',
 'frontend/src/app/layout.tsx':'Global header, consent banner, page children, footer; en HTML and Discogs metadata.',
 'frontend/src/app/login/page.tsx':'Force-dynamic Suspense shell for LoginClient; Loading fallback.',
 'frontend/src/app/cart/page.tsx':'Force-dynamic Suspense shell for CartClient; Loading fallback.',
 'frontend/src/lib/types.ts':'Frontend release cards/home/genre types match display data, not a state transition model.',
 'frontend/src/app/globals.css':'Tailwind import, Arial/Helvetica font and white .page background only.',
 'frontend/src/components/ReleaseCard.tsx':'Clickable /release/id card with optional Unsplash image and artist text; year accepted but not rendered.',
 'frontend/package-lock.json':'Inspected root lockfile metadata and top-level exact Next/React dependencies; did not review third-party package implementations.',
 'frontend/README.md':'Generic create-next-app development documentation; runtime truth taken from actual config instead.',
 'README.md':'Deployment/SDK documentation contains backend port differing from ports.json; do not infer active endpoint solely from README.',
 'website_description.md':'Screenshot-derived desired functionality is aspirational and broader than implementation; source implementation takes precedence.',
 '.env.example':'Public example env values only; configured ports can differ from defaults. No actual .env or private secrets read.',
 'ports.json':'Declares backend12138/frontend12093; adapter public contract independently declares deployed UI12042.',
 'docker-compose.yml':'Postgres16 database-only service with persistence and healthcheck; local experiment uses separate SQLite adapter.',
 'Dockerfile':'Python3.11+Node22 multistage packaging, package installation and optional frontend build; port env12138/12093.',
 'backend/Dockerfile':'Python3.11 uvicorn app.main:app, default8000 differs from local adapter.',
 'frontend/Dockerfile':'Node22 Next development server3000; differs from production adapter execution.',
 'backend/requirements.txt':'Unpinned FastAPI/SQLAlchemy/Alembic/Pydantic/auth/Faker/http dependencies; installed versions require runtime manifest.',
 'frontend/next.config.ts':'Unsplash image allowlist and /api wildcard rewrite to localhost12138/api; filesystem route precedence must be observed.',
 'frontend/tsconfig.json':'Strict TS bundler config and @/* path alias; no business logic.',
 'frontend/postcss.config.mjs':'Tailwind PostCSS plugin only.',
 'frontend/eslint.config.mjs':'Next recommended lint configs and generated-dir ignores only.',
 'frontend/.gitignore':'Generated/dependency/env/cert/debug files ignored; no runtime behavior.',
 '.gitignore':'Dependency/data/env/cache exclusions; no runtime behavior.',
 'sdk/python/discogs_sdk/client.py':'httpx client API wrappers for auth/catalog/membership/cart/checkout; explicit bearer property. SDK does not bypass generic proxy query loss; not used for UI execution.',
 'sdk/python/discogs_sdk/__init__.py':'Exports DiscogsClient only.',
 'sdk/python/pyproject.toml':'Hatchling package metadata, Python>=3.10 and httpx dependency.',
 'sdk/python/README.md':'Public API SDK usage description; no UI completion evidence.',
}
for item in review:
    rel=item['path']
    if item['status']=='excluded':continue
    if rel in summaries:item['summary']=summaries[rel]
    elif rel.startswith('frontend/src/app/api/'):
        item['summary']='Reviewed this exact Next route: request method/body/id forwarding through backendFetch, response status/body propagation; auth cookie translation is in lib/backend.ts. '+item['summary']
    elif rel.startswith('backend/app/models/'):
        item['summary']='Reviewed mapped columns, nullability, keys, relationships and cascade declarations for '+Path(rel).stem+'; schema declarations alone do not prove live SQLite FK enforcement. '+item['summary']
    elif rel.startswith('backend/app/schemas/'):
        item['summary']='Reviewed '+Path(rel).stem+' Pydantic input defaults/constraints and response fields; '+item['summary']
dump('source_review.json',{'source_root':str(SRC),'claim':'Core frontend/backend implementation reviewed; inventory-only and metadata-only entries distinguished. Read is evidence of review, not proof of full semantic or browser coverage.','files':review})
dump('provenance.json',{'model':'gpt-6.1-sol','context':'independent source-visible phase1 Solar author; fork_turns=none','parent_version':None,'old_model_read':False,'allowed_inputs':['AGENTS.md','实验方案.md','研究目标.md','full upstream implementation/config/schema/migrations','public adapter_contract.md','public cases.json','harness/SCRIPT_CONTRACT.md','current experiment PROTOCOL.md','generic checks.py and contract.py'],'excluded_inputs':['evaluator.py','private evaluators/oracles','historical results/test answers','upstream task_instructions.json','task-generation scripts'],'access_isolation':'independent context only; no OS sandbox claimed','business_execution_count':0,'database_mutations_by_author':0,'script_contract':'harness/SCRIPT_CONTRACT.md protocol2','source_review_manifest':'source_review.json','token_usage':None,'billing':None})
lines=['# Discogs 白盒规则书 pw-v001','','作者：独立 gpt-6.1-sol。此版是源码支持的第一阶段模型；所有真实浏览器分支均待验证。未读取旧模型、独立评估器、私有 oracle 或历史成绩。业务动作执行次数为零。','','对象关系：User 拥有 CollectionItem/WantlistItem、CartItem、MarketplaceListing、Order；Release 连接艺术家、标签、曲目、风格和流派。CartItem 指向 listing；OrderItem 固化成交价和数量。对象 ID 与 URL/定位映射须由原生 Playwright 保留可检查证据。','','规则来源为下面的源码行引用；完整结构与逐条检查 ID 见 rules.json，文件哈希和阅读范围见 source_review.json。只有浏览器执行并经独立检查的分支才可提升状态；不得将有限任务通过写成全站覆盖。','']
for r in rules:
    lines += ['## '+r['id'], '',r['statement'],'','- 接口：'+r['interface'],'- 前置：'+'；'.join(r['preconditions']),'- 分支：'+'；'.join(r['branches']),'- 不应发生：'+'；'.join(r['forbidden_side_effects']),'- 源码：'+'；'.join(r['source_refs']),'- 状态：源码支持，浏览器待验证。','']
lines+=['## 执行与修正约定','','每步先记录规则 ID、目标对象、预期分支和检查项；确认目标唯一性，scroll_into_view_if_needed，执行原生 Playwright 操作，固定超时等待，回读 DOM/URL/协议允许响应并截图。失败分为定位、时序、实现、业务矛盾和无法确认；无法确认不得成功。规则作者的断言只用于运行监督，最终正确性由独立评估决定。','','源码发现的疑点须保留：卖家搜索代理丢 query、重复会员计数漂移、无库存数量约束、API PATCH nullable 与数据库非空冲突、SQLite FK enforcement 未开启、decade 表达式数据库依赖。网页导航到后端错误时 Next 的最终页面形态仍未知。','','全站能力边界：不存在注册 UI、移除收藏/想要 UI、编辑 listing UI、订单历史 UI、评论写入、目录编辑或 newsletter 订阅功能。不能通过 API 或页面内注入绕过缺失 UI 后宣称 UI 完成。']
(OUT/'rulebook.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
