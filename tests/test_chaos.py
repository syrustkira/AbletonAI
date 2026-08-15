import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_song import SongStore
from n0te_network import NetworkPolicy,NetworkMode
from n0te_recovery import RecoveryEngine,FaultDomain
from n0te_safety import SafetyController
from n0te_media import *
class ChaosTests(unittest.TestCase):
 def test_optional_crash_network_loss_and_safe_do_not_destroy_song_or_escalate(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);song=SongStore(root).for_workspace("legacy","ableton","set")
   recovery=RecoveryEngine(root,threshold=2);recovery.record("obs",FaultDomain.STREAM_BACKEND,"drop","x");recovery.record("obs",FaultDomain.STREAM_BACKEND,"drop","x")
   safe=SafetyController(root);safe.enter("chaos")
   self.assertFalse(NetworkPolicy(NetworkMode.OFFLINE).decide("https://example.com").allowed)
   self.assertEqual(SongStore(root).get(song.song_id).song_id,song.song_id);self.assertFalse(recovery.available("obs"));self.assertFalse(safe.status()["mutation_authority"])
 def test_stream_drop_and_changed_content_never_publish_or_resume(self):
  class S:
   def status(self):return {"safe":False}
  stream=StreamEngine(MockStreamBackend(),S())
  with self.assertRaises(PermissionError):stream.go_live(StreamScene.PRODUCING,authority="user",explicit=True,reconnect=True)
  p=PublicationRecord("x","project",1,"mock");pub=PublicationEngine(S());pub.approve(p,authority="user",revision=1)
  with self.assertRaises(PermissionError):pub.publish(p,MockSocialAdapter(),current_revision=2)
  self.assertNotEqual(p.state,PublicationState.PUBLISHED)
if __name__=="__main__":unittest.main()
