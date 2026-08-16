import tempfile,unittest,uuid,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_lifecycle import *
class LifecycleTests(unittest.TestCase):
 def test_locked_version_reopen_is_explicit_and_preserves_parent(self):
  with tempfile.TemporaryDirectory() as td:
   s=VersionStore(Path(td));v=s.create("song",VersionState.RELEASE_LOCKED,"approved")
   with self.assertRaises(ValueError):s.reopen(v.id,"")
   reopened=s.reopen(v.id,"new mix");self.assertEqual(reopened.parent_id,v.id);self.assertIsNotNone(s.get(v.id))
 def test_reconnect_does_not_flush_sync_and_vault_never_queues(self):
  with tempfile.TemporaryDirectory() as td:
   o=SyncOutbox(Path(td));i=o.queue("song","r2","r1")
   self.assertEqual(o.ready(network_reconnected=True),[]);self.assertEqual(o.ready(explicit_ids=[i.id])[0]["revision"],"r2")
   with self.assertRaises(PermissionError):o.queue("vault","r1",private_vault=True)
 def test_knowledge_prunes_cache_but_protects_canonical_pinned_and_rights(self):
  with tempfile.TemporaryDirectory() as td:
   s=KnowledgeStore(Path(td));records=[
    KnowledgeRecord("cache",KnowledgeClass.CACHE,EditorialState.DRAFT,"x","derived",time.time()),
    KnowledgeRecord("canon",KnowledgeClass.CANONICAL,EditorialState.PUBLISHED,"x","product",time.time()),
    KnowledgeRecord("pin",KnowledgeClass.IMPORTED,EditorialState.DRAFT,"x","user",time.time(),pinned=True),
    KnowledgeRecord("rights",KnowledgeClass.PROJECT,EditorialState.DRAFT,"x","rights",time.time())]
   for r in records:s.save(r)
   self.assertEqual(s.prune(3),["cache"]);self.assertTrue((s.root/"canon.json").exists() and (s.root/"rights.json").exists())
if __name__=="__main__":unittest.main()
