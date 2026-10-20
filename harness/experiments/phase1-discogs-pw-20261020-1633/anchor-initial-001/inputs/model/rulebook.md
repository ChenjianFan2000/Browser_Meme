# Discogs 白盒规则书 pw-v001

作者：独立 gpt-6.1-sol。此版是源码支持的第一阶段模型；所有真实浏览器分支均待验证。未读取旧模型、独立评估器、私有 oracle 或历史成绩。业务动作执行次数为零。

对象关系：User 拥有 CollectionItem/WantlistItem、CartItem、MarketplaceListing、Order；Release 连接艺术家、标签、曲目、风格和流派。CartItem 指向 listing；OrderItem 固化成交价和数量。对象 ID 与 URL/定位映射须由原生 Playwright 保留可检查证据。

规则来源为下面的源码行引用；完整结构与逐条检查 ID 见 rules.json，文件哈希和阅读范围见 source_review.json。只有浏览器执行并经独立检查的分支才可提升状态；不得将有限任务通过写成全站覆盖。

## AUTH-LOGIN

Username or email login issues a bearer JWT on success; the UI stores it in an httpOnly sameSite=lax cookie and replaces the URL with next or /.

- 接口：native UI
- 前置：username_or_email and password supplied
- 分支：valid: 200 token / UI {ok:true}；unknown user or wrong password: 400 Invalid credentials, visible raw error, remain login
- 不应发生：no account, cart, order, catalog or membership changes；failed fresh login must not create authenticated session
- 源码：backend/app/api/auth.py:38-45；frontend/src/app/api/auth/login/route.ts:5-27；frontend/src/app/login/LoginClient.tsx:9-49
- 状态：源码支持，浏览器待验证。

## AUTH-GATE

All account mutations/reads require current user resolved from a valid JWT subject; UI 401 redirects preserve return target.

- 接口：native UI
- 前置：authenticated account operations
- 分支：missing bearer: framework 401；invalid/expired JWT: 401 Invalid or expired token；missing user: 401 User not found；anonymous collection click: login?next=/release/id; login does not replay collection POST；anonymous cart add: login returns to /cart?add=id, then retries add
- 不应发生：refusals change no business state
- 源码：backend/app/api/deps.py:13-31；frontend/src/components/ReleaseActions.tsx:23-36；frontend/src/app/cart/CartClient.tsx:38-79；frontend/src/app/me/collection/page.tsx:15-34；frontend/src/app/sell/page.tsx:46-61
- 状态：源码支持，浏览器待验证。

## AUTH-LOGOUT

Sign out clears the cookie then refreshes/pushes home; it does not invalidate JWT server-side.

- 接口：native UI
- 前置：cookie-backed UI session
- 分支：sign out: cookie expiry and home；Header treats cookie presence as signed in without validating it
- 不应发生：no business state mutations
- 源码：frontend/src/components/LogoutButton.tsx:10-26；frontend/src/app/api/auth/logout/route.ts:5-8；frontend/src/components/Header.tsx:9-11
- 状态：源码支持，浏览器待验证。

## AUTH-REGISTER

API registration validates schema and exact username/email uniqueness, hashes password, creates a user; there is no registration page.

- 接口：API only; not UI validation
- 前置：username length 3..50; valid email; password length 8..128; optional display_name <=120
- 分支：201 UserOut, no token；400 Username already taken；400 Email already registered；422 schema refusal
- 不应发生：no other users or business records change
- 源码：backend/app/api/auth.py:18-35；backend/app/schemas/user.py:9-18；backend/app/models/user.py:12-33
- 状态：源码支持，浏览器待验证。

## CAT-SEARCH

Search trims q, matches title or main artist using case-insensitive SQL substring pattern, sorts year descending/null last then title, limits 30; it does not search genre/style/label.

- 接口：native UI
- 前置：q string
- 分支：empty/whitespace: []；match: release cards；no match: empty grid without explicit no-result sentence；SQL %/_ act as wildcards
- 不应发生：no database changes
- 源码：backend/app/api/catalog.py:351-377；frontend/src/app/search/page.tsx:12-37；frontend/src/components/Header.tsx:22-36
- 状态：源码支持，浏览器待验证。

## CAT-DETAIL

Release detail returns joined metadata, ordered tracks and current global collection/want counts plus active listing count/minimum price.

- 接口：native UI
- 前置：integer release id
- 分支：exists: metadata, tracklist, optional notes and actions；missing: API 404 Release not found; apiGet throws; exact Next error UI pending
- 不应发生：read does not mutate tables
- 源码：backend/app/api/catalog.py:274-348；frontend/src/app/release/[id]/page.tsx:20-180
- 状态：源码支持，浏览器待验证。

## CAT-HOME

Home ranks most wanted (6), latest created (8), and highest order-item prices in last 31 days (6); promo tiles link home, featured banner links seeded title if available.

- 接口：native UI
- 前置：catalog accessible
- 分支：rankings data-dependent, ties not fully stable；newsletter Subscribe has no handler/form action; app store mockups are display only
- 不应发生：no newsletter subscription or database mutation from placeholder controls
- 源码：backend/app/api/catalog.py:82-174；frontend/src/app/page.tsx:10-178
- 状态：源码支持，浏览器待验证。

## CAT-GENRE

Genre overview includes alphabetic styles, most-collected and earliest-year cards, decade and contributor aggregates, recent-sales ranking. Its navigation links lead to text search, not true genre-filtered search.

- 接口：native UI
- 前置：existing slug
- 分支：known slug: overview；unknown: API 404 Genre not found; exact Next error UI pending；style/release/artist links are q text searches；artist tiles are placeholders
- 不应发生：no catalog/business mutations
- 源码：backend/app/api/catalog.py:177-271；frontend/src/app/genre/[slug]/page.tsx:48-191
- 状态：源码支持，浏览器待验证。

## MEM-COLLECTION

collection GET returns current user release cards; POST is idempotent; DELETE removes only current user membership and succeeds when absent. UI only exposes add and list, no remove control.

- 接口：native UI
- 前置：valid session；POST requires existing release
- 分支：GET 200 array, empty allowed；POST 200 {ok:true}, existing no-op；POST unknown release 404；DELETE 200 {ok:true} even absent；UI 401 login gate
- 不应发生：other users/membership kind and all catalog/cart/order/listing rows unchanged
- 源码：backend/app/api/account.py:41-81；backend/app/models/collection.py:12-25；frontend/src/app/me/collection/page.tsx:15-58；frontend/src/components/ReleaseActions.tsx:23-66
- 状态：源码支持，浏览器待验证。

## MEM-WANTLIST

wantlist GET returns current user release cards; POST is idempotent; DELETE removes only current user membership and succeeds when absent. UI only exposes add and list, no remove control.

- 接口：native UI
- 前置：valid session；POST requires existing release
- 分支：GET 200 array, empty allowed；POST 200 {ok:true}, existing no-op；POST unknown release 404；DELETE 200 {ok:true} even absent；UI 401 login gate
- 不应发生：other users/membership kind and all catalog/cart/order/listing rows unchanged
- 源码：backend/app/api/account.py:84-124；backend/app/models/wantlist.py:12-25；frontend/src/app/me/wantlist/page.tsx:15-58；frontend/src/components/ReleaseActions.tsx:23-66
- 状态：源码支持，浏览器待验证。

## MEM-UI-COUNT

Successful Add to Collection/Wantlist always increments its local component count, including duplicate POST no-op; the separate summary remains its server-rendered value until navigation/reload.

- 接口：native UI
- 前置：authenticated duplicate add
- 分支：first add: one durable membership；repeat add: local count +1 again; durable count unchanged；reload: counts recomputed from backend
- 不应发生：duplicates must not create another membership
- 源码：frontend/src/components/ReleaseActions.tsx:20-36；frontend/src/app/release/[id]/page.tsx:83-108；backend/app/api/account.py:65-74；backend/app/api/account.py:108-117
- 状态：源码支持，浏览器待验证。

## MKT-FILTER

Marketplace exposes only active listings for a release; text filters are exact equality, rating is minimum, sorting is price_asc/price_desc/newest with documented secondary keys.

- 接口：native UI
- 前置：valid release；sort enum; API limit 1..200 default50, offset>=0
- 分支：matching: total before pagination + rows；none: No listings match these filters.；unknown release 404；bad sort/nonnumeric rating/pagination 422 -> server page error；UI has no pagination or quantity control and renders at most default 50
- 不应发生：no state changes from filtering/sorting
- 源码：backend/app/api/marketplace.py:15-90；frontend/src/app/sell/release/[id]/page.tsx:18-173
- 状态：源码支持，浏览器待验证。

## CART-ADD

Add requires active listing and positive quantity; an existing user/listing row accumulates quantity capped at 99; a new row is not capped by the route. No stock or seller-self-purchase check exists.

- 接口：native UI
- 前置：valid session；listing id and integer quantity
- 分支：201 CartOut with totals；404 Listing not found for missing/inactive/sold；400 Quantity must be >= 1；422 invalid payload types；UI always adds one via /cart?add=id and replaces /cart；UI ignores non-401 add refusal then loads cart
- 不应发生：no order or stock decrement; no other users cart changes
- 源码：backend/app/api/account.py:161-179；backend/app/schemas/cart.py:29-31；backend/app/models/cart.py:12-28；frontend/src/app/cart/CartClient.tsx:57-79
- 状态：源码支持，浏览器待验证。

## CART-READ

Cart joins current listing price, calculates sum(price*cart quantity), returns currency USD, latest-added first. UI hides quantity and displays unit prices alongside total.

- 接口：native UI
- 前置：valid session
- 分支：200 CartOut including empty；empty UI message and Checkout disabled；same listing twice yields one visible row but doubled total
- 不应发生：read never creates orders or changes listing
- 源码：backend/app/api/account.py:127-158；frontend/src/app/cart/CartClient.tsx:97-160
- 状态：源码支持，浏览器待验证。

## CART-REMOVE

Remove deletes only the logged-in user cart row by cart_item_id, then UI reloads; absent/other-user IDs are successful no-ops.

- 接口：native UI
- 前置：valid session
- 分支：200 {ok:true}, item gone after reload；empty cart checkout disabled
- 不应发生：no listing/order changes; other users cart unchanged
- 源码：backend/app/api/account.py:182-186；frontend/src/app/cart/CartClient.tsx:120-150
- 状态：源码支持，浏览器待验证。

## CHECKOUT

Checkout snapshots current listing prices and cart quantities into one paid USD order, marks each entire listing sold, leaves listing.quantity unchanged, clears only buyer cart, commits once.

- 接口：native UI
- 前置：valid session；nonempty cart, every listing still active
- 分支：200 OrderOut with item price/quantity snapshots；400 Cart is empty；400 A listing in your cart is no longer available; session closes without commit, pending flushed order should roll back；UI reload then alert Checkout complete (order created).；UI has no order history/detail page
- 不应发生：no listing quantity decrement；no changes to unrelated listings/orders/cart/memberships/catalog；refusal must not leave partial order or sold statuses
- 源码：backend/app/api/account.py:189-229；backend/app/db/session.py:17-22；frontend/src/app/cart/CartClient.tsx:162-180；backend/app/models/order.py:12-40
- 状态：源码支持，浏览器待验证。

## SELL-CREATE

Authenticated seller creates active listing for existing release. Schema accepts arbitrary nonempty conditions, positive cents, three-character currency, origin 1..80, optional comments and qty1..99. UI fixes currency USD.

- 接口：native UI
- 前置：selected release in UI；valid session and schema
- 分支：201 {id}；404 Release not found；422 schema error, no new listing；UI create disabled when no selected or cents<=0; invalid qty still submits；UI price field represents cents, not dollars
- 不应发生：no modifications to existing listings or other business tables
- 源码：backend/app/api/account.py:263-285；backend/app/schemas/sell.py:6-15；frontend/src/app/sell/page.tsx:215-250
- 状态：源码支持，浏览器待验证。

## SELL-MANAGE

My Listings includes all own statuses sorted newest first; Deactivate is soft deletion (inactive), including already inactive/sold own rows. Missing/non-owned returns 404.

- 接口：native UI
- 前置：valid session; owned listing to deactivate
- 分支：GET 200 {items:[...]} omits comments；DELETE 200 {ok:true}, row retained and visible inactive；DELETE missing/non-owned 404 Listing not found
- 不应发生：no physical row deletion; no changes to other sellers listings or orders/cart
- 源码：backend/app/api/account.py:232-260；backend/app/api/account.py:302-309；frontend/src/app/sell/page.tsx:254-311
- 状态：源码支持，浏览器待验证。

## SELL-UPDATE

API PATCH updates explicitly supplied schema fields on owned listing; status permits active/inactive, even reactivating sold. Fields nullable in schema can reach non-null SQL columns and cause DB failure.

- 接口：API only; UI provides no edit/reactivate control
- 前置：valid session; own listing; schema-valid partial body
- 分支：200 {ok:true}；404 missing/non-owned；422 out-of-range or invalid status；explicit null non-null-column fields: potential SQL 500 rollback, browser unverified
- 不应发生：no other listing changes
- 源码：backend/app/api/account.py:288-299；backend/app/schemas/sell.py:18-25；backend/app/models/marketplace.py:21-31
- 状态：源码支持，浏览器待验证。

## SELL-SEARCH-PROXY

Seller search uses /api/backend/search?q=..., but generic proxy builds upstream URL from path only and drops query. Backend search requires q, so expected 422 prevents selection/creation through normal seller search.

- 接口：native UI
- 前置：original proxy route wins Next routing
- 分支：expected 422 missing q; visible JSON error; selected remains unset；if runtime routing differs record counterexample and revise; do not bypass UI with API/DOM injected state
- 不应发生：failed search must not create listing
- 源码：frontend/src/app/sell/page.tsx:95-109；frontend/src/app/api/backend/[...path]/route.ts:5-20；backend/app/api/catalog.py:351-354
- 状态：源码支持，浏览器待验证。

## UI-CONSENT

Accept All Cookies writes localStorage acceptance and hides banner; Cookie Settings has no handler.

- 接口：native UI
- 前置：banner visible in fresh storage
- 分支：accept: hidden, remains hidden on reload when storage works；storage unavailable: hide current mount but return later；settings: no implemented transition
- 不应发生：no backend business changes
- 源码：frontend/src/components/CookieBanner.tsx:5-40
- 状态：源码支持，浏览器待验证。

## UI-NAV

Desktop menus reveal on hover. Header has catalog search, cart, account and sell/genre links. Footer/community links mostly target unimplemented routes, social links are #.

- 接口：native UI
- 前置：desktop viewport for hidden md:flex nav
- 分支：known route navigation；unimplemented /forum /blog /about /careers /api /help /shipping /guides /get-started /add-release /terms /privacy /cookies expected Next404；no mobile dropdown alternative supplied
- 不应发生：no implied business capability for dead links
- 源码：frontend/src/components/Header.tsx:38-211；frontend/src/components/Footer.tsx:26-98
- 状态：源码支持，浏览器待验证。

## DATA-MODEL

Users UUID PK, releases/artists/labels/genres/styles integer PK; releases link tracks, artists with roles, labels, genres, styles, formats; membership composite keys and cart uniqueness constrain duplicates. Comments table exists but no comment API or functional comment UI.

- 接口：native UI
- 前置：migrated schema
- 分支：SQL relation declarations do not prove SQLite FK enforcement; engine has no PRAGMA listener；no mutation APIs for catalog, comments, profile or order cancellation
- 不应发生：UI interactions must not modify read-only catalog/comment entities
- 源码：backend/app/models/release.py:22-133；backend/app/models/cart.py:12-28；backend/app/models/collection.py:12-25；backend/app/models/wantlist.py:12-25；backend/app/models/comment.py:12-30；backend/alembic/versions/7c69fa412e18_init_schema.py:21-235；backend/alembic/versions/c798e9346a24_add_genre_description.py:21-24
- 状态：源码支持，浏览器待验证。

## RUNTIME

Original Next16.1.1/React19.2.3 frontend reads API_INTERNAL_URL first and no-store catalog fetches; backend settings default SQLite and 24h JWT. Actual runtime manifest controls versions/ports, not conflicting README values.

- 接口：native UI
- 前置：correct frontend/backend deployment
- 分支：SQL session closes on every request；no database writes from public reads；external Unsplash image failures separate from local business correctness；generic proxy forwards explicit Authorization but does not attach cookie JWT; dedicated account proxies do
- 不应发生：do not expose JWT/password hashes in evidence
- 源码：frontend/package.json:1-30；frontend/src/lib/api.ts:1-26；frontend/src/lib/backend.ts:3-22；backend/app/core/config.py:6-32；backend/app/main.py:11-26；ports.json:1-8；start_servers.sh:15-37
- 状态：源码支持，浏览器待验证。

## 执行与修正约定

每步先记录规则 ID、目标对象、预期分支和检查项；确认目标唯一性，scroll_into_view_if_needed，执行原生 Playwright 操作，固定超时等待，回读 DOM/URL/协议允许响应并截图。失败分为定位、时序、实现、业务矛盾和无法确认；无法确认不得成功。规则作者的断言只用于运行监督，最终正确性由独立评估决定。

源码发现的疑点须保留：卖家搜索代理丢 query、重复会员计数漂移、无库存数量约束、API PATCH nullable 与数据库非空冲突、SQLite FK enforcement 未开启、decade 表达式数据库依赖。网页导航到后端错误时 Next 的最终页面形态仍未知。

全站能力边界：不存在注册 UI、移除收藏/想要 UI、编辑 listing UI、订单历史 UI、评论写入、目录编辑或 newsletter 订阅功能。不能通过 API 或页面内注入绕过缺失 UI 后宣称 UI 完成。
