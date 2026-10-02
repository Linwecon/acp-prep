"""Fill verified chapter quotas in bounded rounds, preserving all checkpoints."""
import argparse
import json
import govern_bank as g

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start-round',type=int,default=2)
    p.add_argument('--max-rounds',type=int,default=15)
    p.add_argument('--workers',type=int,default=24)
    p.add_argument('--target',type=int,default=100)
    p.add_argument('--factor',type=float,default=4)
    args=p.parse_args()
    cfg=g.qc.load_llm_cfg(); sec=g.cc.extract_chapter_sections(100000)
    prof=(g.qc.load_profiles() or {}).get('profiles',{})
    excluded={r['qid'] for r in json.loads((g.OUT/'audit.json').read_text(encoding='utf-8'))['rows'] if r['action']=='review'}
    for n in range(args.start_round,args.start_round+args.max_rounds):
        qs=g.cc.bank_questions(g.cc.load_bank())
        counts={ch:sum(q['chapter']==ch and q['qid'] not in excluded for q in qs) for ch in sec}
        gaps={ch:max(0,args.target-v) for ch,v in counts.items()}
        g.save(g.OUT/'completion_progress.json',{'round':n,'eligible':counts,'gaps':gaps,'complete':not any(gaps.values())})
        print('ROUND',n,'remaining',sum(gaps.values()),'counts',counts,flush=True)
        if not any(gaps.values()): break
        opts=argparse.Namespace(workers=args.workers,batch=6,target=args.target,round=n,factor=args.factor)
        try:
            g.generate(opts,cfg,sec,prof)
        except g.qc.ModelAccessError as e:
            g.save(g.OUT/'completion_progress.json',{'round':n,'eligible':counts,'gaps':gaps,'complete':False,'blocked':str(e)})
            g.report(opts,cfg,sec,prof)
            print(str(e),flush=True)
            return 2
        g.merge_drafts(opts,cfg,sec,prof)
        g.report(opts,cfg,sec,prof)
    g.report(args,cfg,sec,prof)

if __name__=='__main__': raise SystemExit(main() or 0)
