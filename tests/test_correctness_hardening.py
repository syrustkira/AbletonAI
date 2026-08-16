import math,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from n0te_audio import AudioBuffer
from n0te_dsp import Gain,Polarity,Biquad,Compressor,Gate,Clipper,Limiter,DeEsser,TransientProcessor

def constant(value,count=12000,rate=48000):return AudioBuffer(rate,(tuple([value]*count),),'fixture')
def sine(frequency,amplitude=.5,count=12000,rate=48000):return AudioBuffer(rate,(tuple(amplitude*math.sin(2*math.pi*frequency*i/rate) for i in range(count)),),'fixture')
def rms(channel,start=0):
 values=channel[start:];return math.sqrt(sum(x*x for x in values)/len(values))

class FloatSignalPathTests(unittest.TestCase):
 def test_gain_reference_ratios_and_headroom(self):
  source=constant(.8,32)
  self.assertAlmostEqual(Gain(0).process(source).channels[0][0],.8)
  self.assertAlmostEqual(Gain(6).process(source).channels[0][0],.8*10**.3)
  self.assertAlmostEqual(Gain(-6).process(source).channels[0][0],.8*10**-.3)
  self.assertGreater(Gain(6).process(source).channels[0][0],1)
 def test_polarity_and_eq_preserve_float_headroom(self):
  self.assertEqual(Polarity().process(constant(1.5,4)).channels[0],(-1.5,)*4)
  output=Biquad('peak',1000,.707,6).process(sine(1000,1.1)).channels[0]
  self.assertGreater(max(output),1);self.assertGreater(rms(output,2000),rms(sine(1000,1.1).channels[0],2000)*1.7)
 def test_filter_transfer_functions(self):
  hp=Biquad('highpass',1000);lp=Biquad('lowpass',1000)
  low=sine(100);high=sine(8000)
  self.assertLess(rms(hp.process(low).channels[0],2000),rms(low.channels[0],2000)*.2)
  self.assertGreater(rms(hp.process(high).channels[0],2000),rms(high.channels[0],2000)*.8)
  self.assertGreater(rms(lp.process(low).channels[0],2000),rms(low.channels[0],2000)*.8)
  self.assertLess(rms(lp.process(high).channels[0],2000),rms(high.channels[0],2000)*.2)
 def test_compressor_static_ratio_without_unrelated_clipping(self):
  below=Compressor(-12,4,.01,10).process(constant(.1)).channels[0]
  above=Compressor(-12,4,.01,10).process(constant(2)).channels[0]
  self.assertAlmostEqual(rms(below,4000),.1,delta=.01)
  expected_db=-12+(20*math.log10(2)+12)/4
  self.assertAlmostEqual(20*math.log10(rms(above,4000)),expected_db,delta=.5);self.assertGreater(max(above),1)
 def test_gate_clipper_limiter_and_transient_contracts(self):
  gated=Gate(-20,20).process(AudioBuffer(48000,((.001,)*1000+(.5,)*1000+(.001,)*1000,))).channels[0]
  self.assertLess(max(gated[:500]),.0001);self.assertGreater(min(gated[1200:1800]),.49);self.assertGreater(gated[2001],gated[-1])
  ceiling=10**(-6/20);hard=Clipper(-6).process(AudioBuffer(48000,((2.,-2.,.25),))).channels[0];self.assertEqual(hard[:2],(ceiling,-ceiling))
  soft=Clipper(-1,.5).process(AudioBuffer(48000,((.1,.2,.4),))).channels[0];self.assertTrue(0<soft[0]<soft[1]<soft[2]<1)
  hot=Gain(6).process(constant(.8,4096));self.assertGreater(max(hot.channels[0]),1);limited=Limiter(-3,1,20).process(hot);self.assertLessEqual(max(map(abs,limited.channels[0])),10**(-3/20)+1e-9);self.assertEqual(len(limited.channels[0]),4096)
  impulse=AudioBuffer(48000,((0.,)*50+(1.5,)+(0.2,)*500,));cut=TransientProcessor(-1,0).process(impulse).channels[0];boost=TransientProcessor(1,0).process(impulse).channels[0]
  self.assertLess(cut[50],1.5);self.assertGreater(boost[50],1.5)
 def test_deesser_changes_high_band_more_than_low(self):
  low=sine(300,.5);high=sine(8000,.5)
  low_delta=rms(tuple(a-b for a,b in zip(low.channels[0],DeEsser(5000,-30,8).process(low).channels[0])),2000)
  high_delta=rms(tuple(a-b for a,b in zip(high.channels[0],DeEsser(5000,-30,8).process(high).channels[0])),2000)
  self.assertGreater(high_delta,low_delta*5)

if __name__=='__main__':unittest.main()
