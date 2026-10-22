def run(h):
    read = {'disposition':'accepted','effects':{'persistent_state_changed':False,'affected_record_count':0},'ui_claims':[],'unknowns':[]}
    frozen = {'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['Only authenticated additions for release 221 were tested.']}
    h.expect(read, 'Open previously inspected target release after whole-task prediction is frozen')
    h.page.goto(h.origin + '/release/1')
    if h.page.get_by_role('button',name='Account',exact=True).count() != 1:
        h.note('Authentication not confirmed; no business write attempted')
        return
    title = h.page.get_by_text('Walker Quartet - Business-focused directional knowledgebase',exact=True)
    if title.count() != 1 or not title.is_visible():
        h.note('Target identity not confirmed; no business write attempted')
        return
    h.note('Previous script timed out at nonexistent main h1 before any write. Corrected to exact currently observed text.')
    add = h.page.get_by_role('button',name='Add to Collection',exact=True)
    if add.count() != 1 or not add.is_visible() or not add.is_enabled():
        h.note('Implementation/locator precondition failed; no business write attempted')
        return
    h.expect(frozen, 'Single authorized collection addition for release 1; frozen model has no supported prediction for this release')
    add.click()
    print(h.observe('collection-add-immediate'))
    print(h.network())
    h.expect(read, 'Confirm stored membership by opening collection after single click')
    h.page.goto(h.origin + '/me/collection')
    print(h.observe('collection-after-fresh-navigation'))
    target = h.page.locator('main a[href="/release/1"]')
    print({'target_collection_link_count':target.count(),'target_collection_texts':target.all_text_contents()})
    h.note('Current-task UI readback only. Frozen package remains unchanged; unknown prediction is not a business counterexample.')
