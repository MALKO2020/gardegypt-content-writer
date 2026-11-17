#!/usr/bin/env python3
"""Validate a GardEgypt job manifest only. WordPress writes are performed by the WP GitHub Bridge."""
import argparse, json, re, sys
from pathlib import Path
MODE="content_writer"
def require(ok,msg):
    if not ok: raise ValueError(msg)
def run(path):
    job=json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(job,dict),"job must be a JSON object")
    require(not job.get("template"),"template files cannot be submitted as jobs")
    require(isinstance(job.get("task_id"),str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{3,100}",job["task_id"])),"task_id is required and must be unique")
    if MODE=="page_creator":
        require(bool(str(job.get("title","")).strip()),"title is required")
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*",str(job.get("slug",""))),"slug is required")
        require(isinstance(job.get("content",""),str),"content must be text")
        approval=job.get("approved_for_draft") is True
    elif MODE in ("content_writer","image_manager","content_reviewer","publisher"):
        require(job.get("post_type","page") in ("page","post"),"post_type must be page or post")
        require(isinstance(job.get("id"),int) and job["id"]>0,"positive WordPress ID is required")
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*",str(job.get("expected_slug",""))),"expected_slug is required")
        if MODE=="content_writer":
            require(any(k in job for k in ("title","content","excerpt","meta")),"no update fields supplied")
            approval=job.get("approved") is True
        elif MODE=="image_manager":
            require(isinstance(job.get("media_id"),int) and job["media_id"]>0,"existing image media_id is required")
            require(bool(str(job.get("alt_text","")).strip()),"alt_text is required")
            approval=job.get("approved") is True
        elif MODE=="publisher":
            require(job.get("review_passed") is True,"review_passed approval is required")
            approval=job.get("approved_for_publish") is True
        else:
            approval=True
    elif MODE=="redirects":
        rows=job.get("redirects")
        require(isinstance(rows,list) and len(rows)>0,"redirects must be a non-empty list")
        seen=set()
        for r in rows:
            src=str(r.get("source","")); dst=str(r.get("destination","")); code=str(r.get("type",""))
            require(src.startswith("/") and not src.startswith("//") and "?" not in src and "#" not in src,"source must be a clean local path")
            require(src not in seen,"duplicate source in the same task"); seen.add(src)
            require(code in ("301","410"),"allowed status codes are 301 and 410; 401 is invalid")
            require((code=="301" and dst.startswith("/") and not dst.startswith("//")) or (code=="410" and dst==""),"301 needs local destination; 410 needs an empty destination")
            require(r.get("matching","exact") in ("exact","contains","start","end"),"unsupported matching type")
        approval=job.get("approved") is True
    else: raise ValueError("unknown worker role")
    print(json.dumps({"task_id":job["task_id"],"role":MODE,"validation":"ok","approval_present":approval,"execution":"WordPress Bridge polls and applies approved tasks"},ensure_ascii=False))
def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); a=p.parse_args()
    try: run(a.input)
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        print(json.dumps({"role":MODE,"validation":"blocked","error":str(e)},ensure_ascii=False),file=sys.stderr); sys.exit(2)
if __name__=="__main__": main()
