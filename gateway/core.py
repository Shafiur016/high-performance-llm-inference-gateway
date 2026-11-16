"""Backend-independent limiter and instrumentation helpers."""
import math,time,hashlib,json
from collections import deque

class SlidingLimiter:
    def __init__(self,limit=30,window=60,clock=time.monotonic):
        self.limit=limit;self.window=window;self.clock=clock;self.buckets={}
    def allow(self,key):
        now=self.clock();q=self.buckets.setdefault(key,deque())
        while q and q[0]<=now-self.window:q.popleft()
        if len(q)>=self.limit:return False
        q.append(now);return True

def estimate_tokens(text):return max(1,len(text)//4)

def price(input_tokens,output_tokens,input_usd_m=0,output_usd_m=0):
    return round((input_tokens*input_usd_m+output_tokens*output_usd_m)/1_000_000,8)

def percentile(xs,p=.95):
    if not xs:return None
    arr=sorted(xs);return arr[min(len(arr)-1,max(0,math.ceil(len(arr)*p)-1))]

def mock_reply(messages):
    text=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
    return f'[MOCK MODE — NOT AN LLM] Echo: {text[:160]}'

def cache_key(payload):return 'completion:'+hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
