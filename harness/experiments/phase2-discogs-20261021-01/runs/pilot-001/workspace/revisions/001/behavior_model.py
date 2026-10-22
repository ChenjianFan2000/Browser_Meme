"""Retrospective initial checkpoint: observations 1–3 only, no business effects learned."""
def predict(observation, intent):
    return {"disposition":"unknown", "effects":{"persistent_state_changed":None,"affected_record_count":None}, "ui_claims":[], "unknowns":["This checkpoint discovered the home and login DOM only; business behavior is untested."]}
