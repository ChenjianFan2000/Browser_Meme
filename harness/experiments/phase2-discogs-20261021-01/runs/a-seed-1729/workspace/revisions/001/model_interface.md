# Retrospective checkpoint interface

Only calls001-006 support this checkpoint. See rules.json for bounded claims and
actual evidence references. predict takes observation and intent dicts. Supported
operations are auth.sign_in (login page with supplied valid fixture credentials)
and wantlist.add for release221, authenticated, with memberships.wantlist=false.
All other contexts return unknown. Later repeat/cart/checkout findings belong to
revision002 and must not be attributed to this checkpoint.

Require account_scope="supplied_fixture" for accepted predictions.
