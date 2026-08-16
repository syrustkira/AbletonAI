#!/usr/bin/env python3
"""External replacement helper. It never kills N0TE and never touches user data."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,time,urllib.parse,urllib.request
from pathlib import Path

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def wait_for_exit(pid,timeout):
 end=time.time()+timeout
 while time.time()<end:
  try:os.kill(pid,0)
  except ProcessLookupError:return True
  except OSError:return True
  time.sleep(.2)
 return False
def wait_for_health(url,timeout):
 parsed=urllib.parse.urlsplit(str(url or ''));host=(parsed.hostname or '').lower()
 if parsed.scheme!='http' or host not in {'127.0.0.1','localhost','::1'}:raise RuntimeError('Update health handshake must use local HTTP')
 end=time.time()+float(timeout);last=''
 while time.time()<end:
  try:
   with urllib.request.urlopen(url,timeout=min(1,max(.1,end-time.time()))) as response:
    payload=json.loads(response.read().decode('utf-8') or '{}')
    if getattr(response,'status',200)==200 and isinstance(payload,dict) and payload.get('ok') is True:return True
    last=f"HTTP {getattr(response,'status','?')} without ok=true"
  except Exception as exc:last=str(exc)
  time.sleep(.2)
 raise RuntimeError(f'Updated N0TE did not complete local health handshake: {last}')
def main():
 p=argparse.ArgumentParser();p.add_argument('--handoff',type=Path,required=True);a=p.parse_args();h=json.loads(a.handoff.read_text());current=Path(h['current_app']).resolve();staged=Path(h['staged_app']).resolve();backup=Path(h['backup_app']).resolve();timeout=float(h.get('timeout',30));health_url=str(h.get('health_url') or 'http://127.0.0.1:8766/api/status')
 if not current.name.endswith('.app') or not staged.name.endswith('.app') or current==staged:raise SystemExit('unsafe app paths')
 if not wait_for_exit(int(h['pid']),timeout):raise SystemExit('N0TE did not exit; update remains staged')
 expected=h['bundle_hashes'];actual={str(x.relative_to(staged)):digest(x) for x in staged.rglob('*') if x.is_file()}
 if actual!=expected:raise SystemExit('staged application verification failed')
 shutil.rmtree(backup,ignore_errors=True)
 if current.exists():shutil.copytree(current,backup,symlinks=True)
 replacement=current.with_name(current.name+'.new');shutil.rmtree(replacement,ignore_errors=True);shutil.copytree(staged,replacement,symlinks=True)
 old=current.with_name(current.name+'.old');shutil.rmtree(old,ignore_errors=True)
 try:
  if current.exists():current.replace(old)
  replacement.replace(current)
  if subprocess.run(['/usr/bin/open',str(current)],check=False).returncode!=0:raise RuntimeError('Updated N0TE launch request failed')
  wait_for_health(health_url,timeout)
  shutil.rmtree(old,ignore_errors=True)
 except Exception:
  shutil.rmtree(current,ignore_errors=True)
  if old.exists():old.replace(current)
  elif backup.exists():shutil.copytree(backup,current,symlinks=True)
  try:subprocess.run(['/usr/bin/open',str(current)],check=False)
  except Exception:pass
  raise
 return 0
if __name__=='__main__':raise SystemExit(main())
