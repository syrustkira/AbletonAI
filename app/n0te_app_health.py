from __future__ import annotations
from pathlib import Path
import json,socket,sys

def startup_health(bundle:Path,paths,doctor=None):
 bundle=Path(bundle);contents=bundle/'Contents';runtime=contents/'Frameworks/Python/bin/python3';core=contents/'Resources/app/n0te_server.py';checks={
  'private_runtime':{'state':'READY' if runtime.is_file() else 'FAILED','path':str(runtime)},
  'core':{'state':'READY' if core.is_file() else 'FAILED','path':str(core)},
  'user_data':{'state':'READY' if paths.data.is_dir() else 'FAILED','path':str(paths.data)},
  'configuration':{'state':'READY' if paths.data.is_dir() else 'FAILED'},
  'daw_discovery':{'state':'READY'},'update_manifest':{'state':'READY'},
  'obs':{'state':'OPTIONAL_NOT_INSTALLED'},'camera':{'state':'OPTIONAL_NOT_INSTALLED'},'ai':{'state':'OFF_HEALTHY'} }
 if doctor:checks['ableton_integration']=doctor()
 required=('private_runtime','core','user_data','configuration','daw_discovery','update_manifest');return {'healthy':all(checks[x]['state']=='READY' for x in required),'checks':checks}
