"""Anonymous single-video human evaluation using the general VLM 1–5 rubric."""
from __future__ import annotations
import argparse,csv,hashlib,json,mimetypes,re,secrets,sqlite3,uuid
from contextlib import closing
from datetime import UTC,datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE=Path(__file__).resolve().parent
METRICS={
 "IF":("指令遵循","成片是否充分、明确地满足提示词中的主体、事件、风格、情绪或叙事意图？仅评价提示词满足。"),
 "VQ":("编辑技术质量","成片是否保持可用、清晰且主体明确的视觉呈现？只评价剪辑引入或加剧的技术问题。"),
 "TC":("转场连续性","相邻片段边界是否自然、可读并保留意图？快速剪辑、景别或场景变化仅在破坏理解时扣分。"),
 "NC":("叙事连贯性","片段序列是否有可理解的组织、推进、重点和符合任务的收束？"),
}
PROTOCOL={"version":"likert-v1-general-vlm-rubric","metrics":METRICS,"scale":{"1":"严重不满足","2":"表现较弱","3":"基本可用","4":"表现良好","5":"充分满足"},"sampling":"uniform task, then uniform enabled method; with replacement","blinding":"method identity, run path, and automatic scores are not sent to the browser"}
def now():return datetime.now(UTC).isoformat()
def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def fingerprint(v):return hashlib.sha256(dump(v).encode()).hexdigest()
class APIError(Exception):
 def __init__(self,message,status=400):super().__init__(message);self.status=status

class Study:
 def __init__(self,config_path):
  self.path=Path(config_path).resolve();self.config=json.loads(self.path.read_text());c=self.config
  self.root=(self.path.parent/c["benchmark_root"]).resolve();self.db_path=(self.path.parent/c["database"]).resolve();self.study_id=c["study_id"]
  if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",self.study_id):raise ValueError("Invalid study_id")
  enabled=[m for m in c["methods"] if m.get("enabled",True)];self.methods={m["id"]:m for m in enabled}
  if not self.methods or len(self.methods)!=len(enabled):raise ValueError("Enable at least one unique method")
  rows=[json.loads(x) for x in (self.root/c["task_manifest"]).read_text().splitlines() if x.strip()];asked=set(c.get("task_ids",[]));self.tasks={r["id"]:r for r in rows if not asked or r["id"] in asked}
  if not self.tasks or asked-self.tasks.keys():raise ValueError("Empty or unknown task_ids")
  self.sources={};missing=[]
  for tid in sorted(self.tasks):
   for mid,m in self.methods.items():
    p=(self.root/m["run_dir"]/m.get("output_pattern","task_outputs/{task_id}/output.mp4").format(task_id=tid)).resolve()
    if not p.is_file() or not p.stat().st_size:missing.append(str(p));continue
    s=p.stat();self.sources[tid,mid]={"path":str(p),"bytes":s.st_size,"mtime_ns":s.st_mtime_ns}
  if missing:raise ValueError("All enabled methods must cover selected tasks. Missing/empty:\n"+"\n".join(missing))
  self.snapshot={"protocol":PROTOCOL,"methods":self.methods,"tasks":self.tasks,"sources":{f"{t}/{m}":v for(t,m),v in self.sources.items()}};self.digest=fingerprint(self.snapshot);self.db_path.parent.mkdir(parents=True,exist_ok=True)
  with closing(self.connect()) as db,db:
   db.executescript("""PRAGMA journal_mode=WAL;CREATE TABLE IF NOT EXISTS studies(id TEXT PRIMARY KEY,digest TEXT NOT NULL,snapshot TEXT NOT NULL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS participants(token TEXT PRIMARY KEY,id TEXT UNIQUE NOT NULL,label TEXT NOT NULL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS ratings(id TEXT PRIMARY KEY,study_id TEXT NOT NULL,participant_id TEXT NOT NULL,task_id TEXT NOT NULL,method_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,submitted_at TEXT,scores TEXT,note TEXT,watched INTEGER,media_info TEXT);CREATE UNIQUE INDEX IF NOT EXISTS one_pending_rating ON ratings(study_id,participant_id) WHERE status='pending';""")
   old=db.execute("select digest from studies where id=?",(self.study_id,)).fetchone()
   if old and old["digest"]!=self.digest:raise ValueError("Study contents/config changed. Choose a NEW study_id; existing results are preserved.")
   db.execute("insert or ignore into studies values(?,?,?,?)",(self.study_id,self.digest,dump(self.snapshot),now()))
 def connect(self):
  db=sqlite3.connect(self.db_path,timeout=30);db.row_factory=sqlite3.Row;return db
 def enroll(self,label):
  if not isinstance(label,str) or not 1<=len(label.strip())<=64:raise APIError("标注者代号需为 1–64 个字符。")
  token,pid=secrets.token_urlsafe(32),str(uuid.uuid4())
  with closing(self.connect()) as db,db:db.execute("insert into participants values(?,?,?,?)",(token,pid,label.strip(),now()))
  return token
 def participant(self,token):
  with closing(self.connect()) as db:r=db.execute("select * from participants where token=?",(token,)).fetchone()
  if not r:raise APIError("请先输入标注者代号。",401)
  return dict(r)
 def record(self,pid,rid):
  with closing(self.connect()) as db:r=db.execute("select * from ratings where id=? and participant_id=? and study_id=?",(rid,pid,self.study_id)).fetchone()
  if not r:raise APIError("未找到当前评分。",404)
  return dict(r)
 def draw(self,pid):
  with closing(self.connect()) as db,db:
   db.execute("begin immediate");old=db.execute("select id from ratings where study_id=? and participant_id=? and status='pending'",(self.study_id,pid)).fetchone()
   if old:return old["id"]
   rid,tid,mid=str(uuid.uuid4()),secrets.choice(sorted(self.tasks)),secrets.choice(sorted(self.methods));db.execute("insert into ratings(id,study_id,participant_id,task_id,method_id,created_at) values(?,?,?,?,?,?)",(rid,self.study_id,pid,tid,mid,now()));return rid
 def public(self,pid,rid):
  r=self.record(pid,rid);t=self.tasks[r["task_id"]]
  with closing(self.connect()) as db:n=db.execute("select count(*) from ratings where participant_id=? and study_id=? and status='submitted'",(pid,self.study_id)).fetchone()[0]
  return {"id":rid,"status":r["status"],"completed":n,"media":{"url":f"/media/{rid}"},"task":{"id":r["task_id"],"prompt":t["task"]["prompt"],"domain":t["video"]["category"],"intent":t["task"].get("type_zh",t["task"]["type"]),"source_title":t["video"].get("title_zh",t["video"].get("title_en","")),"target_seconds":t["task"]["target_output_length_sec"],"bgm_title":t.get("audio",{}).get("title","")}}
 def finish(self,pid,rid,body,skip=False):
  note=body.get("note","")
  if not isinstance(note,str) or len(note)>2000 or(skip and not note.strip()):raise APIError("跳过时需填写原因；备注不超过 2000 字。")
  scores=body.get("scores")
  if not skip:
   if not isinstance(scores,dict) or set(scores)!=set(METRICS):raise APIError("请完成 IF、VQ、TC、NC 四项评分。")
   if any(type(x)is not int or x not in(1,2,3,4,5) for x in scores.values()):raise APIError("每项请选择 1–5 分。")
   if body.get("watched") is not True:raise APIError("请确认已带声完整观看成片。")
  with closing(self.connect()) as db,db:
   db.execute("begin immediate");r=db.execute("select * from ratings where id=?",(rid,)).fetchone();status="skipped"if skip else"submitted"
   if r["status"]==status:
    if not skip and json.loads(r["scores"])!=scores:raise APIError("这一轮已保存，不能覆盖评分。",409)
    return
   if r["status"]!="pending":raise APIError("这一轮已结束。",409)
   source=self.sources[r["task_id"],r["method_id"]];db.execute("update ratings set status=?,submitted_at=?,scores=?,note=?,watched=?,media_info=? where id=?",(status,now(),None if skip else dump(scores),note,None if skip else 1,None if skip else dump(source),rid))

class Handler(BaseHTTPRequestHandler):
 @property
 def study(self):return self.server.study
 def json_response(self,v,status=200,cookie=None):
  b=dump(v).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Cache-Control","no-store");cookie and self.send_header("Set-Cookie",cookie);self.end_headers();self.wfile.write(b)
 def end_headers(self):self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","no-referrer");self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none'");super().end_headers()
 def identity(self):
  c=SimpleCookie(self.headers.get("Cookie",""));return self.study.participant(c["judge_session"].value if"judge_session"in c else"")
 def do_GET(self):self.dispatch()
 def do_HEAD(self):self.dispatch(head=True)
 def do_POST(self):self.dispatch(True)
 def dispatch(self,post=False,head=False):
  try:
   if self.headers.get("Origin")and urlparse(self.headers["Origin"]).netloc!=self.headers.get("Host"):raise APIError("Cross-origin request rejected",403)
   path=urlparse(self.path).path;body=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0")))or b"{}")if post else None
   if path=="/api/bootstrap"and not post:
    try:p=self.identity();p={"id":p["id"],"label":p["label"]}
    except APIError:p=None
    self.json_response({"title":self.study.config["title"],"study_id":self.study.study_id,"participant":p,"task_count":len(self.study.tasks),"metrics":METRICS});return
   if path in{"/","/app.js","/style.css"}and not post:self.file(BASE/"static"/{"/":"index.html","/app.js":"app.js","/style.css":"style.css"}[path],head);return
   if path=="/api/session"and post:self.json_response({"ok":True},cookie=f"judge_session={self.study.enroll(body.get('label'))}; HttpOnly; SameSite=Strict; Path=/");return
   if path=="/api/logout"and post:self.json_response({"ok":True},cookie="judge_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0");return
   pid=self.identity()["id"]
   if path=="/api/next"and post:self.json_response(self.study.public(pid,self.study.draw(pid)));return
   m=re.fullmatch(r"/api/ratings/([a-f0-9-]{36})/(ratings|skip)",path)
   if m and post:self.study.finish(pid,m[1],body,m[2]=="skip");self.json_response({"ok":True});return
   m=re.fullmatch(r"/media/([a-f0-9-]{36})",path)
   if m and not post:
    r=self.study.record(pid,m[1]);source=self.study.sources[r["task_id"],r["method_id"]];s=Path(source["path"]).stat()
    if s.st_size!=source["bytes"]or s.st_mtime_ns!=source["mtime_ns"]:raise APIError("源视频已变更，请联系管理员启动新实验。",409)
    self.file(Path(source["path"]),head);return
   raise APIError("Not found",404)
  except APIError as e:self.json_response({"error":str(e)},e.status)
  except Exception as e:print(type(e).__name__,e,flush=True);self.json_response({"error":"保存或读取失败，请重试。"},500)
 def file(self,path,head=False):
  size=path.stat().st_size;start,end,status=0,size-1,200;m=re.fullmatch(r"bytes=(\d*)-(\d*)",self.headers.get("Range", ""))
  if m and any(m.groups()):
   a,b=m.groups();start=int(a)if a else max(0,size-int(b));end=min(int(b),size-1)if b else size-1;status=206
   if start>end or start>=size:self.send_response(416);self.end_headers();return
  self.send_response(status);self.send_header("Content-Type",mimetypes.guess_type(path)[0]or"application/octet-stream");self.send_header("Content-Length",str(end-start+1));self.send_header("Accept-Ranges","bytes");status==206 and self.send_header("Content-Range",f"bytes {start}-{end}/{size}");self.end_headers()
  if not head:
   with path.open("rb")as f:
    f.seek(start);self.wfile.write(f.read(end-start+1))
 def log_message(self,*args):pass

def export_results(config_path,output):
 s=Study(config_path);output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);stamp=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ");base=output/f"{s.study_id}_{stamp}"
 with closing(s.connect()) as db:
  rows=[dict(r)for r in db.execute("select r.*,p.label from ratings r join participants p on p.id=r.participant_id where r.study_id=? order by r.created_at",(s.study_id,))]
 with (base.with_suffix(".csv")).open("w",newline="",encoding="utf-8")as f:
  writer=csv.DictWriter(f,fieldnames=["rating_id","participant_id","participant_label","task_id","method_id","metric","score","submitted_at","note"]);writer.writeheader()
  for r in rows:
   if r["status"]!="submitted":continue
   for metric,score in json.loads(r["scores"]).items():writer.writerow({"rating_id":r["id"],"participant_id":r["participant_id"],"participant_label":r["label"],"task_id":r["task_id"],"method_id":r["method_id"],"metric":metric,"score":score,"submitted_at":r["submitted_at"],"note":r["note"]})
 with (base.with_suffix(".jsonl")).open("w",encoding="utf-8")as f:
  for r in rows:f.write(dump(r)+"\n")
 base.with_suffix(".study.json").write_text(dump({"study_id":s.study_id,"digest":s.digest,"snapshot":s.snapshot})+"\n",encoding="utf-8")
 print(dump({"csv":str(base.with_suffix(".csv")),"jsonl":str(base.with_suffix(".jsonl")),"study":str(base.with_suffix(".study.json")),"records":len(rows)}))
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("serve","check","export"),nargs="?",default="serve");p.add_argument("--config",default=str(BASE/"config.json"));p.add_argument("--host");p.add_argument("--port",type=int);p.add_argument("--output",default=str(BASE/"exports"));a=p.parse_args();s=Study(a.config)
 if a.command=="check":print(dump({"study":s.study_id,"tasks":len(s.tasks),"methods":list(s.methods),"videos":len(s.sources),"database":str(s.db_path)}));return
 if a.command=="export":export_results(a.config,a.output);return
 host,port=a.host or s.config.get("host","127.0.0.1"),a.port or s.config.get("port",8766);server=ThreadingHTTPServer((host,port),Handler);server.study=s;print(f"Likert Human Judge: http://{host}:{port}\n{len(s.tasks)} tasks / {len(s.methods)} methods / {len(s.sources)} videos",flush=True);server.serve_forever()
if __name__=="__main__":main()
