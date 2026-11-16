from gateway.core import SlidingLimiter,price,percentile,mock_reply,cache_key
from fastapi.testclient import TestClient
from gateway.app import app

def test_rate_limiter_window():
    t=[0.]
    l=SlidingLimiter(limit=2,window=60,clock=lambda:t[0])
    assert l.allow('u') and l.allow('u') and not l.allow('u')
    t[0]=61
    assert l.allow('u')

def test_price_and_metrics():
    assert price(1_000_000,1_000_000,2,5)==7
    assert percentile([1,2,3,4,5],.95)==5
    assert cache_key({'a':1})==cache_key({'a':1})

def test_mock_api_response(monkeypatch):
    monkeypatch.delenv('VLLM_URL',raising=False)
    with TestClient(app) as client:
        r=client.post('/v1/chat/completions',json={'model':'demo','messages':[{'role':'user','content':'Hello world'}]},headers={'x-api-key':'local-demo-key'})
        assert r.status_code==200 and 'MOCK MODE' in r.json()['choices'][0]['message']['content']
