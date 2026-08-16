"""Deterministic offline audio measurement and bounded corrective preview.
Loudness is explicitly an ungated BS.1770 energy estimate, not certified LUFS.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import array,math,wave
@dataclass(frozen=True)
class AudioBuffer:sample_rate:int;channels:tuple[tuple[float,...],...];source:str="";range_seconds:tuple[float,float]|None=None
@dataclass(frozen=True)
class Diagnosis:code:str;measurement:str;interpretation:str;recommendation:str;severity:str

def read_wav(path,start=0.0,end=None):
 with wave.open(str(path),'rb') as f:
  if f.getcomptype()!='NONE' or f.getsampwidth()!=2:raise ValueError('Only uncompressed 16-bit PCM WAV is supported')
  rate,n=f.getframerate(),f.getnchannels();a=max(0,int(start*rate));b=min(f.getnframes(),int(end*rate) if end is not None else f.getnframes());f.setpos(a);raw=f.readframes(b-a)
 vals=array.array('h',raw)
 if vals.itemsize!=2:raise RuntimeError('Unexpected PCM width')
 channels=tuple(tuple(vals[i]/32768 for i in range(c,len(vals),n)) for c in range(n));return AudioBuffer(rate,channels,str(path),(a/rate,b/rate))
def _flat(b):return [x for c in b.channels for x in c]
def levels(b,clip_threshold=1.0):
 x=_flat(b);peak=max(map(abs,x),default=0);rms=math.sqrt(sum(v*v for v in x)/max(1,len(x)));dc=sum(x)/max(1,len(x));crest=20*math.log10(peak/rms) if peak and rms else 0
 return {'sample_peak':peak,'sample_peak_dbfs':20*math.log10(peak) if peak else -math.inf,'rms':rms,'rms_dbfs':20*math.log10(rms) if rms else -math.inf,'dc_offset':dc,'crest_factor_db':crest,'overs':sum(abs(v)>=clip_threshold for v in x),'headroom_db':-20*math.log10(peak) if peak else math.inf,'loudness_estimate_lufs':-0.691+10*math.log10(sum(v*v for v in x)/max(1,len(x))) if any(x) else -math.inf,'loudness_standard':'BS.1770 energy estimate; K-weighting/gating not applied'}
def stereo(b):
 if len(b.channels)<2:return {'correlation':1.0,'mid_energy':sum(v*v for v in b.channels[0]),'side_energy':0.0,'width_ratio':0.0,'mono_compatibility_risk':False}
 l,r=b.channels[:2];n=min(len(l),len(r));l=l[:n];r=r[:n];ml=sum(l)/max(n,1);mr=sum(r)/max(n,1);num=sum((a-ml)*(z-mr) for a,z in zip(l,r));den=math.sqrt(sum((a-ml)**2 for a in l)*sum((z-mr)**2 for z in r));corr=num/den if den else 1.;mid=sum(((a+z)*.5)**2 for a,z in zip(l,r));side=sum(((a-z)*.5)**2 for a,z in zip(l,r));return {'correlation':corr,'mid_energy':mid,'side_energy':side,'width_ratio':math.sqrt(side/mid) if mid else math.inf,'mono_compatibility_risk':corr<0}
def spectrum(b,size=1024):
 x=[sum(v)/len(b.channels) for v in zip(*b.channels)][:size];n=len(x)
 if not n:return {'bins':[],'centroid_hz':0,'rolloff_hz':0,'band_energy':{}}
 mags=[]
 for k in range(n//2+1):
  re=sum(v*math.cos(2*math.pi*k*i/n) for i,v in enumerate(x));im=-sum(v*math.sin(2*math.pi*k*i/n) for i,v in enumerate(x));mags.append(math.hypot(re,im))
 freqs=[k*b.sample_rate/n for k in range(len(mags))];total=sum(mags);cent=sum(f*m for f,m in zip(freqs,mags))/total if total else 0;target=.85*total;acc=0;roll=0
 for f,m in zip(freqs,mags):
  acc+=m
  if acc>=target:roll=f;break
 bands={'sub':(20,80),'low':(80,250),'mid':(250,2000),'presence':(2000,6000),'air':(6000,20000)};ener={name:sum(m*m for f,m in zip(freqs,mags) if lo<=f<hi) for name,(lo,hi) in bands.items()}
 peaks=sorted(((m,f) for f,m in zip(freqs,mags) if f>20),reverse=True)[:8];return {'bins':list(zip(freqs,mags)),'centroid_hz':cent,'rolloff_hz':roll,'band_energy':ener,'resonance_candidates_hz':[f for _,f in peaks]}
def dynamics(b,window=1024):
 x=[sum(abs(v) for v in frame)/len(frame) for frame in zip(*b.channels)];env=[sum(x[i:i+window])/max(1,len(x[i:i+window])) for i in range(0,len(x),window)];trans=[i for i in range(1,len(env)) if env[i]>env[i-1]*1.8 and env[i]>.01];return {'transient_count':len(trans),'transient_density_hz':len(trans)/(len(x)/b.sample_rate) if x else 0,'macro_dynamic_range':max(env,default=0)-min(env,default=0),'flatness_indicator':1-(max(env,default=0)-min(env,default=0))/max(max(env,default=0),1e-12)}
def masking(a,b):
 sa,sb=spectrum(a),spectrum(b);bands=set(sa['band_energy'])&set(sb['band_energy']);overlap={k:min(sa['band_energy'][k],sb['band_energy'][k])/max(sa['band_energy'][k],sb['band_energy'][k],1e-15) for k in bands};return {'band_overlap':overlap,'maximum_overlap':max(overlap.values(),default=0),'candidate':max(overlap.values(),default=0)>.7}
def analyze(b):return {'source':b.source,'range_seconds':b.range_seconds,'levels':levels(b),'stereo':stereo(b),'spectrum':spectrum(b),'dynamics':dynamics(b)}
def diagnose(report):
 out=[];l,s=report['levels'],report['stereo']
 if l['overs']:out.append(Diagnosis('CLIPPING','samples reached the configured clipping threshold','Digital clipping may be present','Reduce gain before later processing and re-measure','HIGH'))
 if abs(l['dc_offset'])>.01:out.append(Diagnosis('DC_OFFSET',f"DC offset {l['dc_offset']:.4f}",'A measurable DC bias is present','Use a DC-removal/high-pass stage and re-measure','MEDIUM'))
 if s['correlation']<0:out.append(Diagnosis('PHASE_RISK',f"L/R correlation {s['correlation']:.3f}",'Mono cancellation risk is measurable','Preview in mono; inspect the contributing source before global width changes','MEDIUM'))
 return [asdict(x) for x in out]
def gain(b,db):
 g=10**(db/20);return AudioBuffer(b.sample_rate,tuple(tuple(max(-1,min(1,v*g)) for v in c) for c in b.channels),b.source,b.range_seconds)
def closed_loop_peak(b,target_dbfs=-1):
 before=analyze(b);change=target_dbfs-before['levels']['sample_peak_dbfs'] if math.isfinite(before['levels']['sample_peak_dbfs']) else 0;candidate=gain(b,change);after=analyze(candidate);return {'processor':'N0TE_GAIN','parameter_db':change,'before':before,'after':after,'improved':after['levels']['sample_peak_dbfs']<=target_dbfs+1e-6,'approval_required':True,'applied':False,'quality_state':'NUMERICALLY_VALIDATED'}
