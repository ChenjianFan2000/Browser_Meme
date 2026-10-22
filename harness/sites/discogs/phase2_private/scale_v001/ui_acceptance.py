"""Same frozen independent30 UI acceptance, explicitly admitted extra runtime."""
import argparse
import os
from urllib.parse import urlparse
from management import PRIVATE, EXTRA, PARENT, evaluator, load_file

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=EXTRA,required=True);args=p.parse_args()
    worker=EXTRA[args.worker]
    os.environ['BM_DISCOGS_PHASE2_RUNTIME']=str(PARENT)
    module=load_file('scale_original_ui_acceptance',PRIVATE/'check_ui_readiness.py')
    module.e=evaluator(worker['runtime'])
    module.BASE='http://127.0.0.1:'+str(worker['frontend_port'])
    original_attach=module.e.attach_ui
    class AliasedResponse:
        def __init__(self,response): self.response=response
        @property
        def url(self):
            parsed=urlparse(self.response.url)
            return parsed._replace(netloc='127.0.0.1:12042').geturl() if parsed.hostname in {'127.0.0.1','localhost'} and parsed.port==worker['frontend_port'] else self.response.url
        def __getattr__(self,name):return getattr(self.response,name)
    class AliasedPage:
        def __init__(self,page):self.page=page
        def on(self,event,callback):
            return self.page.on(event,lambda response:callback(AliasedResponse(response))) if event=='response' else self.page.on(event,callback)
    # Same origin normalization as original abc attach_ui, extended to d..l.
    # Original response/status/request body and original scoring functions unchanged.
    module.e.attach_ui=lambda page:original_attach(AliasedPage(page))
    os.environ['BM_PRIVATE_UI_RUN']='scale-ui-acceptance-002'
    module.main()
    module.e.reset_learning(0)

if __name__=='__main__':main()
