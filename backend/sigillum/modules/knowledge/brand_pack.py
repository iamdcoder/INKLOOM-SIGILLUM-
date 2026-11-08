import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from sigillum.config import get_settings

class BrandPack:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().brand_pack_path
        self._cache: dict[str, Any] = {}

    def _load(self, filename: str) -> dict[str, Any]:
        if filename not in self._cache:
            path = self.root / filename
            if not path.exists():
                raise FileNotFoundError(f"Brand Knowledge Pack file is missing: {path}")
            self._cache[filename] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[filename]

    @property
    def brand(self): return self._load("brand.json")
    @property
    def facts(self): return self._load("facts.json").get("facts", [])
    @property
    def policies(self): return self._load("policies.json").get("policies", [])
    @property
    def terminology(self): return self._load("terminology.json")
    @property
    def voice(self): return self._load("voice.json")
    @property
    def assets(self): return self._load("asset_manifest.json")
    @property
    def sources(self):
        path = self.root / "sources.json"
        if not path.exists():
            return {"schema_version": "1.0.0", "sources": []}
        return self._load("sources.json")

    def version(self) -> str:
        return str(self.brand.get("pack_version", "unknown"))

    def snapshot(self) -> dict[str, Any]:
        """Return the complete knowledge context used by a review.

        The returned object is JSON-serialisable and deliberately includes every
        record family that can influence a finding. Reviews persist this snapshot
        so an operator can reconstruct the inputs even if the fixture changes.
        """
        snapshot = {
            "brand": self.brand,
            "facts": self.facts,
            "policies": self.policies,
            "terminology": self.terminology,
            "voice": self.voice,
            "assets": self.assets,
        }
        # Older immutable packs predate the source registry. Do not silently
        # change their historical fingerprint merely because this property exists.
        if (self.root / "sources.json").exists():
            snapshot["sources"] = self.sources
        return snapshot

    def fingerprint(self) -> str:
        """Return a stable SHA-256 fingerprint of the complete pack snapshot."""
        canonical = json.dumps(
            self.snapshot(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(canonical).hexdigest()
