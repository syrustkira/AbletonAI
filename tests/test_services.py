import tempfile,threading,time,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_services import CreatorService
from n0te_media import MockStreamBackend
class Safe:
 def __init__(self,on=False):self.on=on
 def status(self):return {"safe":self.on}
class ServiceTests(unittest.TestCase):
 def test_creator_round_trip_recipe_edit_and_artist(self):
  with tempfile.TemporaryDirectory() as td:
   s=CreatorService(Path(td),Safe(),MockStreamBackend());s.artist_update({"identity":{"name":"N0TE"}});self.assertEqual(s.artist_read()["identity"]["name"],"N0TE")
   p=s.project_create("song","clip");s.recipe(p["id"],"BEAT_BUILD",[{"name":"Hook","start":0,"end":8}],[],"9:16");edited=s.edit(p["id"],0,"CAPTION",{"text":"Hook"});self.assertEqual(edited["timeline"][0]["operations"][0]["operation"],"CAPTION")
 def test_service_does_not_bypass_public_or_live_authority(self):
  with tempfile.TemporaryDirectory() as td:
   s=CreatorService(Path(td),Safe(),MockStreamBackend());p=s.project_create("song","clip")
   with self.assertRaises(PermissionError):s.visibility(p["id"],"PUBLIC","ai",True)
   with self.assertRaises(PermissionError):s.stream_live("PRODUCING","community",True)
   r=s.publication_prepare(p["id"],"mock")
   with self.assertRaises(PermissionError):s.publication_approve(r["id"],"ai",1)
 def test_creator_service_serializes_concurrent_project_edits(self):
  with tempfile.TemporaryDirectory() as td:
   s=CreatorService(Path(td),Safe(),MockStreamBackend());p=s.project_create("song","clip");s.recipe(p["id"],"BEAT_BUILD",[{"name":"Hook","start":0,"end":8}],[],"9:16")
   original_get=s.creator.get
   def slow_get(project_id):
    project=original_get(project_id);time.sleep(.03);return project
   s.creator.get=slow_get
   errors=[]
   def edit(text):
    try:s.edit(p["id"],0,"CAPTION",{"text":text})
    except Exception as exc:errors.append(exc)
   threads=[threading.Thread(target=edit,args=(text,)) for text in ("A","B")]
   [t.start() for t in threads];[t.join() for t in threads]
   self.assertEqual(errors,[]);restored=original_get(p["id"]);self.assertEqual(len(restored.timeline[0].operations),2)
if __name__=="__main__":unittest.main()
