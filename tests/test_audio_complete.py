import math,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"));sys.path.insert(0,str(ROOT/"scripts"))
from n0te_audio import *
from n0te_audio_workflow import *
from n0te_dsp import *

def tone(rate=8000,seconds=1,frequency=1000,amplitude=.2,channels=2):
 values=tuple(amplitude*math.sin(2*math.pi*frequency*i/rate) for i in range(rate*seconds));return AudioBuffer(rate,tuple(values for _ in range(channels)),"fixture")
def wav(path,tag,bits,values,channels=1,rate=48000):
 width=bits//8;data=bytearray()
 for value in values:
  if tag==3:data.extend(struct.pack("<f",value))
  else:
   integer=round(value*(1<<(bits-1)));integer=max(-(1<<(bits-1)),min((1<<(bits-1))-1,integer));data.extend(integer.to_bytes(width,"little",signed=True))
 fmt=struct.pack("<HHIIHH",tag,channels,rate,rate*channels*width,channels*width,bits)
 def chunk(name,payload):return name+struct.pack("<I",len(payload))+payload+(b"\0" if len(payload)&1 else b"")
 body=b"WAVE"+chunk(b"fmt ",fmt)+chunk(b"data",bytes(data));Path(path).write_bytes(b"RIFF"+struct.pack("<I",len(body))+body)

class AudioCompleteTests(unittest.TestCase):
 def test_pcm_24_32_and_float_decode(self):
  with tempfile.TemporaryDirectory() as tmp:
   for tag,bits in ((1,24),(1,32),(3,32)):
    path=Path(tmp)/f"{tag}-{bits}.wav";wav(path,tag,bits,[-.5,0,.5]);buffer=read_wav(path)
    self.assertEqual(buffer.metadata["bits_per_sample"],bits);self.assertAlmostEqual(buffer.channels[0][-1],.5,places=5)
 def test_loudness_gating_series_and_lra(self):
  result=loudness(tone(seconds=4));self.assertTrue(math.isfinite(result["lufs_i"]));self.assertGreater(len(result["momentary_series"]),1);self.assertGreaterEqual(result["lra_lu"],0)
 def test_fft_stft_finds_tone_and_flux(self):
  result=stft(tone(seconds=1),1024,256);self.assertGreater(len(result["frames"]),1);index=max(range(len(result["frames"][0]["magnitudes"])),key=result["frames"][0]["magnitudes"].__getitem__);self.assertAlmostEqual(result["frequencies_hz"][index],1000,delta=50)
 def test_true_peak_and_reference_comparison(self):
  impulse=AudioBuffer(48000,((0,.9,-.9,0)*512,),"impulse");peak=true_peak(impulse);self.assertGreaterEqual(peak["true_peak"],peak["sample_peak"])
  delta=compare_reference(tone(amplitude=.1),tone(amplitude=.2));self.assertGreater(delta["loudness_match_gain_db"],5)
 def test_dsp_chain_is_functional_and_bypass_safe(self):
  source=tone(amplitude=.8);processors=[Gain(-3),Polarity(),StereoUtility(.5),Delay(10),Biquad("highpass",100),Compressor(),Gate(-80),Clipper(-3,.2),Limiter(-2),DeEsser(3000),TransientProcessor(-.2,.1)]
  output,receipt=process_chain(source,processors);self.assertEqual(len(output.channels[0]),len(source.channels[0]));self.assertEqual(len(receipt["processors"]),11);self.assertEqual(Gain(-20,bypass=True).process(source),source)
 def test_stem_mastering_render_and_history(self):
  with tempfile.TemporaryDirectory() as tmp:
   mix=tone(amplitude=.2);stems=analyze_stems({"alpha":tone(frequency=100),"beta":tone(frequency=1000)},mix);self.assertIn("alpha::beta",stems["pairwise_masking"])
   plan=mastering_candidate(mix,-18,-2);source=Path(tmp)/"source.wav";write_pcm16(source,mix);output=Path(tmp)/"version.wav";receipt=render_external(source,output,plan["candidate"],"song","v1",plan["processor_receipt"],True);self.assertTrue(output.exists());self.assertEqual(receipt["authority"],"EXTERNAL_AUDIO_RENDER")
   history=AnalysisHistory(Path(tmp)/"history.json");item=history.record("song","workspace",mix,analyze(mix));self.assertEqual(item["song_id"],"song")
 def test_render_never_overwrites_original_and_requires_authority(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"audio.wav";write_pcm16(path,tone())
   with self.assertRaises(PermissionError):render_external(path,path,tone(),"song","v1",{},True)
   with self.assertRaises(PermissionError):render_external(path,Path(tmp)/"out.wav",tone(),"song","v1",{},False)
if __name__=="__main__":unittest.main()
