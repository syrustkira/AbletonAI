import unittest,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_media import *
class Safe:
 def __init__(self,on=False):self.on=on
 def status(self):return {"safe":self.on}
class MediaTests(unittest.TestCase):
 def test_motion_is_untrusted_and_authority_targets_are_denied(self):
  m=MotionMapper();e=MotionEvent("clap",.9,{},time.time())
  self.assertEqual(m.map(e,GestureMapping("clap","MARK"))["authority"],"untrusted_motion")
  with self.assertRaises(PermissionError):m.map(e,GestureMapping("clap","PUBLISH"))
  self.assertIsNone(m.map(MotionEvent("clap",.2,{},0),GestureMapping("clap","MARK")))
 def test_stream_test_is_local_and_live_requires_user_not_reconnect(self):
  b=MockStreamBackend();e=StreamEngine(b,Safe());self.assertEqual(e.test(StreamScene.PRODUCING).state,StreamState.TESTING);self.assertFalse(b.live)
  for authority in ("ai","community","gesture"):
   with self.assertRaises(PermissionError):e.go_live(StreamScene.PRODUCING,authority=authority,explicit=True)
  with self.assertRaises(PermissionError):e.go_live(StreamScene.PRODUCING,authority="user",explicit=True,reconnect=True)
  self.assertEqual(e.go_live(StreamScene.PERFORMANCE,authority="user",explicit=True).state,StreamState.LIVE);e.enter_safe();self.assertFalse(b.live)
 def test_publication_invalidates_after_revision_and_safe_denies(self):
  r=PublicationRecord("p","project",1,"mock");e=PublicationEngine(Safe());e.approve(r,authority="user",revision=1)
  with self.assertRaises(PermissionError):e.publish(r,MockSocialAdapter(),current_revision=2)
  r.state=PublicationState.DRAFT;e.approve(r,authority="user",revision=1);self.assertEqual(e.publish(r,MockSocialAdapter(),current_revision=1).state,PublicationState.PUBLISHED)
  s=PublicationEngine(Safe(True));r2=PublicationRecord("q","project",1,"mock");s.approve(r2,authority="user",revision=1)
  with self.assertRaises(PermissionError):s.publish(r2,MockSocialAdapter(),current_revision=1)
if __name__=="__main__":unittest.main()
