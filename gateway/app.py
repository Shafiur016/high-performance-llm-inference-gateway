import os,json,time,uuid,asyncio,logging
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
from gateway.core import SlidingLimiter,estimate_tokens,price,percentile,mock_reply,cache_key

logging.basicConfig(level=logging.INFO)
log=logging.getLogger('inference-gateway')
limiter=SlidingLimiter(int(os.getenv('RATE_PER_MINUTE','30')))
metrics={'latencies_ms':[],'ttft_ms':[],'requests':0,'errors':0,'estimate_usd':0.0,'cache_hits':0}
app=FastAPI(title='LLM Inference Gateway',version='0.1.0')

class Message(BaseModel):
    role:str=Field(pattern='^(system|user|assistant)$')
    content:str=Field(min_length=1,max_length=10000)
class Completion(BaseModel):
    model:str=Field(default_factory=lambda:os.getenv('MODEL_NAME','demo-model'))
    messages:list[Message]=Field(min_length=1,max_length=30)
    stream:bool=False
    temperature:float=Field(default=0,ge=0,le=2)
    max_tokens:int=Field(default=256,ge=1,le=2048)

def authorize(x_api_key:str|None=Header(None)):
    if x_api_key!=os.getenv('GATEWAY_API_KEY','local-demo-key'):raise HTTPException(401,'Invalid gateway API key')
    if not limiter.allow(x_api_key):raise HTTPException(429,'Rate limit exceeded')

@app.get('/health')
def health():return {'status':'ok','backend':'vllm' if os.getenv('VLLM_URL') else 'mock'}

@app.get('/metrics',dependencies=[Depends(authorize)])
def stats():
    return {'requests':metrics['requests'],'errors':metrics['errors'],'latency_p95_ms':percentile(metrics['latencies_ms']),'ttft_p95_ms':percentile(metrics['ttft_ms']),'approx_cost_usd':metrics['estimate_usd'],'cache_hits':metrics['cache_hits']}

@app.post('/v1/chat/completions',dependencies=[Depends(authorize)])
async def chat(req:Completion):
    started=time.perf_counter();metrics['requests']+=1
    body=req.model_dump();url=os.getenv('VLLM_URL','').rstrip('/')
    # Do not cache stream mode or temperature > 0: those responses may not be deterministic.
    cache=None
    if url and not req.stream and req.temperature==0 and os.getenv('REDIS_URL'):
        try:
            from redis.asyncio import from_url
            cache=from_url(os.environ['REDIS_URL'],decode_responses=True)
            v=await cache.get(cache_key(body))
            if v:
                metrics['cache_hits']+=1
                await cache.aclose()
                return json.loads(v)
        except Exception as e:
            log.warning('Redis cache unavailable: %s',str(e));cache=None
    if not url:
        msg=mock_reply([m.model_dump() for m in req.messages]);inp=estimate_tokens(' '.join(m.content for m in req.messages));out=estimate_tokens(msg)
        response={'id':'mock-'+uuid.uuid4().hex,'object':'chat.completion','model':'mock-not-llm','choices':[{'index':0,'message':{'role':'assistant','content':msg},'finish_reason':'stop'}],'usage':{'prompt_tokens':inp,'completion_tokens':out,'total_tokens':inp+out}}
        elapsed=(time.perf_counter()-started)*1000;metrics['latencies_ms'].append(elapsed);metrics['ttft_ms'].append(elapsed)
        if not req.stream:return response
        async def demo():
            for word in msg.split(' '):
                delta={'choices':[{'delta':{'content':word+' '},'index':0,'finish_reason':None}],'object':'chat.completion.chunk'}
                yield 'data: '+json.dumps(delta)+'\n\n'
                await asyncio.sleep(0.02)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(demo(),media_type='text/event-stream')
    headers={'Authorization':'Bearer '+os.getenv('VLLM_API_KEY','local')}
    if req.stream:
        async def proxy():
            first=True
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream('POST',url+'/chat/completions',json=body,headers=headers) as resp:
                        if resp.status_code>=400:
                            yield 'data: '+json.dumps({'error':f'Upstream returned {resp.status_code}'})+'\n\n';return
                        async for line in resp.aiter_lines():
                            if first and line.startswith('data:'):
                                metrics['ttft_ms'].append((time.perf_counter()-started)*1000);first=False
                            if line:yield line+'\n\n'
            except Exception as e:
                metrics['errors']+=1;yield 'data: '+json.dumps({'error':'Upstream streaming unavailable'})+'\n\n'
            finally:metrics['latencies_ms'].append((time.perf_counter()-started)*1000)
        return StreamingResponse(proxy(),media_type='text/event-stream')
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r=await client.post(url+'/chat/completions',json=body,headers=headers)
            r.raise_for_status();result=r.json()
        usage=result.get('usage',{})
        metrics['estimate_usd']+=price(usage.get('prompt_tokens',0),usage.get('completion_tokens',0),float(os.getenv('INPUT_USD_PER_M',0)),float(os.getenv('OUTPUT_USD_PER_M',0)))
        metrics['latencies_ms'].append((time.perf_counter()-started)*1000)
        if cache:
            try:await cache.setex(cache_key(body),300,json.dumps(result));await cache.aclose()
            except Exception:pass
        return result
    except (httpx.HTTPError,ValueError) as e:
        metrics['errors']+=1;log.error('Upstream request failed: %s',str(e))
        raise HTTPException(502,'Inference backend unavailable')
