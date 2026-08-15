import tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_song import SongStore
from n0te_project_graph import GraphNode,ProjectGraph,PortabilityEngine
class SongGraphTests(unittest.TestCase):
 def test_legacy_mapping_is_idempotent_and_non_destructive(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); old=root/"songs"/"legacy.json";old.parent.mkdir();old.write_text('{"stage":"MIX"}')
   store=SongStore(root);a=store.for_workspace("legacy","ableton","set-1","/tmp/A.als");b=store.for_workspace("legacy","ableton","set-1","/tmp/A.als")
   self.assertEqual(a.song_id,b.song_id);self.assertEqual(old.read_text(),'{"stage":"MIX"}')
   logic=store.attach_workspace(a.song_id,"logic","future-1")
   self.assertEqual(logic.song_id,a.song_id);self.assertEqual(len(store.get(a.song_id).workspaces),2)
 def test_graph_round_trip_retains_host_extensions(self):
  graph=ProjectGraph("song","ws",[GraphNode("c","ClipRegion","Scene Clip","AbletonSessionClip",extensions={"slot":3})])
  loaded=ProjectGraph.from_dict(graph.to_dict());self.assertEqual(loaded.nodes[0].extensions["slot"],3)
 def test_graph_validation_rejects_unknown_edges_and_kinds(self):
  with self.assertRaises(ValueError):ProjectGraph("s","w",[GraphNode("x","LogicLiveLoop")]).validate()
  with self.assertRaises(ValueError):ProjectGraph("s","w",[GraphNode("x","Track")],[{"from":"x","to":"missing"}]).validate()
 def test_manifest_is_non_destructive_and_reports_unavailable_plugin(self):
  with tempfile.TemporaryDirectory() as td:
   song=SongStore(Path(td)).for_workspace("legacy","ableton","set")
   graph=ProjectGraph(song.song_id,song.workspaces[0].workspace_id,[GraphNode("t","Track"),GraphNode("d","Device",data={"portable":False})])
   manifest=PortabilityEngine().survival_manifest(song,graph,decisions=[{"id":"d1"}])
   self.assertTrue(manifest["export_candidates_only"]);self.assertFalse(manifest["portability"]["destructive_conversion"])
   self.assertEqual(manifest["portability"]["results"][1]["status"],"UNAVAILABLE")
if __name__=="__main__":unittest.main()
