#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,plistlib,shutil,stat
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def hash_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def copy_tree(source,destination):
 shutil.copytree(source,destination,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--runtime-root',type=Path);p.add_argument('--allow-missing-runtime',action='store_true');p.add_argument('--bundle-id');args=p.parse_args()
 cfg=json.loads((ROOT/'packaging/macos/BUILD_CONFIG.json').read_text());name=cfg['development_product_name'] if cfg['development_build'] else cfg['product_name'];app=args.output/f'{name}.app';shutil.rmtree(app,ignore_errors=True)
 contents=app/'Contents';macos=contents/'MacOS';resources=contents/'Resources';frameworks=contents/'Frameworks';macos.mkdir(parents=True);resources.mkdir();frameworks.mkdir()
 runtime_present=bool(args.runtime_root and args.runtime_root.is_dir())
 if not runtime_present and not args.allow_missing_runtime:raise SystemExit('Private runtime missing: provide --runtime-root; builds never download or use Python from PATH')
 if runtime_present:copy_tree(args.runtime_root,frameworks/'Python')
 launcher=macos/'N0TE';shutil.copy2(ROOT/'packaging/macos/N0TE-launcher',launcher);launcher.chmod(launcher.stat().st_mode|stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)
 copy_tree(ROOT/'app',resources/'app');copy_tree(ROOT/'packaging',resources/'packaging');copy_tree(ROOT/'docs/acceptance',resources/'Acceptance');shutil.copy2(ROOT/'LICENSE',resources/'LICENSE');tools=resources/'tools';tools.mkdir();shutil.copy2(ROOT/'INSTALL_N0TE_ABLETON_AI.py',tools/'INSTALL_N0TE_ABLETON_AI.py');shutil.copy2(ROOT/'scripts/macos_update_helper.py',tools/'macos_update_helper.py')
 plist={'CFBundleDevelopmentRegion':'en','CFBundleDisplayName':name,'CFBundleExecutable':'N0TE','CFBundleIdentifier':args.bundle_id or cfg['bundle_identifier'],'CFBundleInfoDictionaryVersion':'6.0','CFBundleName':cfg['product_name'],'CFBundlePackageType':'APPL','CFBundleShortVersionString':cfg['bundle_version'],'CFBundleVersion':cfg['bundle_version'],'LSMinimumSystemVersion':cfg['minimum_macos'],'NSHighResolutionCapable':True}
 with (contents/'Info.plist').open('wb') as f:plistlib.dump(plist,f,sort_keys=True)
 classification={**cfg,'bundle_identifier':plist['CFBundleIdentifier'],'runtime_present':runtime_present,'consumer_ready':runtime_present,'artifact':str(app)};(resources/'BUILD_CLASSIFICATION.json').write_text(json.dumps(classification,indent=2,sort_keys=True)+'\n')
 hashes={str(x.relative_to(app)):hash_file(x) for x in sorted(app.rglob('*')) if x.is_file()};(resources/'BUNDLE_HASHES.json').write_text(json.dumps({'schema':1,'files':hashes},indent=2,sort_keys=True)+'\n')
 dmg=args.output/'dmg-root';shutil.rmtree(dmg,ignore_errors=True);dmg.mkdir();shutil.copytree(app,dmg/app.name);(dmg/'Applications').symlink_to('/Applications');shutil.copy2(ROOT/'LICENSE',dmg/'LICENSE');shutil.copy2(ROOT/'packaging/THIRD_PARTY_COMPONENTS.json',dmg/'THIRD_PARTY_COMPONENTS.json')
 print(json.dumps(classification,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
