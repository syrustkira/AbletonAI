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
def extensible_wav(path,channels,mask,frames,rate=48000):
 bits=16;width=2;data=b''.join(max(-32768,min(32767,round(value*32767))).to_bytes(2,'little',signed=True) for frame in frames for value in frame);guid=struct.pack('<H',1)+b'\0'*14
 fmt=struct.pack('<HHIIHHHHI16s',0xfffe,channels,rate,rate*channels*width,channels*width,bits,22,bits,mask,guid)
 def chunk(name,payload):return name+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)&1 else b'')
 body=b'WAVE'+chunk(b'fmt ',fmt)+chunk(b'data',data);Path(path).write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)

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
 def test_multichannel_layout_controls_loudness_claim_and_lfe_weight(self):
  with tempfile.TemporaryDirectory() as tmp:
   known=Path(tmp)/'known.wav';unknown=Path(tmp)/'unknown.wav';frames=[(.1,.1,.1,.9,.1,.1)]*4800;extensible_wav(known,6,0x3f,frames);wav(unknown,1,16,[.1]*600,channels=3)
   decoded=read_wav(known);self.assertEqual(decoded.metadata['channel_roles'],['FL','FR','FC','LFE','BL','BR']);self.assertEqual(loudness(decoded)['channel_layout_status'],'KNOWN')
   without_lfe=AudioBuffer(decoded.sample_rate,tuple(channel if role!='LFE' else tuple(0 for _ in channel) for channel,role in zip(decoded.channels,decoded.metadata['channel_roles'])),metadata=decoded.metadata)
   self.assertAlmostEqual(loudness(decoded)['lufs_i'],loudness(without_lfe)['lufs_i'],places=6)
   self.assertEqual(loudness(read_wav(unknown))['standard'],'UNKNOWN_CHANNEL_LAYOUT')
 def test_analysis_history_is_fully_scoped(self):
  with tempfile.TemporaryDirectory() as tmp:
   history=AnalysisHistory(Path(tmp)/'history.json');buffer=tone();report=analyze(buffer);history.record('song-a','workspace-a',buffer,report,{'fft':1024})
   valid=AnalysisKey.create('song-a','workspace-a',buffer,{'fft':1024},report['algorithm_version']);self.assertIsNotNone(history.current_for(valid))
   for key in (AnalysisKey.create('song-b','workspace-a',buffer,{'fft':1024},report['algorithm_version']),AnalysisKey.create('song-a','workspace-b',buffer,{'fft':1024},report['algorithm_version']),AnalysisKey.create('song-a','workspace-a',AudioBuffer(buffer.sample_rate,buffer.channels,buffer.source,(0,1),buffer.metadata),{'fft':1024},report['algorithm_version']),AnalysisKey.create('song-a','workspace-a',buffer,{'fft':2048},report['algorithm_version']),AnalysisKey.create('song-a','workspace-a',buffer,{'fft':1024},'audio-next')):self.assertIsNone(history.current_for(key))
 def test_ranged_analysis_key_survives_json_round_trip(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=tone();ranged=AudioBuffer(base.sample_rate,base.channels,'range.wav',(0.25,0.75),{'source_sha256':'range-hash'});report=analyze(ranged);path=Path(tmp)/'history.json';AnalysisHistory(path).record('song','workspace',ranged,report,{'fft':1024})
   key=AnalysisKey.create('song','workspace',ranged,{'fft':1024},report['algorithm_version']);self.assertIsNotNone(AnalysisHistory(path).current_for(key))
 def test_professional_render_formats_dither_and_receipt(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.wav';write_wav(source,tone(),RenderSpecification(8000,Encoding.FLOAT32));buffer=read_wav(source)
   for encoding in (Encoding.PCM16,Encoding.PCM24,Encoding.PCM32,Encoding.FLOAT32):
    output=Path(tmp)/f'{encoding.value}.wav';spec=RenderSpecification(8000,encoding,('FL','FR'),DitherPolicy.TPDF if encoding is Encoding.PCM16 else DitherPolicy.NONE, destination_role=DestinationRole.MASTER);receipt=render_external(source,output,buffer,'song','v1',{},True,spec,'workspace',analyze(buffer),analyze(buffer));decoded=read_wav(output)
    self.assertEqual(decoded.metadata['bits_per_sample'],16 if encoding is Encoding.PCM16 else 24 if encoding is Encoding.PCM24 else 32);self.assertEqual(receipt['render_specification']['encoding'],encoding.value);self.assertEqual(receipt['workspace_id'],'workspace');self.assertTrue(receipt['source_sha256'])
   quiet=AudioBuffer(8000,((0.,)*256,),metadata={'source_sha256':'seed'});none=Path(tmp)/'none.wav';dithered=Path(tmp)/'tpdf.wav';write_wav(none,quiet,RenderSpecification(8000,Encoding.PCM16,dither=DitherPolicy.NONE));write_wav(dithered,quiet,RenderSpecification(8000,Encoding.PCM16,dither=DitherPolicy.TPDF));self.assertNotEqual(none.read_bytes(),dithered.read_bytes())
 def test_mastering_optimizer_is_bounded_and_selects_best(self):
  plan=mastering_candidate(tone(amplitude=.5),-16,-2,maximum_iterations=4,tolerance=.2)
  self.assertLessEqual(len(plan['candidates_explored']),4);scores=[row['score'] for row in plan['candidates_explored']];self.assertAlmostEqual(plan['objective']['selected_score'],min(scores));self.assertLessEqual(abs(plan['objective']['target_error_after']),abs(plan['objective']['target_error_before'])+1e-6);self.assertTrue(plan['approval_required']);self.assertFalse(plan['applied']);self.assertIn('LISTENING_ACCEPTANCE_PENDING',plan['quality_status'])
  guarded=mastering_candidate(tone(amplitude=.9),-8,-1,minimum_crest_preservation=2,maximum_iterations=10);self.assertEqual(len(guarded['candidates_explored']),1)
 def test_streaming_level_scan_is_bounded_and_matches_full_decode(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'long.wav';write_wav(path,tone(seconds=4),RenderSpecification(8000,Encoding.PCM24));streamed=stream_levels_wav(path,257);full=levels(read_wav(path))
   self.assertAlmostEqual(streamed['sample_peak'],full['sample_peak'],places=6);self.assertAlmostEqual(streamed['rms'],full['rms'],places=6);self.assertLess(streamed['memory_bound_bytes'],10000);self.assertIn('gated_loudness',streamed['deferred_metrics'])
 def test_streaming_level_scan_rejects_truncated_declared_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'truncated.wav';wav(path,1,16,[.1,.2,.3,.4]);raw=bytearray(path.read_bytes());offset=raw.index(b'data');declared=struct.unpack_from('<I',raw,offset+4)[0];struct.pack_into('<I',raw,offset+4,declared+64);path.write_bytes(raw)
   with self.assertRaisesRegex(ValueError,'Truncated WAVE data chunk'):stream_levels_wav(path,2)
if __name__=="__main__":unittest.main()
