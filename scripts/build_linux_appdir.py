#!/usr/bin/env python3
"""Build a deterministic Linux AppDir from an explicit private runtime input."""
from __future__ import annotations
import argparse,hashlib,json,shutil,stat,subprocess,os,platform
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def copy_tree(source,target):shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.pyc","tests"))
def build(output,runtime):
 output=Path(output);runtime=Path(runtime)
 python=runtime/"bin/python3"
 if not python.is_file() or not (runtime/"LICENSE").is_file():raise RuntimeError("Runtime input requires bin/python3 and LICENSE; system Python fallback is forbidden")
 if output.exists():shutil.rmtree(output)
 (output/"usr/bin").mkdir(parents=True);(output/"usr/lib/n0te").mkdir(parents=True);(output/"usr/share/applications").mkdir(parents=True);(output/"usr/share/licenses/N0TE").mkdir(parents=True)
 copy_tree(runtime,output/"usr/runtime");copy_tree(ROOT/"app",output/"usr/lib/n0te/app");copy_tree(ROOT/"packaging",output/"usr/lib/n0te/packaging")
 shutil.copy2(ROOT/"LICENSE",output/"usr/share/licenses/N0TE/LICENSE") if (ROOT/"LICENSE").exists() else None
 launcher='#!/bin/sh\nHERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexport PYTHONHOME="$HERE/usr/runtime"\nunset PYTHONPATH\nexec "$HERE/usr/runtime/bin/python3" -s "$HERE/usr/lib/n0te/app/n0te_app.py" "$@"\n'
 (output/"AppRun").write_text(launcher);(output/"AppRun").chmod(0o755)
 desktop='[Desktop Entry]\nType=Application\nName=N0TE\nExec=n0te\nIcon=n0te\nCategories=AudioVideo;Audio;\nTerminal=false\n'
 (output/"n0te.desktop").write_text(desktop);shutil.copy2(output/"n0te.desktop",output/"usr/share/applications/n0te.desktop")
 hashes={}
 for path in sorted(x for x in output.rglob("*") if x.is_file()):hashes[str(path.relative_to(output))]=hashlib.sha256(path.read_bytes()).hexdigest()
 env={**os.environ,"PYTHONHOME":str(output/"usr/runtime")};env.pop("PYTHONPATH",None)
 version=subprocess.check_output([str(output/"usr/runtime/bin/python3"),"-s","--version"],text=True,env=env).strip()
 manifest={"product":"N0TE","development_build":True,"consumer_ready":False,"runtime_present":True,"runtime_version":version,"runtime_architecture":platform.machine(),"runtime_binary_sha256":hashes["usr/runtime/bin/python3"],"runtime_license_sha256":hashes["usr/runtime/LICENSE"],"runtime_provenance":"EXTERNAL_INPUT_NOT_ATTESTED","signed":False,"appimage":False,"files":hashes}
 (output/"BUILD_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n");return manifest
if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);parser.add_argument("--runtime",required=True);args=parser.parse_args();build(args.output,args.runtime)
