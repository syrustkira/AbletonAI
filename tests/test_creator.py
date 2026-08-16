import tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_creator import *
class Safe:
 def __init__(self,on=False):self.on=on
 def status(self):return {"safe":self.on}
class CreatorTests(unittest.TestCase):
 def test_artist_world_is_advisory_and_atomic(self):
  with tempfile.TemporaryDirectory() as td:
   s=ArtistWorldStore(Path(td));s.save(ArtistWorld(identity={"name":"N0TE"},visual={"colors":["black"]}))
   self.assertFalse(s.guidance(ArtistMode.USE_ARTIST_WORLD)["blocking"]);self.assertEqual(s.guidance(ArtistMode.TRY_SOMETHING_DIFFERENT)["guidance"],{})
 def test_public_requires_explicit_user_and_safe_denies(self):
  with tempfile.TemporaryDirectory() as td:
   e=CreatorEngine(Path(td),Safe());p=e.create("song","clip")
   for authority in ("ai","community","gesture","reconnect"):
    with self.assertRaises(PermissionError):e.set_visibility(p,Visibility.PUBLIC,authority=authority,explicit=True)
   self.assertEqual(e.set_visibility(p,Visibility.PUBLIC,authority="user",explicit=True).visibility,Visibility.PUBLIC)
   with self.assertRaises(PermissionError):CreatorEngine(Path(td),Safe(True)).set_visibility(p,Visibility.PUBLIC,authority="user",explicit=True)
 def test_recipe_and_quick_edit_work_ai_off(self):
  with tempfile.TemporaryDirectory() as td:
   e=CreatorEngine(Path(td),Safe());p=e.create("song","build");plan=e.recipe(p,Recipe.BEAT_BUILD,[{"name":"Chorus","start":32,"end":48}],[{"id":"mark"}],aspect="9:16")
   self.assertFalse(plan["ai_required"]);self.assertEqual(plan["marks"],["mark"]);self.assertEqual(plan["revision"],2)
   e.add_edit(p,0,EditOperation.CAPTION,text="Chorus arrives");self.assertEqual(p.timeline[0].operations[0]["operation"],"CAPTION")
 def test_recipe_change_invalidates_prior_publication_approval_and_persists_revision(self):
  with tempfile.TemporaryDirectory() as td:
   e=CreatorEngine(Path(td),Safe());p=e.create("song","clip");e.set_visibility(p,Visibility.PUBLIC,authority="user",explicit=True);approved_revision=p.revision;self.assertTrue(p.publication_approved)
   e.recipe(p,Recipe.STUDIO_STORY,[{"name":"Verse","start":0,"end":8}],[]);self.assertGreater(p.revision,approved_revision);self.assertFalse(p.publication_approved)
   restored=e.get(p.id);self.assertEqual(restored.revision,p.revision);self.assertFalse(restored.publication_approved)
if __name__=="__main__":unittest.main()
