#!/usr/bin/env python3
"""External replacement helper. It never kills N0TE and never touches user data."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def wait_for_exit(pid,timeout):
 end=time.time()+timeout
 while time.time()<end:
  try:os.kill(pid,0)
  except ProcessLookupError:return True
  time.sleep(.2)
 return False
def main():
 p=argparse.ArgumentParser();p.add_argument('--handoff',type=Path,required=True);a=p.parse_args();h=json.loads(a.handoff.read_text());current=Path(h['current_app']).resolve();staged=Path(h['staged_app']).resolve();backup=Path(h['backup_app']).resolve()
 if not current.name.endswith('.app') or not staged.name.endswith('.app') or current==staged:raise SystemExit('unsafe app paths')
 if not wait_for_exit(int(h['pid']),float(h.get('timeout',30))):raise SystemExit('N0TE did not exit; update remains staged')
 expected=h['bundle_hashes'];actual={str(x.relative_to(staged)):digest(x) for x in staged.rglob('*') if x.is_file()}
 if actual!=expected:raise SystemExit('staged application verification failed')
 shutil.rmtree(backup,ignore_errors=True)
 if current.exists():shutil.copytree(current,backup,symlinks=True)
 replacement=current.with_name(current.name+'.new');shutil.rmtree(replacement,ignore_errors=True);shutil.copytree(staged,replacement,symlinks=True)
 try:
  old=current.with_name(current.name+'.old');shutil.rmtree(old,ignore_errors=True)
  if current.exists():current.replace(old)
  replacement.replace(current);subprocess.run(['/usr/bin/open',str(current)],check=False)
  shutil.rmtree(old,ignore_errors=True)
 except Exception:
  shutil.rmtree(current,ignore_errors=True)
  if backup.exists():shutil.copytree(backup,current,symlinks=True)
  raise
 return 0
if __name__=='__main__':raise SystemExit(main())
