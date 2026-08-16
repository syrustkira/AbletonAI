"""Deterministic offline audio analysis.

The loudness implementation follows BS.1770-4 block/gating rules and the
published K-weighting biquads. It is not labelled formally certified until it
is checked against the ITU/EBU conformance programme.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import struct
from pathlib import Path

ALGORITHM_VERSION = "audio-2"
CHANNEL_BITS = {0x1:"FL",0x2:"FR",0x4:"FC",0x8:"LFE",0x10:"BL",0x20:"BR",0x200:"SL",0x400:"SR"}


@dataclass(frozen=True)
class AudioBuffer:
    sample_rate: int
    channels: tuple[tuple[float, ...], ...]
    source: str = ""
    range_seconds: tuple[float, float] | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class Diagnosis:
    code: str
    evidence: dict
    interpretation: str
    recommendation: str
    severity: str
    reasoning_version: str = "diagnosis-2"


def _riff_chunks(raw: bytes):
    if raw[:4] not in {b"RIFF", b"RF64"} or raw[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/RF64 WAVE file")
    offset = 12
    while offset + 8 <= len(raw):
        name, size = struct.unpack_from("<4sI", raw, offset)
        start = offset + 8
        yield name, raw[start:start + size]
        offset = start + size + (size & 1)


def read_wav(path, start=0.0, end=None):
    """Decode PCM16/24/32 or IEEE float32 WAVE without optional libraries."""
    path = Path(path)
    raw = path.read_bytes()
    chunks = {name: data for name, data in _riff_chunks(raw)}
    if b"fmt " not in chunks or b"data" not in chunks:
        raise ValueError("WAVE requires fmt and data chunks")
    fmt = chunks[b"fmt "]
    if len(fmt) < 16:
        raise ValueError("Truncated WAVE format")
    tag, count, rate, _, align, bits = struct.unpack_from("<HHIIHH", fmt)
    channel_mask=0
    if tag == 0xFFFE and len(fmt) >= 40:  # WAVE_FORMAT_EXTENSIBLE
        channel_mask=struct.unpack_from("<I",fmt,20)[0]
        tag = struct.unpack_from("<H", fmt, 24)[0]
    supported = {(1, 16), (1, 24), (1, 32), (3, 32)}
    if (tag, bits) not in supported or not count or align != count * (bits // 8):
        raise ValueError(f"Unsupported WAVE encoding tag={tag} bits={bits} channels={count}")
    data = chunks[b"data"]
    frame_count = len(data) // align
    first = min(frame_count, max(0, int(start * rate)))
    last = min(frame_count, int(end * rate) if end is not None else frame_count)
    channels = [[] for _ in range(count)]
    width = bits // 8
    for frame in range(first, last):
        base = frame * align
        for channel in range(count):
            sample = data[base + channel * width:base + (channel + 1) * width]
            if tag == 3:
                value = struct.unpack("<f", sample)[0]
                if not math.isfinite(value):
                    raise ValueError("Non-finite float sample")
            elif bits == 24:
                integer = int.from_bytes(sample, "little", signed=False)
                if integer & 0x800000:
                    integer -= 1 << 24
                value = integer / 8388608.0
            else:
                integer = int.from_bytes(sample, "little", signed=True)
                value = integer / float(1 << (bits - 1))
            channels[channel].append(value)
    roles=[role for bit,role in CHANNEL_BITS.items() if channel_mask&bit]
    if count==1 and not roles:roles=["MONO"]
    elif count==2 and not roles:roles=["FL","FR"]
    layout_status="KNOWN" if len(roles)==count else "UNKNOWN_CHANNEL_LAYOUT"
    return AudioBuffer(rate, tuple(tuple(c) for c in channels), str(path),
                       (first / rate, last / rate),
                       {"format": "WAVE", "encoding": "IEEE_FLOAT" if tag == 3 else "PCM",
                        "bits_per_sample": bits, "channels": count, "frames": last - first,
                        "channel_mask":channel_mask,"channel_roles":roles,"channel_layout_status":layout_status,
                        "source_sha256": hashlib.sha256(raw).hexdigest()})


def stream_levels_wav(path,chunk_frames=65536):
    """Bounded-memory exact level/DC and chunk-overlapped true-peak scan."""
    path=Path(path)
    with path.open('rb') as header_handle:raw=header_handle.read(12)
    if raw[:4] not in {b"RIFF",b"RF64"} or raw[8:12]!=b"WAVE":raise ValueError("Not a RIFF/RF64 WAVE file")
    with path.open('rb') as handle:
        handle.seek(12);fmt=None;data_offset=data_size=None
        while True:
            header=handle.read(8)
            if len(header)<8:break
            name,size=struct.unpack('<4sI',header);start=handle.tell()
            if name==b'fmt ':fmt=handle.read(size)
            elif name==b'data':data_offset=start;data_size=size;break
            handle.seek(start+size+(size&1))
        if fmt is None or data_offset is None:raise ValueError("WAVE requires fmt and data chunks")
        if len(fmt)<16:raise ValueError("Truncated WAVE format")
        tag,count,rate,_,align,bits=struct.unpack_from('<HHIIHH',fmt)
        if tag==0xfffe and len(fmt)>=40:tag=struct.unpack_from('<H',fmt,24)[0]
        width=bits//8
        if (tag,bits) not in {(1,16),(1,24),(1,32),(3,32)} or not count or align!=count*width:raise ValueError("Unsupported streaming WAVE encoding")
        if data_size%align:raise ValueError("Truncated WAVE frame")
        handle.seek(data_offset);remaining=data_size;total=0;squares=0.;summed=0.;peak=0.;overs=0;true=0.;tail=[[] for _ in range(count)]
        while remaining:
            requested=min(remaining,chunk_frames*align);block=handle.read(requested)
            if len(block)!=requested:raise ValueError("Truncated WAVE data chunk")
            remaining-=len(block);frames=len(block)//align;channels=[[] for _ in range(count)]
            for frame in range(frames):
                for channel in range(count):
                    sample=block[frame*align+channel*width:frame*align+(channel+1)*width]
                    if tag==3:value=struct.unpack('<f',sample)[0]
                    elif bits==24:
                        integer=int.from_bytes(sample,'little');integer=integer-(1<<24) if integer&0x800000 else integer;value=integer/8388608
                    else:value=int.from_bytes(sample,'little',signed=True)/float(1<<(bits-1))
                    channels[channel].append(value);total+=1;squares+=value*value;summed+=value;peak=max(peak,abs(value));overs+=abs(value)>=1
            scan=AudioBuffer(rate,tuple(tuple(tail[i]+channels[i]) for i in range(count)));true=max(true,true_peak(scan)['true_peak']);tail=[channel[-16:] for channel in channels]
    rms=math.sqrt(squares/max(1,total));return {"sample_peak":peak,"sample_peak_dbfs":20*math.log10(peak) if peak else -math.inf,"rms":rms,"rms_dbfs":20*math.log10(rms) if rms else -math.inf,"dc_offset":summed/max(1,total),"overs":overs,"true_peak":true,"dbtp":20*math.log10(true) if true else -math.inf,"samples":total,"memory_bound_bytes":chunk_frames*align+count*16*8,"streaming_metrics":["level","rms","dc","overs","true_peak"],"deferred_metrics":["gated_loudness","stft","dynamics"]}


def _flat(buffer):
    return [value for channel in buffer.channels for value in channel]


def _biquad(samples, coefficients):
    b0, b1, b2, a1, a2 = coefficients
    x1 = x2 = y1 = y2 = 0.0
    output = []
    for x0 in samples:
        y0 = b0*x0 + b1*x1 + b2*x2 - a1*y1 - a2*y2
        output.append(y0)
        x2, x1, y2, y1 = x1, x0, y1, y0
    return output


def _k_weight(samples, sample_rate):
    # Coefficients published by ITU for 48 kHz; bilinear design for other rates.
    if sample_rate == 48000:
        stage1 = (1.53512485958697, -2.69169618940638, 1.19839281085285,
                  -1.69065929318241, 0.73248077421585)
        stage2 = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)
    else:
        def high_shelf(f0, gain, q):
            a = 10 ** (gain / 40); w = 2*math.pi*f0/sample_rate
            alpha = math.sin(w)/(2*q); c = math.cos(w); root = math.sqrt(a)
            b0=a*((a+1)+(a-1)*c+2*root*alpha); b1=-2*a*((a-1)+(a+1)*c); b2=a*((a+1)+(a-1)*c-2*root*alpha)
            a0=(a+1)-(a-1)*c+2*root*alpha; a1=2*((a-1)-(a+1)*c); a2=(a+1)-(a-1)*c-2*root*alpha
            return b0/a0,b1/a0,b2/a0,a1/a0,a2/a0
        def high_pass(f0, q):
            w=2*math.pi*f0/sample_rate; alpha=math.sin(w)/(2*q); c=math.cos(w)
            b0=(1+c)/2; b1=-(1+c); b2=b0; a0=1+alpha
            return b0/a0,b1/a0,b2/a0,(-2*c)/a0,(1-alpha)/a0
        stage1 = high_shelf(1681.974, 3.99984385, .707175)
        stage2 = high_pass(38.135, .500327)
    return _biquad(_biquad(samples, stage1), stage2)


def loudness(buffer):
    weighted = [_k_weight(channel, buffer.sample_rate) for channel in buffer.channels]
    roles=(buffer.metadata or {}).get("channel_roles") or (["MONO"] if len(weighted)==1 else ["FL","FR"] if len(weighted)==2 else [])
    layout_status="KNOWN" if len(roles)==len(weighted) else "UNKNOWN_CHANNEL_LAYOUT"
    weights=[0.0 if role=="LFE" else 1.41 if role in {"SL","SR","BL","BR"} else 1.0 for role in roles] if layout_status=="KNOWN" else [1.0]*len(weighted)
    def blocks(seconds, overlap):
        size=max(1,round(seconds*buffer.sample_rate)); hop=max(1,round(size*(1-overlap)))
        values=[]
        for start in range(0, max(1, min(map(len, weighted), default=0)-size+1), hop):
            energy=sum(weights[i]*sum(v*v for v in channel[start:start+size])/size for i,channel in enumerate(weighted))
            values.append(-.691+10*math.log10(energy) if energy>0 else -math.inf)
        return values
    momentary=blocks(.4,.75); short_term=blocks(3.0,2/3)
    absolute=[x for x in momentary if x>=-70]
    preliminary=10*math.log10(sum(10**((x+.691)/10) for x in absolute)/len(absolute))-.691 if absolute else -math.inf
    gated=[x for x in absolute if x>=preliminary-10]
    integrated=10*math.log10(sum(10**((x+.691)/10) for x in gated)/len(gated))-.691 if gated else -math.inf
    lra_values=sorted(x for x in short_term if x>=-70 and x>=integrated-20)
    def percentile(values,p):
        if not values:return 0.0
        pos=(len(values)-1)*p; lo=int(pos); hi=min(lo+1,len(values)-1); return values[lo]+(values[hi]-values[lo])*(pos-lo)
    return {"lufs_i":integrated,"lufs_m":momentary[-1] if momentary else -math.inf,
            "lufs_s":short_term[-1] if short_term else -math.inf,
            "lra_lu":percentile(lra_values,.95)-percentile(lra_values,.10),
            "momentary_series":momentary,"short_term_series":short_term,
            "standard":"BS.1770-4 / EBU R128 compatible algorithm; conformance vectors pending" if layout_status=="KNOWN" else "UNKNOWN_CHANNEL_LAYOUT",
            "channel_layout_status":layout_status,"channel_roles":roles}


def true_peak(buffer, oversample=4, taps=16):
    if oversample not in {2,4,8}: raise ValueError("oversample must be 2, 4, or 8")
    peak=0.0;half=taps//2;phases=[]
    for phase in range(oversample):
        coefficients=[]
        for offset in range(-half,half+1):
            distance=phase/oversample-offset
            sinc=1.0 if distance==0 else math.sin(math.pi*distance)/(math.pi*distance)
            coefficients.append((offset,sinc*(.5+.5*math.cos(math.pi*distance/(half+1)))))
        normalization=sum(value for _,value in coefficients);phases.append([(offset,value/normalization) for offset,value in coefficients])
    for channel in buffer.channels:
        peak=max(peak,max(map(abs,channel),default=0.0))
        for index in range(half,len(channel)-half):
            for coefficients in phases[1:]:peak=max(peak,abs(sum(channel[index+offset]*value for offset,value in coefficients)))
    sample_peak=max(map(abs,_flat(buffer)),default=0.0)
    return {"sample_peak":sample_peak,"true_peak":peak,"dbtp":20*math.log10(peak) if peak else -math.inf,
            "difference_db":20*math.log10(peak/sample_peak) if peak and sample_peak else 0.0,
            "oversample":oversample,"method":"windowed-sinc interpolation"}


def levels(buffer, clip_threshold=1.0):
    values=_flat(buffer); peak=max(map(abs,values),default=0); rms=math.sqrt(sum(v*v for v in values)/max(1,len(values))); dc=sum(values)/max(1,len(values))
    result={"sample_peak":peak,"sample_peak_dbfs":20*math.log10(peak) if peak else -math.inf,"rms":rms,"rms_dbfs":20*math.log10(rms) if rms else -math.inf,"dc_offset":dc,"crest_factor_db":20*math.log10(peak/rms) if peak and rms else 0,"overs":sum(abs(v)>=clip_threshold for v in values),"headroom_db":-20*math.log10(peak) if peak else math.inf}
    result.update(loudness(buffer));result.update({f"true_{k}":v for k,v in true_peak(buffer).items()});return result


def _fft(values):
    n=len(values)
    if n==1:return [complex(values[0])]
    if n<1 or n&(n-1):raise ValueError("FFT size must be a power of two")
    even=_fft(values[0::2]);odd=_fft(values[1::2]);out=[0j]*n
    for k in range(n//2):
        term=complex(math.cos(-2*math.pi*k/n),math.sin(-2*math.pi*k/n))*odd[k]
        out[k]=even[k]+term;out[k+n//2]=even[k]-term
    return out


def stft(buffer, fft_size=1024, hop_size=256, window="hann"):
    if window not in {"hann","rectangular"}:raise ValueError("Unsupported window")
    mono=[sum(frame)/len(frame) for frame in zip(*buffer.channels)]
    coefficients=[.5-.5*math.cos(2*math.pi*i/(fft_size-1)) if window=="hann" else 1 for i in range(fft_size)]
    frames=[];previous=None
    for start in range(0,max(0,len(mono)-fft_size+1),hop_size):
        magnitudes=[abs(x) for x in _fft([mono[start+i]*coefficients[i] for i in range(fft_size)])[:fft_size//2+1]]
        total=sum(magnitudes);freqs=[i*buffer.sample_rate/fft_size for i in range(len(magnitudes))]
        centroid=sum(f*m for f,m in zip(freqs,magnitudes))/total if total else 0;target=.85*total;running=0;rolloff=0
        for f,m in zip(freqs,magnitudes):
            running+=m
            if running>=target:rolloff=f;break
        flux=math.sqrt(sum(max(0,m-(previous[i] if previous else 0))**2 for i,m in enumerate(magnitudes))/len(magnitudes))
        frames.append({"time":start/buffer.sample_rate,"magnitudes":magnitudes,"centroid_hz":centroid,"rolloff_hz":rolloff,"spectral_flux":flux});previous=magnitudes
    return {"fft_size":fft_size,"hop_size":hop_size,"window":window,"frequencies_hz":[i*buffer.sample_rate/fft_size for i in range(fft_size//2+1)],"frames":frames}


def spectrum(buffer,size=1024):
    result=stft(buffer,size,max(1,size//2));frames=result["frames"]
    if not frames:return {"bins":[],"centroid_hz":0,"rolloff_hz":0,"band_energy":{},"resonance_candidates_hz":[]}
    mags=[sum(frame["magnitudes"][i] for frame in frames)/len(frames) for i in range(len(result["frequencies_hz"]))];freqs=result["frequencies_hz"]
    bands={"sub":(20,80),"low":(80,250),"mid":(250,2000),"presence":(2000,6000),"air":(6000,20000)};energy={name:sum(m*m for f,m in zip(freqs,mags) if lo<=f<hi) for name,(lo,hi) in bands.items()}
    peaks=sorted(((m,f) for f,m in zip(freqs,mags) if f>20),reverse=True)[:8]
    return {"bins":list(zip(freqs,mags)),"centroid_hz":sum(x["centroid_hz"] for x in frames)/len(frames),"rolloff_hz":sum(x["rolloff_hz"] for x in frames)/len(frames),"band_energy":energy,"resonance_candidates_hz":[f for _,f in peaks],"spectral_flux":sum(x["spectral_flux"] for x in frames)/len(frames)}


def stereo_by_band(buffer,bands=None,fft_size=1024,hop_size=512):
    bands=bands or {"sub":(20,80),"low":(80,250),"mid":(250,2000),"presence":(2000,6000),"air":(6000,20000)}
    if len(buffer.channels)<2:return {name:{"correlation":1.0,"width_ratio":0.0,"mono_cancellation_ratio":0.0,"phase_risk":False} for name in bands}
    left,right=buffer.channels[:2];window=[.5-.5*math.cos(2*math.pi*i/(fft_size-1)) for i in range(fft_size)];acc={name:[0.,0.,0.,0.,0.] for name in bands}
    for start in range(0,max(0,min(len(left),len(right))-fft_size+1),hop_size):
        lf=_fft([left[start+i]*window[i] for i in range(fft_size)]);rf=_fft([right[start+i]*window[i] for i in range(fft_size)])
        for index,(lv,rv) in enumerate(zip(lf[:fft_size//2+1],rf[:fft_size//2+1])):
            frequency=index*buffer.sample_rate/fft_size
            for name,(low,high) in bands.items():
                if low<=frequency<high:
                    l2=abs(lv)**2;r2=abs(rv)**2;cross=(lv*rv.conjugate()).real;mid=abs((lv+rv)/2)**2;side=abs((lv-rv)/2)**2
                    row=acc[name];row[0]+=l2;row[1]+=r2;row[2]+=cross;row[3]+=mid;row[4]+=side;break
    result={}
    for name,(l2,r2,cross,mid,side) in acc.items():
        correlation=cross/math.sqrt(l2*r2) if l2 and r2 else 1.;original=l2+r2
        result[name]={"correlation":correlation,"mid_energy":mid,"side_energy":side,"width_ratio":math.sqrt(side/mid) if mid else math.inf,"mono_cancellation_ratio":1-(2*mid/original if original else 1),"phase_risk":correlation<0}
    return result


def stereo(buffer):
    if len(buffer.channels)<2:return {"correlation":1.0,"mid_energy":sum(v*v for v in buffer.channels[0]),"side_energy":0.0,"width_ratio":0.0,"mono_compatibility_risk":False,"mono_cancellation_ratio":0.0}
    left,right=buffer.channels[:2];n=min(len(left),len(right));left=left[:n];right=right[:n];ml=sum(left)/max(n,1);mr=sum(right)/max(n,1);num=sum((a-ml)*(b-mr) for a,b in zip(left,right));den=math.sqrt(sum((a-ml)**2 for a in left)*sum((b-mr)**2 for b in right));correlation=num/den if den else 1.;mid=sum(((a+b)*.5)**2 for a,b in zip(left,right));side=sum(((a-b)*.5)**2 for a,b in zip(left,right));original=sum(a*a+b*b for a,b in zip(left,right));return {"correlation":correlation,"mid_energy":mid,"side_energy":side,"width_ratio":math.sqrt(side/mid) if mid else math.inf,"mono_compatibility_risk":correlation<0,"mono_cancellation_ratio":1-(2*mid/original if original else 1),"bands":stereo_by_band(buffer)}


def dynamics(buffer,window=1024):
    values=[sum(abs(v) for v in frame)/len(frame) for frame in zip(*buffer.channels)];envelope=[sum(values[i:i+window])/max(1,len(values[i:i+window])) for i in range(0,len(values),window)];events=[]
    for i in range(1,len(envelope)):
        if envelope[i]>envelope[i-1]*1.8 and envelope[i]>.01:events.append({"start":i*window/buffer.sample_rate,"end":min(len(values),(i+1)*window)/buffer.sample_rate,"strength":envelope[i]-envelope[i-1]})
    crests=[]
    for i in range(0,len(values),window):
        block=values[i:i+window];rms=math.sqrt(sum(x*x for x in block)/max(1,len(block)));crests.append(max(block,default=0)/rms if rms else 0)
    spectral=stft(buffer,window,max(1,window//4));fluxes=[frame["spectral_flux"] for frame in spectral["frames"]];threshold=(sum(fluxes)/len(fluxes)+math.sqrt(sum((x-sum(fluxes)/len(fluxes))**2 for x in fluxes)/len(fluxes))) if fluxes else math.inf
    spectral_events=[]
    for index,frame in enumerate(spectral["frames"]):
        if frame["spectral_flux"]>threshold:
            magnitudes=frame["magnitudes"];total=sum(magnitudes);centroid=sum(f*m for f,m in zip(spectral["frequencies_hz"],magnitudes))/total if total else 0
            spectral_events.append({"start":frame["time"],"end":frame["time"]+window/buffer.sample_rate,"onset_strength":frame["spectral_flux"],"confidence":min(1,frame["spectral_flux"]/max(threshold,1e-12)-1),"transient_centroid_hz":centroid})
    return {"transient_count":len(spectral_events),"transient_density_hz":len(spectral_events)/(len(values)/buffer.sample_rate) if values else 0,"transient_events":spectral_events,"envelope_events":events,"onset_threshold":threshold if math.isfinite(threshold) else 0,"macro_dynamic_range":max(envelope,default=0)-min(envelope,default=0),"micro_dynamic_variance":sum((x-sum(envelope)/max(1,len(envelope)))**2 for x in envelope)/max(1,len(envelope)),"windowed_crest_distribution":crests,"flatness_indicator":1-(max(envelope,default=0)-min(envelope,default=0))/max(max(envelope,default=0),1e-12),"pumping_candidate":False}


def masking(first,second):
    a,b=spectrum(first),spectrum(second);bands=set(a["band_energy"])&set(b["band_energy"]);overlap={key:min(a["band_energy"][key],b["band_energy"][key])/max(a["band_energy"][key],b["band_energy"][key],1e-15) for key in bands};return {"band_overlap":overlap,"maximum_overlap":max(overlap.values(),default=0),"candidate":max(overlap.values(),default=0)>.7}


def analyze(buffer):return {"algorithm_version":ALGORITHM_VERSION,"source":buffer.source,"range_seconds":buffer.range_seconds,"metadata":buffer.metadata or {},"levels":levels(buffer),"stereo":stereo(buffer),"spectrum":spectrum(buffer),"dynamics":dynamics(buffer)}


def compare_reference(subject,reference):
    a,b=analyze(subject),analyze(reference);gain=b["levels"]["lufs_i"]-a["levels"]["lufs_i"] if math.isfinite(a["levels"]["lufs_i"]) and math.isfinite(b["levels"]["lufs_i"]) else 0
    bands={key:a["spectrum"]["band_energy"].get(key,0)-b["spectrum"]["band_energy"].get(key,0) for key in set(a["spectrum"]["band_energy"])|set(b["spectrum"]["band_energy"])}
    return {"loudness_match_gain_db":gain,"band_energy_delta":bands,"crest_delta_db":a["levels"]["crest_factor_db"]-b["levels"]["crest_factor_db"],"width_delta":a["stereo"]["width_ratio"]-b["stereo"]["width_ratio"],"true_peak_delta_db":a["levels"]["true_dbtp"]-b["levels"]["true_dbtp"],"transient_density_delta":a["dynamics"]["transient_density_hz"]-b["dynamics"]["transient_density_hz"],"subject":a,"reference":b}


def diagnose(report,reference=None,masking_report=None):
    output=[];level=report["levels"];st=report["stereo"]
    def add(code,evidence,text,recommendation,severity):output.append(Diagnosis(code,evidence,text,recommendation,severity))
    if level["overs"]:add("CLIPPING",{"overs":level["overs"]},"Samples reached the configured clipping threshold","Reduce gain before later processing and re-measure","HIGH")
    if level["true_true_peak"]>1:add("TRUE_PEAK_OVER",{"dbtp":level["true_dbtp"]},"An interpolated inter-sample over is measurable","Create a limited preview and re-measure true peak","HIGH")
    if abs(level["dc_offset"])>.01:add("DC_OFFSET",{"dc_offset":level["dc_offset"]},"A measurable DC bias is present","Use a DC-removal/high-pass stage and re-measure","MEDIUM")
    if level["headroom_db"]<1:add("LOW_HEADROOM",{"headroom_db":level["headroom_db"]},"Available sample-peak headroom is below the configured diagnostic threshold","Review gain staging before adding processing","MEDIUM")
    if st["correlation"]<0:add("PHASE_RISK",{"correlation":st["correlation"],"mono_cancellation_ratio":st["mono_cancellation_ratio"]},"Mono cancellation risk is measurable","Preview in mono and inspect the contributing source","MEDIUM")
    if level["crest_factor_db"]<4:add("LOW_CREST",{"crest_factor_db":level["crest_factor_db"]},"Peak-to-average range is low","Compare against the intended reference before further dynamics reduction","LOW")
    if masking_report and masking_report["candidate"]:add("MASKING_CANDIDATE",masking_report,"High pairwise band overlap is measurable","Inspect contribution and audition source-specific correction","MEDIUM")
    if reference:
        if abs(reference["loudness_match_gain_db"])>3:add("REFERENCE_LOUDNESS_DELTA",{"delta_db":reference["loudness_match_gain_db"]},"A material loudness difference exists against the mapped reference range","Loudness-match before subjective comparison","LOW")
    return [{**asdict(item),"source":report["source"],"range_seconds":report["range_seconds"]} for item in output]


def gain(buffer,db):
    factor=10**(db/20);return AudioBuffer(buffer.sample_rate,tuple(tuple(value*factor for value in channel) for channel in buffer.channels),buffer.source,buffer.range_seconds,buffer.metadata)


def closed_loop_peak(buffer,target_dbfs=-1):
    before=analyze(buffer);change=target_dbfs-before["levels"]["sample_peak_dbfs"] if math.isfinite(before["levels"]["sample_peak_dbfs"]) else 0;candidate=gain(buffer,change);after=analyze(candidate);return {"processor":"N0TE_GAIN","parameter_db":change,"before":before,"after":after,"improved":after["levels"]["sample_peak_dbfs"]<=target_dbfs+1e-6,"approval_required":True,"applied":False,"quality_state":"NUMERICALLY_VALIDATED","candidate":candidate}
