from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
import threading
from n0te_state import atomic_write_json


CAPABILITIES = [
    {
        "id": "capture_midi",
        "name": "Capture MIDI / recover what I just played",
        "terms": ["capture midi", "what i just played", "forgot to record", "retroactive midi", "recover midi"],
        "native_candidates": [],
        "methods": ["Ableton Live already provides Capture MIDI. N0TE should invoke/guide the native feature rather than implementing another MIDI buffer."],
    },
    {
        "id": "sound_similarity",
        "name": "Sound Similarity / find similar sounds",
        "terms": ["sound similar", "similar sample", "more like this", "similar snare", "similar kick", "find similar"],
        "native_candidates": [],
        "methods": ["Use Live's Browser/Sound Similarity first for local compatible material. N0TE's discovery layer adds song-role reasoning, tried-here memory, and web fallback when local discovery is insufficient."],
    },
    {
        "id": "audio_to_midi",
        "name": "Audio to MIDI / hum to MIDI",
        "terms": ["audio to midi", "hum to midi", "melody to midi", "harmony to midi", "drums to midi", "transcribe audio"],
        "native_candidates": [],
        "methods": ["Use Live's native audio-to-MIDI conversion first for ordinary melody/harmony/drum extraction. External transcription is a fallback for deeper or batch cases."],
    },
    {
        "id": "stem_separation",
        "name": "Stem separation",
        "terms": ["stem separation", "separate vocals", "separate drums", "separate bass", "split stems", "isolate vocal"],
        "native_candidates": [],
        "methods": ["On Live editions/versions that expose native stem separation, use it first. External separation remains a fallback/forensics option rather than a duplicate default engine."],
    },
    {
        "id": "vocal_pitch_harmony",
        "name": "Pitch correction / MIDI-controlled vocal harmony",
        "terms": ["pitch correct", "autotune", "auto tune", "vocal harmony", "harmonizer", "harmony voices", "tune vocal"],
        "native_candidates": ["Auto Shift"],
        "methods": ["When Auto Shift is available, use the native pitch/harmony engine first. N0TE adds chord-map-aware voicing decisions and routing rather than rebuilding the DSP."],
    },
    {
        "id": "midi_tools",
        "name": "MIDI Generators / Transformations",
        "terms": ["generate midi", "midi generator", "stacks", "seed", "shape", "rhythm generator", "recombine", "strum", "time warp"],
        "native_candidates": [],
        "methods": ["Live 12's MIDI Generators and Transformations should be orchestrated before inventing a redundant generator. N0TE contributes intent, motif/harmony constraints, and cross-song context."],
    },
    {
        "id": "take_lanes",
        "name": "Take lanes / comping / alternate takes",
        "terms": ["take lane", "variation lane", "alternate take", "comp", "a b take", "experiment lane"],
        "native_candidates": [],
        "methods": ["Use Live's take lanes/comping when the workflow fits. N0TE adds naming, variation intent, decision memory, and review."],
    },
    {
        "id": "project_portability",
        "name": "Project portability / collect / bounce",
        "terms": ["portable", "collect all and save", "missing samples", "bounce", "print", "freeze", "archive project"],
        "native_candidates": [],
        "methods": ["Use Live's native Collect All and Save, bounce/freeze/print workflows as the mechanical layer. N0TE audits dependencies, recommends what to commit, and preserves semantic reconstruction notes."],
    },

    {
        "id": "eq_cleanup",
        "name": "EQ / filtering / cleanup",
        "terms": ["eq", "equalizer", "filter", "high pass", "low pass", "notch", "cut mud", "remove rumble", "tone"],
        "native_candidates": ["EQ Eight", "Channel EQ", "Auto Filter"],
        "methods": ["Use EQ Eight for precise filtering/tonal shaping; Channel EQ for fast broad shaping; Auto Filter when modulation or filter character matters."],
    },
    {
        "id": "dynamic_control",
        "name": "Compression / dynamic control",
        "terms": ["compress", "compression", "level", "peaks", "control dynamics", "glue", "duck"],
        "native_candidates": ["Compressor", "Glue Compressor", "Multiband Dynamics"],
        "methods": ["Use Compressor for general/sidechain control, Glue Compressor for bus-style control, and Multiband Dynamics when frequency-dependent dynamics are genuinely needed."],
    },
    {
        "id": "sidechain_ducking",
        "name": "Sidechain ducking",
        "terms": ["sidechain", "duck", "kick bass", "vocal duck", "duck reverb", "pump"],
        "native_candidates": ["Compressor", "Glue Compressor"],
        "methods": ["Ableton can do conventional sidechain ducking natively with Compressor/Glue Compressor. Prefer an existing instance before loading another processor."],
    },
    {
        "id": "saturation_distortion",
        "name": "Saturation / distortion / harmonic density",
        "terms": ["saturate", "saturation", "distort", "distortion", "harmonics", "warmth", "drive", "clip"],
        "native_candidates": ["Saturator", "Roar", "Overdrive", "Pedal", "Dynamic Tube"],
        "methods": ["Choose the simplest device that produces the required character. A one-control Saturator job does not require a complex multiband processor."],
    },
    {
        "id": "stereo_width",
        "name": "Stereo width / mono / imaging",
        "terms": ["width", "stereo", "mono", "wider", "narrow", "imaging", "bass mono"],
        "native_candidates": ["Utility", "Chorus-Ensemble"],
        "methods": ["Utility handles simple width/mono/balance tasks. Use modulation effects only when movement/character is part of the job."],
    },
    {
        "id": "reverb_space",
        "name": "Reverb / space / depth",
        "terms": ["reverb", "space", "room", "plate", "hall", "depth", "ambience"],
        "native_candidates": ["Hybrid Reverb", "Reverb"],
        "methods": ["Prefer shared returns when multiple sources need the same space; use insertion only when the sound itself depends on the reverb."],
    },
    {
        "id": "delay_echo",
        "name": "Delay / echo",
        "terms": ["delay", "echo", "slap", "feedback", "ping pong"],
        "native_candidates": ["Echo", "Delay"],
        "methods": ["Use Delay for straightforward timing; Echo when modulation, character, filtering, or more involved feedback behavior matters."],
    },
    {
        "id": "transient_shape",
        "name": "Transient shaping / drum impact",
        "terms": ["transient", "attack", "punch", "drum punch", "snare attack", "kick attack"],
        "native_candidates": ["Drum Buss", "Compressor", "Saturator"],
        "methods": ["Drum Buss can shape transients directly; compression or clipping can sometimes solve the same perceptual job with less complexity."],
    },
    {
        "id": "limiting_loudness",
        "name": "Limiting / peak containment",
        "terms": ["limiter", "limit", "loudness", "ceiling", "true peak", "master loud"],
        "native_candidates": ["Limiter"],
        "methods": ["Use limiting only after the song/mix is ready for loudness decisions. During writing, keep enough headroom to judge contrast and transients."],
    },
    {
        "id": "multiband",
        "name": "Multiband processing",
        "terms": ["multiband", "frequency dependent", "bands", "split frequency"],
        "native_candidates": ["Multiband Dynamics", "Roar", "Audio Effect Rack", "EQ Eight"],
        "methods": ["Use multiband only when one frequency region genuinely needs different treatment. Multiple simple bands/rack chains can sometimes replace a complex plugin, but not always."],
    },
    {
        "id": "modulation",
        "name": "Parameter modulation / movement",
        "terms": ["modulate", "modulation", "lfo", "movement", "randomize", "envelope follower", "shaper"],
        "native_candidates": ["LFO", "Shaper", "Envelope Follower", "Auto Pan"],
        "methods": ["Use Max for Live modulation devices when available. N0TE should remember the command/capability even when it is not safe to automate directly."],
    },
    {
        "id": "racks_parallel",
        "name": "Racks / parallel chains / macro control",
        "terms": ["rack", "parallel", "macro", "split chain", "layer effects", "dry wet rack"],
        "native_candidates": ["Audio Effect Rack", "Instrument Rack", "Drum Rack"],
        "methods": ["Racks can reduce exposed decisions by mapping several technical controls to a few musical macros."],
    },
    {
        "id": "warp_timing",
        "name": "Warping / timing / audio alignment",
        "terms": ["warp", "warping", "timing", "stretch audio", "tempo match", "align audio"],
        "native_candidates": [],
        "methods": ["Live audio clips support warping and warp-marker editing natively. This is a clip capability, not a plugin requirement."],
    },
    {
        "id": "resample_print",
        "name": "Resampling / printing / committing audio",
        "terms": ["resample", "print", "commit", "render track", "record effects", "bounce in place", "freeze", "flatten"],
        "native_candidates": [],
        "methods": ["Live supports resampling and freeze/flatten workflows natively. N0TE should advise when to commit stable sounds but avoid freezing creative decisions too early."],
    },
    {
        "id": "midi_notes",
        "name": "MIDI note editing / variation",
        "terms": ["midi", "notes", "transpose", "humanize", "velocity", "bassline", "chords", "melody", "drum pattern"],
        "native_candidates": ["Arpeggiator", "Chord", "Scale"],
        "methods": ["N0TE can inspect and edit MIDI note pitch, timing, duration and velocity through the Live object model. Prefer duplicate-before-experiment for creative rewrites."],
    },
    {
        "id": "routing_sends",
        "name": "Routing / sends / returns",
        "terms": ["send", "return", "routing", "bus", "parallel reverb", "parallel compression", "submix"],
        "native_candidates": [],
        "methods": ["Live tracks, returns and mixer sends can accomplish many parallel/routing jobs without another plugin."],
    },
    {
        "id": "arrangement_navigation",
        "name": "Arrangement navigation / loop / locators",
        "terms": ["loop chorus", "arrangement loop", "locator", "marker", "jump section", "navigate"],
        "native_candidates": [],
        "methods": ["Live supports arrangement looping, cue/locator navigation and transport control natively. N0TE can know these commands even when the action surface remains approval-gated."],
    },
    {
        "id": "comping_recording",
        "name": "Recording / comping / takes",
        "terms": ["comp", "comping", "takes", "record vocals", "take lane", "punch in"],
        "native_candidates": [],
        "methods": ["Live supports recording, punch settings and take-lane/comping workflows natively. Recording mutations should remain explicit rather than autonomous."],
    },
]


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1}


def score_text(query: str, *parts: str) -> float:
    q = tokenize(query)
    if not q:
        return 0.0
    hay = " ".join(str(p or "") for p in parts).lower()
    ht = tokenize(hay)
    overlap = len(q & ht)
    phrase = 3.0 if query.lower().strip() and query.lower().strip() in hay else 0.0
    return overlap + phrase


class LibraryIndex:
    ROOTS = ("plugins", "audio_effects", "midi_effects", "instruments", "max_for_live", "user_library")

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.path = state_dir / "library" / "library_index.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except Exception:
            pass
        return {"version": 1, "scanned_at": None, "items": [], "errors": []}

    def scan(self, bridge, per_root_limit: int = 1200) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for root in self.ROOTS:
            try:
                result = bridge.request("browser_search", {
                    "query": "",
                    "roots": [root],
                    "limit": per_root_limit,
                    "max_depth": 12,
                    "max_visited": 30000,
                    "loadable_only": True,
                    "include_folders": False,
                    "stop_on_limit": False,
                    "match_all_terms": False,
                    "timeout": 25,
                })
                for row in (result or {}).get("results") or []:
                    if not isinstance(row, dict):
                        continue
                    item = dict(row)
                    item["scan_root"] = root
                    item["kind"] = self._kind(item)
                    item["format"] = self._format(item)
                    items.append(item)
            except Exception as exc:
                errors.append({"root": root, "error": str(exc)})
        dedup: dict[str, dict[str, Any]] = {}
        for item in items:
            key = str(item.get("uri") or item.get("path") or f"{item.get('root')}::{item.get('name')}")
            if key not in dedup:
                dedup[key] = item
        payload = {
            "version": 1,
            "scanned_at": time.time(),
            "items": sorted(dedup.values(), key=lambda x: (str(x.get("kind")), str(x.get("name", "")).lower())),
            "errors": errors,
        }
        with self._lock:
            atomic_write_json(self.path, payload)
        return payload

    def _kind(self, item: dict[str, Any]) -> str:
        root = str(item.get("scan_root") or item.get("root") or "")
        path = str(item.get("path") or "").lower()
        if root == "plugins" or "plug-ins" in path or "plugins" in path:
            return "third_party_plugin"
        if root == "max_for_live" or "max for live" in path:
            return "max_for_live"
        if root == "audio_effects":
            return "native_audio_effect"
        if root == "midi_effects":
            return "native_midi_effect"
        if root == "instruments":
            return "native_instrument"
        if root == "user_library":
            if "rack" in path:
                return "user_rack"
            if "preset" in path:
                return "user_preset"
            return "user_library"
        return root or "unknown"

    def _format(self, item: dict[str, Any]) -> str:
        text = (str(item.get("path") or "") + " " + str(item.get("name") or "")).lower()
        for fmt in ("vst3", "vst2", "audio unit", "au", "clap"):
            if fmt in text:
                return "AU" if fmt in ("audio unit", "au") else fmt.upper()
        return ""

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data = self.load()
        scored = []
        for item in data.get("items") or []:
            score = score_text(query, item.get("name", ""), item.get("path", ""), item.get("kind", ""), item.get("format", ""), item.get("category", ""), " ".join(item.get("capability_tags") or []))
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("name", "")).lower()))
        return [item for _, item in scored[:limit]]


    def apply_enrichment(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        data = self.load()
        by_key = {}
        for item in data.get("items") or []:
            key = str(item.get("uri") or item.get("path") or f"{item.get('root')}::{item.get('name')}")
            by_key[key] = item
        updates = 0
        for row in rows:
            key = str(row.get("key") or "")
            if key not in by_key:
                continue
            item = by_key[key]
            item["category"] = str(row.get("category") or "unknown")
            item["capability_tags"] = [str(x) for x in (row.get("capability_tags") or []) if str(x).strip()][:12]
            item["enrichment_confidence"] = float(row.get("confidence") or 0.0)
            item["enrichment_source"] = "model_knowledge"
            item["enrichment_note"] = str(row.get("note") or "")
            updates += 1
        data["enriched_at"] = time.time()
        with self._lock:
            atomic_write_json(self.path, data)
        return {"updated": updates, "total": len(data.get("items") or []), "enriched_at": data.get("enriched_at")}

    def enrichment_targets(self, limit: int = 240) -> list[dict[str, Any]]:
        data = self.load()
        result = []
        for item in data.get("items") or []:
            if item.get("category") and item.get("capability_tags"):
                continue
            if item.get("kind") not in ("third_party_plugin", "max_for_live", "user_rack", "user_preset"):
                continue
            key = str(item.get("uri") or item.get("path") or f"{item.get('root')}::{item.get('name')}")
            result.append({"key": key, "name": item.get("name", ""), "path": item.get("path", ""), "kind": item.get("kind", "")})
            if len(result) >= limit:
                break
        return result

    def summary(self) -> dict[str, Any]:
        data = self.load()
        counts: dict[str, int] = {}
        for item in data.get("items") or []:
            kind = str(item.get("kind") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "scanned_at": data.get("scanned_at"),
            "count": len(data.get("items") or []),
            "counts": counts,
            "errors": data.get("errors") or [],
            "enriched_at": data.get("enriched_at"),
            "capability_catalog_count": len(CAPABILITIES),
            "capability_catalog_exhaustive": False,
        }


def _device_kind(device: dict[str, Any]) -> str:
    class_name = str(device.get("class_name") or "")
    if "Plugin" in class_name:
        return "third_party_plugin"
    if "MxDevice" in class_name:
        return "max_for_live"
    return "native_or_builtin"


def current_set_devices(snapshot: dict[str, Any], bridge=None, max_depth: int = 4) -> list[dict[str, Any]]:
    """Return top-level and, when bridge access is available, devices nested in Rack chains."""
    result: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_device(device: dict[str, Any], *, group: str, track: dict[str, Any], device_index: int,
                   device_path: str, parent_device_id: int | None = None, chain_name: str = "", depth: int = 0) -> None:
        if not isinstance(device, dict) or not device.get("name"):
            return
        did = device.get("id")
        if isinstance(did, int) and did in seen:
            return
        if isinstance(did, int):
            seen.add(did)
        result.append({
            "track_group": group,
            "track_index": track.get("index"),
            "track_id": track.get("id"),
            "track_name": track.get("name", "Master" if group == "master" else ""),
            "device_index": device_index,
            "device_id": did,
            "name": device.get("name"),
            "class_name": str(device.get("class_name") or ""),
            "kind": _device_kind(device),
            "device_path": device_path,
            "parent_device_id": parent_device_id,
            "chain_name": chain_name,
            "depth": depth,
        })

        # Some bridge snapshots may already include nested chain/device data.
        if depth < max_depth:
            for c_idx, chain in enumerate(device.get("chains") or []):
                if not isinstance(chain, dict):
                    continue
                cname = str(chain.get("name") or f"Chain {c_idx + 1}")
                for n_idx, nested in enumerate(chain.get("devices") or []):
                    if isinstance(nested, dict):
                        add_device(nested, group=group, track=track, device_index=n_idx,
                                   device_path=f"{device_path} > {cname} > {nested.get('name') or n_idx}",
                                   parent_device_id=did if isinstance(did, int) else parent_device_id,
                                   chain_name=cname, depth=depth + 1)

        if bridge is None or depth >= max_depth or not isinstance(did, int):
            return
        try:
            meta = bridge.request("get", {
                "ref": {"id": did},
                "properties": ["can_have_chains"],
                "children": {"chains": 32},
                "max_depth": 2,
                "timeout": 4,
            }) or {}
            if not (meta.get("properties") or {}).get("can_have_chains"):
                return
            chains = (meta.get("children") or {}).get("chains") or []
            for c_idx, chain in enumerate(chains):
                if not isinstance(chain, dict) or not isinstance(chain.get("id"), int):
                    continue
                cname = str(chain.get("name") or f"Chain {c_idx + 1}")
                try:
                    child = bridge.request("get", {
                        "ref": {"id": chain["id"]},
                        "children": {"devices": 64},
                        "max_depth": 2,
                        "timeout": 4,
                    }) or {}
                    nested_devices = (child.get("children") or {}).get("devices") or []
                except Exception:
                    nested_devices = []
                for n_idx, nested in enumerate(nested_devices):
                    if isinstance(nested, dict):
                        add_device(nested, group=group, track=track, device_index=n_idx,
                                   device_path=f"{device_path} > {cname} > {nested.get('name') or n_idx}",
                                   parent_device_id=did, chain_name=cname, depth=depth + 1)
        except Exception:
            return

    groups = [
        ("track", snapshot.get("set", {}).get("tracks") or []),
        ("return", snapshot.get("set", {}).get("return_tracks") or []),
    ]
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        groups.append(("master", [master]))
    for group, tracks in groups:
        for track in tracks:
            if not isinstance(track, dict):
                continue
            for idx, device in enumerate(track.get("devices") or []):
                if not isinstance(device, dict):
                    continue
                add_device(device, group=group, track=track, device_index=idx,
                           device_path=str(device.get("name") or f"Device {idx + 1}"))
    return result

def capability_matches(query: str, available_names: set[str] | None = None, limit: int = 8) -> list[dict[str, Any]]:
    available_names = {n.lower() for n in (available_names or set())}
    ranked = []
    for cap in CAPABILITIES:
        score = score_text(query, cap["name"], " ".join(cap["terms"]), " ".join(cap.get("methods") or []))
        if score <= 0:
            continue
        item = dict(cap)
        item["score"] = score
        item["native_available"] = [name for name in cap.get("native_candidates") or [] if name.lower() in available_names]
        ranked.append(item)
    ranked.sort(key=lambda x: -x["score"])
    return ranked[:limit]


def resolve_tools(query: str, library: LibraryIndex, snapshot: dict[str, Any], bridge=None, deep: bool = False) -> dict[str, Any]:
    data = library.load()
    installed = data.get("items") or []
    available_names = {str(item.get("name") or "") for item in installed}
    set_devices = current_set_devices(snapshot, bridge=bridge if deep else None)
    set_hits = []
    for item in set_devices:
        score = score_text(query, item.get("name", ""), item.get("track_name", ""), item.get("kind", ""))
        if score > 0:
            row = dict(item)
            row["score"] = score
            set_hits.append(row)
    set_hits.sort(key=lambda x: -x["score"])
    return {
        "query": query,
        "capabilities": capability_matches(query, available_names),
        "current_set": set_hits[:12],
        "library": library.search(query, limit=20),
        "library_summary": library.summary(),
        "solution_order": ["already in this set", "Ableton native", "already owned plugin/rack", "N0TE extension only for a missing capability", "web/external/new only if genuinely needed"],
        "capability_catalog_count": len(CAPABILITIES),
        "capability_catalog_exhaustive": False,
        "capability_note": "The deterministic catalog is a curated production index, not the complete Ableton manual/command surface yet. Browser/library evidence and the coproducer model supplement it.",
    }
