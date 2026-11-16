"""Basic concurrency benchmark. Prefer real load tests and a stable GPU environment for meaningful results."""
import argparse,asyncio,time,json,statistics
import httpx
p=argparse.ArgumentParser();p.add_argument('--requests',type=int,default=20);p.add_argument('--concurrency',type=int,default=5);a=p.parse_args()
sem=asyncio.Semaphore(a.concurrency)
async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        async def run(i):
            async with sem:
                st=time.perf_counter();r=await c.post('http://localhost:8000/v1/chat/completions',headers={'x-api-key':'local-demo-key'},json={'messages':[{'role':'user','content':f'Explain binary search example {i}'}]});r.raise_for_status();return 1000*(time.perf_counter()-st)
        t=time.perf_counter();lat=await asyncio.gather(*(run(i) for i in range(a.requests)))
        xs=sorted(lat)
        print(json.dumps({'requests':len(xs),'throughput_rps':len(xs)/(time.perf_counter()-t),'latency_p95_ms':xs[max(0,int(.95*len(xs))-1)],'model_backend':'check /health; mock mode is NOT model performance'},indent=2))
asyncio.run(main())
