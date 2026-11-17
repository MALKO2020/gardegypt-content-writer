#!/usr/bin/env python3
"""GardEgypt scoped task worker. Writes require --apply and explicit job approval."""
import argparse, base64, csv, html, json, os, re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MODE = "content_writer"
ROOT = Path(__file__).resolve().parent
class Blocked(Exception): pass
def stop(msg): raise Blocked(msg)

def load(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data,list):
        if len(data)!=1: stop("Use one task per JSON file.")
        data=data[0]
    if not isinstance(data,dict) or data.get("template"): stop("Fill a task JSON; templates are not executable.")
    return data

def api(method,path,payload=None):
    base=os.getenv("GARD_EGYPT_SITE_URL","").rstrip("/")
    user=os.getenv("GARD_EGYPT_WP_USER","")
    password=os.getenv("GARD_EGYPT_WP_APP_PASSWORD","").replace(" ","")
    if not base.startswith("https://") or not user or not password:
        stop("Missing HTTPS WordPress credentials in GitHub Actions secrets.")
    body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
    headers={"Authorization":"Basic "+base64.b64encode((user+":"+password).encode()).decode(),"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    req=Request(base+"/wp-json/wp/v2/"+path.lstrip("/"),data=body,headers=headers,method=method)
    try:
        with urlopen(req,timeout=35) as res: return json.loads(res.read().decode() or "{}")
    except HTTPError as e: stop("WordPress REST HTTP %s: %s"%(e.code,e.read().decode("utf-8","replace")[:800]))
    except URLError as e: stop("WordPress connection failed: "+str(e.reason))

def identity(job):
    kind=job.get("post_type","page")
    if kind not in ("page","post"): stop("post_type must be page or post.")
    try: pid=int(job.get("id",0))
    except (TypeError,ValueError): pid=0
    slug=str(job.get("expected_slug",""))
    if pid<1 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*",slug): stop("Provide a positive ID and exact expected_slug.")
    item=api("GET",f"{kind}s/{pid}?context=edit")
    if item.get("slug")!=slug: stop("Identity check failed: current slug differs.")
    return kind,item

class Scan(HTMLParser):
    def __init__(self): super().__init__(); self.h1=0; self.h2=0; self.img=0; self.noalt=0; self.links=0; self.words=[]
    def handle_starttag(self,t,a):
        a=dict(a)
        if t=="h1": self.h1+=1
        if t=="h2": self.h2+=1
        if t=="img":
            self.img+=1
            if not a.get("alt","").strip(): self.noalt+=1
        if t=="a" and (a.get("href","").startswith("/") or "bodyguardegy.com" in a.get("href","")): self.links+=1
    def handle_data(self,d): self.words.extend(re.findall(r"\w+",d,re.UNICODE))

def run(j,apply):
    if MODE=="page_creator":
        title=str(j.get("title","")).strip(); slug=str(j.get("slug","")).strip()
        if not title or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*",slug): stop("Provide title and a safe slug.")
        if api("GET","pages?"+urlencode({"slug":slug,"status":"publish,draft,pending,private"})): stop("Slug already exists; refusing duplicate.")
        data={"title":title,"slug":slug,"content":j.get("content",""),"status":"draft"}
        if j.get("language") in ("ar","en"): data["lang"]=j["language"]
        if not apply or j.get("approved_for_draft") is not True: return {"status":"preview_draft","slug":slug}
        p=api("POST","pages",data); return {"status":"created_draft","id":p.get("id"),"slug":p.get("slug"),"url":p.get("link")}

    if MODE=="content_writer":
        kind,p=identity(j); data={k:j[k] for k in ("title","content","excerpt","meta") if k in j}
        if not data: stop("No content fields supplied.")
        if "meta" in data:
            allowed={"rank_math_title","rank_math_description","rank_math_focus_keyword","rank_math_canonical_url"}
            if not isinstance(data["meta"],dict) or not set(data["meta"]).issubset(allowed): stop("Unsupported Rank Math meta field.")
        if not apply or j.get("approved") is not True: return {"status":"preview_update","id":p["id"],"fields":list(data)}
        q=api("POST",f"{kind}s/{p['id']}",data); return {"status":"updated","id":q.get("id"),"slug":q.get("slug")}

    if MODE=="image_manager":
        kind,p=identity(j)
        try: mid=int(j.get("media_id",0))
        except (TypeError,ValueError): mid=0
        alt=str(j.get("alt_text","")).strip()
        if mid<1 or not alt: stop("Provide existing media_id and descriptive alt_text.")
        media=api("GET",f"media/{mid}?context=edit")
        if media.get("media_type")!="image": stop("media_id is not an image.")
        if not apply or j.get("approved") is not True: return {"status":"preview_image_link","post_id":p["id"],"media_id":mid}
        api("POST",f"media/{mid}",{"alt_text":alt})
        q=api("POST",f"{kind}s/{p['id']}",{"featured_media":mid})
        return {"status":"image_linked","post_id":q.get("id"),"media_id":mid}

    if MODE=="content_reviewer":
        kind,p=identity(j); raw=p.get("content",{}).get("rendered",""); title=html.unescape(p.get("title",{}).get("rendered",""))
        s=Scan(); s.feed(raw)
        checks={"one_h1":s.h1==1,"has_h2":s.h2>0,"title_present":bool(title.strip()),"300_words":len(s.words)>=300,"images_have_alt":s.noalt==0,"has_internal_link":s.links>0}
        return {"status":"read_only_review","id":p["id"],"slug":p["slug"],"checks":checks,"metrics":{"h1":s.h1,"h2":s.h2,"words":len(s.words),"images":s.img,"missing_alt":s.noalt,"internal_links":s.links},"automated_pass":all(checks.values()),"note":"Structural checks only; human review is required for facts and editorial quality."}

    if MODE=="publisher":
        kind,p=identity(j)
        if p.get("status")!="draft": stop("Publisher only publishes drafts.")
        if j.get("review_passed") is not True or j.get("approved_for_publish") is not True: return {"status":"held","reason":"Explicit review and publish approvals are required."}
        if not apply: return {"status":"preview_publish","id":p["id"],"slug":p["slug"]}
        q=api("POST",f"{kind}s/{p['id']}",{"status":"publish"})
        return {"status":"published","id":q.get("id"),"slug":q.get("slug"),"url":q.get("link")}

    if MODE=="redirects":
        rows=j.get("redirects")
        if not isinstance(rows,list) or not rows: stop("Provide a non-empty redirects list.")
        clean=[]
        for r in rows:
            src=str(r.get("source","")); dst=str(r.get("destination","")); typ=str(r.get("type",""))
            if not src.startswith("/") or src.startswith("//") or "?" in src or "#" in src: stop("Each source must be a local path.")
            if typ not in ("301","410"): stop("Allowed types are 301 and 410; 401 is not a removal code.")
            if typ=="301" and not dst.startswith("/"): stop("301 destination must be a local path.")
            if typ=="410" and dst: stop("410 must not have a destination.")
            match=r.get("matching","exact"); status=r.get("status","active")
            if match not in ("exact","contains","start","end","regex") or status not in ("active","inactive"): stop("Invalid matching or status.")
            clean.append({"id":"","source":src,"matching":match,"destination":dst,"type":typ,"category":r.get("category","GardEgypt"),"status":status,"ignore":r.get("ignore","")})
        if not apply or j.get("approved") is not True: return {"status":"preview_rankmath_csv","rules":clean}
        out=ROOT/"rankmath-import.csv"
        with out.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=["id","source","matching","destination","type","category","status","ignore"]); w.writeheader(); w.writerows(clean)
        return {"status":"csv_ready_no_live_change","file":str(out),"rules":len(clean)}
    stop("Unknown worker mode.")

def main():
    a=argparse.ArgumentParser(); a.add_argument("--input",required=True); a.add_argument("--apply",action="store_true"); a.add_argument("--report",default="report.json"); args=a.parse_args()
    try:
        result=run(load(args.input),args.apply)
        Path(args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (Blocked,ValueError,KeyError) as e:
        print(json.dumps({"status":"blocked_or_failed","mode":MODE,"error":str(e)},ensure_ascii=False),file=sys.stderr); sys.exit(2)
if __name__=="__main__": main()
