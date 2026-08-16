"""Song-bound audio history, professional rendering, stems, and optimization."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from enum import Enum
import hashlib,json,math,struct,time
from pathlib import Path
from n0te_audio import ALGORITHM_VERSION,AudioBuffer,analyze,compare_reference,diagnose,masking
from n0te_dsp import Gain,Limiter,process_chain
from n0te_state import atomic_write_json


@dataclass(frozen=True)
class AnalysisKey:
 song_id:str;workspace_id:str;source:str;source_sha256:str;range_seconds:tuple|None;algorithm_version:str;settings_json:str
 @classmethod
 def create(cls,song_id,workspace_id,buffer,settings=None,algorithm_version=ALGORITHM_VERSION):
  source_hash=(buffer.metadata or {}).get("source_sha256") or hashlib.sha256(repr(buffer.channels).encode()).hexdigest()
  return cls(song_id,workspace_id,buffer.source,source_hash,buffer.range_seconds,algorithm_version,json.dumps(settings or {},sort_keys=True,separators=(",",":")))


def _canonical_json_value(value):
 return json.loads(json.dumps(value,sort_keys=True,separators=(",",":")))


class AnalysisHistory:
 def __init__(self,path):self.path=Path(path)
 def _load(self):
  if not self.path.exists():return {"schema":2,"analyses":[]}
  try:value=json.loads(self.path.read_text())
  except (OSError,json.JSONDecodeError):return {"schema":2,"analyses":[],"recovery":"CORRUPT_STATE_IGNORED"}
  rows=value.get("analyses",[]) if isinstance(value,dict) else []
  return {"schema":2,"analyses":[row for row in rows if isinstance(row,dict)]}
 def record(self,song_id,workspace_id,buffer,report,settings=None):
  if not song_id:raise ValueError("Song identity required")
  key=AnalysisKey.create(song_id,workspace_id,buffer,settings,report["algorithm_version"]);current=self._load()
  item={"key":asdict(key),"song_id":song_id,"workspace_id":workspace_id,"source":buffer.source,"source_sha256":key.source_sha256,"range":buffer.range_seconds,"algorithm_version":report["algorithm_version"],"settings":settings or {},"time":time.time(),"report":report}
  current["analyses"].append(item);atomic_write_json(self.path,current);return item
 def current_for(self,key:AnalysisKey):
  target=_canonical_json_value(asdict(key));matches=[item for item in self._load()["analyses"] if _canonical_json_value(item.get("key"))==target]
  return matches[-1] if matches else None


class Encoding(str,Enum):PCM16="PCM16";PCM24="PCM24";PCM32="PCM32";FLOAT32="FLOAT32"
class DitherPolicy(str,Enum):NONE="NONE";TPDF="TPDF"
class DestinationRole(str,Enum):WORKING_RENDER="WORKING_RENDER";MASTER="MASTER";DELIVERY="DELIVERY";STREAM="STREAM";ARCHIVE="ARCHIVE";PREVIEW="PREVIEW"
@dataclass(frozen=True)
class RenderSpecification:
 sample_rate:int;encoding:Encoding=Encoding.FLOAT32;channel_layout:tuple[str,...]=();dither:DitherPolicy=DitherPolicy.NONE;metadata_policy:str="PRESERVE_RECEIPT";destination_role:DestinationRole=DestinationRole.WORKING_RENDER


def analyze_stems(sources,master=None):
 reports={name:analyze(buffer) for name,buffer in sources.items()};pairs={};names=sorted(sources)
 for index,name in enumerate(names):
  for other in names[index+1:]:pairs[f"{name}::{other}"]=masking(sources[name],sources[other])
 contribution={};master_report=analyze(master) if master else None
 if master_report:
  for name,report in reports.items():contribution[name]={band:energy/max(master_report["spectrum"]["band_energy"].get(band,0),1e-15) for band,energy in report["spectrum"]["band_energy"].items()}
 return {"sources":reports,"pairwise_masking":pairs,"master":master_report,"frequency_contribution":contribution}


def mastering_candidate(mix,target_lufs=-14,target_dbtp=-1,reference=None,maximum_gain_change=12,minimum_crest_preservation=.6,maximum_iterations=6,tolerance=.25):
 if maximum_iterations<1 or maximum_iterations>20:raise ValueError("maximum_iterations must be 1..20")
 before=analyze(mix);initial=target_lufs-before["levels"]["lufs_i"] if math.isfinite(before["levels"]["lufs_i"]) else 0;gain_db=max(-maximum_gain_change,min(maximum_gain_change,initial));explored=[];best=None
 reference_report=compare_reference(mix,reference) if reference else None
 for iteration in range(maximum_iterations):
  chain=[Gain(gain_db),Limiter(target_dbtp)];candidate,receipt=process_chain(mix,chain);report=analyze(candidate);loudness_error=target_lufs-report["levels"]["lufs_i"] if math.isfinite(report["levels"]["lufs_i"]) else math.inf;true_peak_over=max(0,report["levels"]["true_dbtp"]-target_dbtp);crest_ratio=report["levels"]["crest_factor_db"]/max(before["levels"]["crest_factor_db"],1e-9);dynamics_penalty=max(0,minimum_crest_preservation-crest_ratio)*10;score=abs(loudness_error)+10*true_peak_over+dynamics_penalty
  row={"iteration":iteration+1,"gain_db":gain_db,"lufs_i":report["levels"]["lufs_i"],"dbtp":report["levels"]["true_dbtp"],"crest_factor_db":report["levels"]["crest_factor_db"],"loudness_error":loudness_error,"true_peak_over":true_peak_over,"crest_preservation":crest_ratio,"score":score}
  explored.append(row)
  if best is None or score<best[0]-1e-9:best=(score,candidate,report,receipt,row)
  else:break
  if abs(loudness_error)<=tolerance and true_peak_over<=.05:break
  if crest_ratio<minimum_crest_preservation:break
  adjustment=max(-3,min(3,loudness_error));new_gain=max(-maximum_gain_change,min(maximum_gain_change,gain_db+adjustment))
  if abs(new_gain-gain_db)<.01:break
  gain_db=new_gain
 _,candidate,after,receipt,selected=best
 return {"before":before,"diagnoses":diagnose(before),"reference":reference_report,"target":{"lufs_i":target_lufs,"dbtp":target_dbtp,"tolerance":tolerance,"minimum_crest_preservation":minimum_crest_preservation},"strategy":"bounded deterministic gain/limiter optimization","candidates_explored":explored,"objective":{"target_error_before":initial,"target_error_after":selected["loudness_error"],"selected_score":selected["score"]},"selected_reason":"lowest bounded objective score without an accepted dynamics violation","processor_receipt":receipt,"candidate":candidate,"after":after,"approval_required":True,"applied":False,"quality_status":["IMPLEMENTED","NUMERICALLY_VALIDATED","LISTENING_ACCEPTANCE_PENDING","BENCHMARK_PENDING"]}


def _tpdf(seed,index):
 first=int.from_bytes(hashlib.sha256(f"{seed}:{index}:a".encode()).digest()[:8],"little")/2**64
 second=int.from_bytes(hashlib.sha256(f"{seed}:{index}:b".encode()).digest()[:8],"little")/2**64
 return first-second


def write_wav(path,buffer,specification:RenderSpecification):
 if specification.sample_rate!=buffer.sample_rate:raise ValueError("Resampling is not implemented; render sample rate must match source")
 if specification.channel_layout and len(specification.channel_layout)!=len(buffer.channels):raise ValueError("Channel layout count does not match audio")
 encoding=specification.encoding;bits={Encoding.PCM16:16,Encoding.PCM24:24,Encoding.PCM32:32,Encoding.FLOAT32:32}[encoding];tag=3 if encoding is Encoding.FLOAT32 else 1;width=bits//8;payload=bytearray();seed=(buffer.metadata or {}).get("source_sha256",buffer.source)
 for index,frame in enumerate(zip(*buffer.channels)):
  for value in frame:
   if tag==3:payload.extend(struct.pack("<f",float(value)));continue
   scale=1<<(bits-1);noise=_tpdf(seed,index)/scale if specification.dither is DitherPolicy.TPDF else 0;integer=max(-scale,min(scale-1,round((value+noise)*(scale-1))));payload.extend(integer.to_bytes(width,"little",signed=True))
 channels=len(buffer.channels);align=channels*width;fmt=struct.pack("<HHIIHH",tag,channels,buffer.sample_rate,buffer.sample_rate*align,align,bits)
 def chunk(name,data):return name+struct.pack("<I",len(data))+data+(b"\0" if len(data)&1 else b"")
 body=b"WAVE"+chunk(b"fmt ",fmt)+chunk(b"data",bytes(payload));Path(path).write_bytes(b"RIFF"+struct.pack("<I",len(body))+body)


def write_pcm16(path,buffer):write_wav(path,buffer,RenderSpecification(buffer.sample_rate,Encoding.PCM16))


def render_external(source_path,output_path,candidate,song_id,parent_version,processor_receipt,approved,specification=None,workspace_id="",analysis_before=None,analysis_after=None):
 if not approved:raise PermissionError("Explicit output authority required")
 source_path=Path(source_path);output_path=Path(output_path)
 if source_path.resolve()==output_path.resolve():raise PermissionError("Original audio cannot be overwritten")
 specification=specification or RenderSpecification(candidate.sample_rate)
 write_wav(output_path,candidate,specification);data=output_path.read_bytes();source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest() if source_path.exists() else ""
 receipt={"song_id":song_id,"workspace_id":workspace_id,"source":str(source_path),"source_sha256":source_hash,"output":str(output_path),"parent_version":parent_version,"output_sha256":hashlib.sha256(data).hexdigest(),"render_specification":{**asdict(specification),"encoding":specification.encoding.value,"dither":specification.dither.value,"destination_role":specification.destination_role.value},"processor_chain":processor_receipt,"analysis_before":analysis_before,"analysis_after":analysis_after,"created_at":time.time(),"authority":"EXTERNAL_AUDIO_RENDER","daw_gate1":False}
 atomic_write_json(output_path.with_suffix(output_path.suffix+".n0te.json"),receipt);return receipt
