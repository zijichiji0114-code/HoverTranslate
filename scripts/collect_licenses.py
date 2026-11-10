"""Copy distribution-provided legal notices into the portable application folder."""
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys

destination = ((Path(sys.argv[1]) if len(sys.argv) > 1 else
                Path(__file__).resolve().parents[1]/"dist"/"HoverTranslate")/"licenses")
destination.mkdir(parents=True, exist_ok=True)
excluded = {"pytest", "pyinstaller", "pyinstaller-hooks-contrib", "pluggy", "iniconfig", "altgraph", "pefile"}
manifest = []
for distribution in metadata.distributions():
    name = distribution.metadata.get("Name", "unknown")
    if name.lower() in excluded:
        continue
    notices = []
    for file in distribution.files or []:
        # Preserve the actual upstream terms rather than generating substitute license text.
        parts = file.parts
        if not any(token in file.name.lower() for token in ("license", "licence", "copying", "notice", "copyright")):
            continue
        source = Path(distribution.locate_file(file))
        if source.is_file():
            target = destination/name/Path(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            notices.append(str(target.relative_to(destination)))
    manifest.append({"name": name, "version": distribution.version, "notices": notices,
                     "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "")})
(destination/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
bundled = Path(__file__).resolve().parents[1]/"third_party_licenses"
if bundled.exists():
    shutil.copytree(bundled, destination/"standard-licenses", dirs_exist_ok=True)
print(f"Collected notices for {len(manifest)} packages into {destination}")
