import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_observability import ObservabilityEngine
from n0te_panic import *
class Adapter:
 def __init__(self,result):self.result=result;self.ops=[]
 def execute_panic(self,ops):self.ops=ops;return self.result
class ObservabilityPanicTests(unittest.TestCase):
 def test_observability_reports_truth_and_labels_unsupported_metrics(self):
  x=ObservabilityEngine().sample(daw_online=False,ai={"state":"OFF"},network={"mode":"OFFLINE"},community={"state":"OFF"},safety={"safe":True},recovery={"recovery_required":False,"quarantine":{"camera":{}}},song="s",workspace="w")
  self.assertGreater(x["compact"]["rss_bytes"],0);self.assertEqual(x["compact"]["ai_state"],"OFF");self.assertFalse(x["compact"]["daw_online"]);self.assertIn("audio_xruns",x["detailed"]["unsupported_metrics"])
 def test_panic_clears_only_after_confirmed_host_execution(self):
  p=MusicalPanic();n=GeneratedNote("w","vision","synth",1,60);p.note_on(n);p.set_sustain("w","vision","synth",1,True)
  unknown=Adapter("UNKNOWN");self.assertFalse(p.execute("w",unknown));self.assertIn(n,p.notes);self.assertTrue(p.recovery_required)
  confirmed=Adapter("CONFIRMED");self.assertTrue(p.execute("w",confirmed));self.assertNotIn(n,p.notes);self.assertTrue(any(x["operation"]=="ALL_SOUND_OFF" for x in confirmed.ops))
 def test_panic_does_not_touch_other_workspace(self):
  p=MusicalPanic();a=GeneratedNote("a","n0te","x",1,60);b=GeneratedNote("b","n0te","x",1,61);p.note_on(a);p.note_on(b);p.execute("a",Adapter("CONFIRMED"));self.assertEqual(p.notes,{b})
if __name__=="__main__":unittest.main()
