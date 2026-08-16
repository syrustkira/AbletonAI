"""Offline N0TE DSP processors. Realtime production use requires native builds."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from n0te_audio import AudioBuffer


class Processor:
    latency_frames = 0
    def __init__(self, bypass=False): self.bypass=bypass
    def reset(self): pass
    def state(self): return {"processor":type(self).__name__, **self.__dict__, "latency_frames":self.latency_frames}
    def process(self, buffer): raise NotImplementedError
    def _done(self, source, channels):
        return source if self.bypass else AudioBuffer(source.sample_rate,tuple(tuple(c) for c in channels),source.source,source.range_seconds,source.metadata)


class Gain(Processor):
    def __init__(self, db=0, **kw): super().__init__(**kw);self.db=db
    def process(self,b):
        if self.bypass:return b
        factor=10**(self.db/20);return self._done(b,([x*factor for x in c] for c in b.channels))


class Polarity(Processor):
    def process(self,b):return b if self.bypass else self._done(b,([-x for x in c] for c in b.channels))


class StereoUtility(Processor):
    def __init__(self,width=1.0,mono=False,**kw):super().__init__(**kw);self.width=width;self.mono=mono
    def process(self,b):
        if self.bypass or len(b.channels)<2:return b
        left,right=b.channels[:2];out_l=[];out_r=[]
        for l,r in zip(left,right):
            mid=(l+r)/2;side=0 if self.mono else (l-r)*self.width/2;out_l.append(mid+side);out_r.append(mid-side)
        return self._done(b,(out_l,out_r,*b.channels[2:]))


class Delay(Processor):
    def __init__(self,frames=0,**kw):super().__init__(**kw);self.frames=max(0,int(frames));self.latency_frames=self.frames
    def process(self,b):return b if self.bypass else self._done(b,(([0.0]*self.frames+list(c))[:len(c)] for c in b.channels))


class Biquad(Processor):
    def __init__(self,kind="lowpass",frequency=1000,q=.707,gain_db=0,**kw):super().__init__(**kw);self.kind=kind;self.frequency=frequency;self.q=q;self.gain_db=gain_db
    def _coefficients(self,rate):
        if not 0<self.frequency<rate/2:raise ValueError("frequency must be below Nyquist")
        w=2*math.pi*self.frequency/rate;c=math.cos(w);s=math.sin(w);alpha=s/(2*self.q)
        if self.kind=="lowpass":b0=(1-c)/2;b1=1-c;b2=b0;a0=1+alpha;a1=-2*c;a2=1-alpha
        elif self.kind=="highpass":b0=(1+c)/2;b1=-(1+c);b2=b0;a0=1+alpha;a1=-2*c;a2=1-alpha
        elif self.kind=="peak":
            a=10**(self.gain_db/40);b0=1+alpha*a;b1=-2*c;b2=1-alpha*a;a0=1+alpha/a;a1=-2*c;a2=1-alpha/a
        else:raise ValueError("kind must be lowpass, highpass, or peak")
        return b0/a0,b1/a0,b2/a0,a1/a0,a2/a0
    def process(self,b):
        if self.bypass:return b
        b0,b1,b2,a1,a2=self._coefficients(b.sample_rate);result=[]
        for channel in b.channels:
            x1=x2=y1=y2=0.;out=[]
            for x0 in channel:
                y0=b0*x0+b1*x1+b2*x2-a1*y1-a2*y2;out.append(y0);x2,x1,y2,y1=x1,x0,y1,y0
            result.append(out)
        return self._done(b,result)


class Compressor(Processor):
    def __init__(self,threshold_db=-18,ratio=4,attack_ms=10,release_ms=100,makeup_db=0,**kw):super().__init__(**kw);self.threshold_db=threshold_db;self.ratio=max(1,ratio);self.attack_ms=attack_ms;self.release_ms=release_ms;self.makeup_db=makeup_db
    def process(self,b):
        if self.bypass:return b
        attack=math.exp(-1/(max(.01,self.attack_ms)*.001*b.sample_rate));release=math.exp(-1/(max(.01,self.release_ms)*.001*b.sample_rate));env=0.;gain=1.;channels=[[] for _ in b.channels]
        for frame in zip(*b.channels):
            peak=max(map(abs,frame));env=(attack if peak>env else release)*env+(1-(attack if peak>env else release))*peak;db=20*math.log10(max(env,1e-12));reduction=(self.threshold_db+(db-self.threshold_db)/self.ratio-db) if db>self.threshold_db else 0;target=10**((reduction+self.makeup_db)/20);gain=.9*gain+.1*target
            for i,x in enumerate(frame):channels[i].append(x*gain)
        return self._done(b,channels)


class Gate(Processor):
    def __init__(self,threshold_db=-50,release_ms=50,**kw):super().__init__(**kw);self.threshold_db=threshold_db;self.release_ms=release_ms
    def process(self,b):
        if self.bypass:return b
        threshold=10**(self.threshold_db/20);release=math.exp(-1/(max(.01,self.release_ms)*.001*b.sample_rate));gain=0.;out=[[] for _ in b.channels]
        for frame in zip(*b.channels):
            target=1. if max(map(abs,frame))>=threshold else 0.;gain=target if target>gain else release*gain
            for i,x in enumerate(frame):out[i].append(x*gain)
        return self._done(b,out)


class Clipper(Processor):
    def __init__(self,ceiling_db=-1,softness=0,**kw):super().__init__(**kw);self.ceiling_db=ceiling_db;self.softness=max(0,min(1,softness))
    def process(self,b):
        if self.bypass:return b
        ceiling=10**(self.ceiling_db/20)
        def clip(x):return ceiling*math.tanh(x/ceiling) if self.softness else max(-ceiling,min(ceiling,x))
        return self._done(b,([clip(x) for x in c] for c in b.channels))


class Limiter(Processor):
    def __init__(self,ceiling_db=-1,lookahead_ms=5,release_ms=50,**kw):super().__init__(**kw);self.ceiling_db=ceiling_db;self.lookahead_ms=lookahead_ms;self.release_ms=release_ms
    def process(self,b):
        if self.bypass:return b
        look=max(0,round(self.lookahead_ms*.001*b.sample_rate));self.latency_frames=look;self.offline_latency_compensated=True;ceiling=10**(self.ceiling_db/20);release=math.exp(-1/(max(.01,self.release_ms)*.001*b.sample_rate));out=[[] for _ in b.channels];gain=1.;frames=list(zip(*b.channels))
        # Offline rendering can inspect future samples without physically delaying
        # the output. This is equivalent to compensating the realtime lookahead
        # latency and, critically, preserves the final lookahead window.
        for i,frame in enumerate(frames):
            future=max((abs(x) for f in frames[i:min(len(frames),i+look+1)] for x in f),default=0);target=min(1,ceiling/future) if future else 1;gain=min(gain,target) if target<gain else release*gain+(1-release)*target
            for c,x in enumerate(frame):out[c].append(max(-ceiling,min(ceiling,x*gain)))
        return self._done(b,out)


class DeEsser(Processor):
    def __init__(self,frequency=6000,threshold_db=-24,ratio=4,**kw):super().__init__(**kw);self.frequency=frequency;self.threshold_db=threshold_db;self.ratio=ratio
    def process(self,b):
        high=Biquad("highpass",self.frequency).process(b);controlled=Compressor(self.threshold_db,self.ratio,2,40).process(high);res=[]
        for original,h,c in zip(b.channels,high.channels,controlled.channels):res.append([o-hh+cc for o,hh,cc in zip(original,h,c)])
        return b if self.bypass else self._done(b,res)


class TransientProcessor(Processor):
    def __init__(self,attack=0,sustain=0,**kw):super().__init__(**kw);self.attack=max(-1,min(1,attack));self.sustain=max(-1,min(1,sustain))
    def process(self,b):
        if self.bypass:return b
        fast=math.exp(-1/(.003*b.sample_rate));slow=math.exp(-1/(.080*b.sample_rate));fe=se=0.;out=[[] for _ in b.channels]
        for frame in zip(*b.channels):
            peak=max(map(abs,frame));fe=fast*fe+(1-fast)*peak;se=slow*se+(1-slow)*peak;transient=max(0,fe-se)/max(fe,1e-9);factor=max(0,1+self.attack*transient+self.sustain*(1-transient)*.5)
            for i,x in enumerate(frame):out[i].append(x*factor)
        return self._done(b,out)


def process_chain(buffer,processors):
    current=buffer;receipt=[]
    for processor in processors:current=processor.process(current);receipt.append(processor.state())
    return current,{"processors":receipt,"latency_frames":sum(x.latency_frames for x in processors),"quality":"NUMERICALLY_VALIDATED_LISTENING_PENDING"}
