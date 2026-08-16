"""Song-bound audio history, external rendering, stems, and mastering plans."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,struct,time,wave
from pathlib import Path
from n0te_audio import analyze,compare_reference,diagnose,masking,AudioBuffer
from n0te_dsp import Gain,Limiter,process_chain
from n0te_state import atomic_write_json


class AnalysisHistory:
 def __init__(self,path):self.path=Path(path)
 def record(self,song_id,workspace_id,buffer,report,settings=None):
  if not song_id:raise ValueError("Song identity required")
  source_hash=(buffer.metadata or {}).get("source_sha256") or hashlib.sha256(repr(buffer.channels).encode()).hexdigest()
  current=json.loads(self.path.read_text()) if self.path.exists() else {"schema":1,"analyses":[]}
  item={"song_id":song_id,"workspace_id":workspace_id,"source":buffer.source,"source_sha256":source_hash,"range":buffer.range_seconds,"algorithm_version":report["algorithm_version"],"settings":settings or {},"time":time.time(),"report":report}
  current["analyses"].append(item);atomic_write_json(self.path,current);return item
 def current_for(self,source,source_hash):
  if not self.path.exists():return None
  matches=[x for x in json.loads(self.path.read_text())["analyses"] if x["source"]==source and x["source_sha256"]==source_hash]
  return matches[-1] if matches else None


def analyze_stems(sources,master=None):
 reports={name:analyze(buffer) for name,buffer in sources.items()};pairs={}
 names=sorted(sources)
 for index,name in enumerate(names):
  for other in names[index+1:]:pairs[f"{name}::{other}"]=masking(sources[name],sources[other])
 contribution={}
 if master:
  master_report=analyze(master)
  for name,report in reports.items():contribution[name]={band:energy/max(master_report["spectrum"]["band_energy"].get(band,0),1e-15) for band,energy in report["spectrum"]["band_energy"].items()}
 else:master_report=None
 return {"sources":reports,"pairwise_masking":pairs,"master":master_report,"frequency_contribution":contribution}


def mastering_candidate(mix,target_lufs=-14,target_dbtp=-1,reference=None):
 before=analyze(mix);gain_db=max(-12,min(12,target_lufs-before["levels"]["lufs_i"])) if before["levels"]["lufs_i"]!=float("-inf") else 0
 chain=[Gain(gain_db),Limiter(target_dbtp)];candidate,receipt=process_chain(mix,chain);after=analyze(candidate)
 return {"before":before,"diagnoses":diagnose(before),"reference":compare_reference(mix,reference) if reference else None,"target":{"lufs_i":target_lufs,"dbtp":target_dbtp},"strategy":"bounded gain followed by lookahead limiter","processor_receipt":receipt,"candidate":candidate,"after":after,"approval_required":True,"applied":False}


def write_pcm16(path,buffer):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with wave.open(str(path),"wb") as handle:
  handle.setnchannels(len(buffer.channels));handle.setsampwidth(2);handle.setframerate(buffer.sample_rate)
  frames=bytearray()
  for frame in zip(*buffer.channels):
   for value in frame:frames.extend(struct.pack("<h",max(-32768,min(32767,round(value*32767)))))
  handle.writeframes(frames)


def render_external(source_path,output_path,candidate,song_id,parent_version,processor_receipt,approved):
 if not approved:raise PermissionError("Explicit output authority required")
 source_path=Path(source_path);output_path=Path(output_path)
 if source_path.resolve()==output_path.resolve():raise PermissionError("Original audio cannot be overwritten")
 write_pcm16(output_path,candidate);data=output_path.read_bytes()
 receipt={"song_id":song_id,"source":str(source_path),"output":str(output_path),"parent_version":parent_version,"output_sha256":hashlib.sha256(data).hexdigest(),"processor_chain":processor_receipt,"created_at":time.time(),"authority":"EXTERNAL_AUDIO_RENDER","daw_gate1":False}
 atomic_write_json(output_path.with_suffix(output_path.suffix+".n0te.json"),receipt);return receipt
