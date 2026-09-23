"""Shared library for the scoop-extras-cn skill (Python standard library only).

Layers:
    paths        skill_root / assets_dir / scoop_bucket_root / find_repo_root / bucket_dir
    serialize    load_manifest / dumps_manifest / write_manifest (4-space indent + CRLF + trailing newline + canonical key order)
    recipes      load_recipes / recipe_by_id / build_manifest (assets/recipes.jsonc is the single source of truth)
    checkver     detect_latest (github / url+regex / url+jsonpath+regex+replace)
    hashing      sha256_url / sha256_file
    lint        RULES / lint_manifest_text
    README      parse_summary / insert_summary_row

Every public function raises SmError on failure; the CLI turns that into a readable message.
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

USER_AGENT = "scoop-extras-cn-skill/1.0 (+https://github.com/Scoopforge/Extras-CN)"

# This bucket targets Chinese users, so a description written in Chinese is the
# repo convention rather than a defect: 57 of the 88 manifests here do it. The
# W101 "capitalized, no trailing period, <=120 chars" check is a rule about
# Latin-script phrasing and does not carry over.
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def has_cjk(text: str) -> bool:
    """True when the text contains Chinese (or CJK) characters."""
    return bool(CJK_RE.search(text))


# --------------------------------------------------------------------------
# 0. Exceptions and runtime
# --------------------------------------------------------------------------


class SmError(Exception):
    """A predictable error inside the skill; the CLI prints message and exits 1."""


def use_utf8_stdio() -> None:
    """Switch stdout/stderr to UTF-8 so non-ASCII output is not mangled on Windows.

    reconfigure is fetched through getattr because it only exists on TextIOWrapper;
    it must not raise when the console is redirected to a non-text stream.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure: Any = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# 1. Path resolution
# --------------------------------------------------------------------------


def skill_root() -> Path:
    """Skill package root (the parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return skill_root() / "assets"


def references_dir() -> Path:
    return skill_root() / "references"


# The skill is bound to one bucket, and to the copy of it Scoop itself has
# installed. The location is read from the environment at run time -- the docs
# spell it `$env:Scoop/buckets/extras-cn`, and a literal drive path never
# appears in this package, so the globally installed skill works on any machine
# and from any cwd.
SCOOP_ENV_VAR = "Scoop"
BUCKET_NAME = "extras-cn"
BUCKETS_SUBDIR = "buckets"


def is_bucket_root(path: Path) -> bool:
    """True when *path* looks like a bucket repo: bucket/ next to README.md."""
    return (path / "bucket").is_dir() and (path / "README.md").is_file()


def scoop_bucket_root() -> Path | None:
    """`$env:Scoop/buckets/extras-cn`, or None when Scoop is not installed."""
    home = os.environ.get(SCOOP_ENV_VAR, "").strip()
    if not home:
        return None
    return Path(home) / BUCKETS_SUBDIR / BUCKET_NAME


def find_repo_root(explicit: Path | None = None, start: Path | None = None) -> Path:
    """Resolve the bucket repo to operate on.

    Precedence: an explicit `--repo` path, then `$env:Scoop/buckets/extras-cn`,
    so the globally installed skill writes into the bucket Scoop actually reads
    whatever the cwd is, then the nearest ancestor of *start* (the cwd by
    default) holding both bucket/ and README.md, which covers a plain checkout
    on a machine without the Scoop environment.
    """
    if explicit is not None:
        candidate = Path(explicit)
        if not is_bucket_root(candidate):
            raise SmError(
                "--repo is not a bucket root (needs both bucket/ and README.md): "
                f"{candidate}"
            )
        return candidate.resolve()
    installed = scoop_bucket_root()
    if installed is not None and is_bucket_root(installed):
        return installed.resolve()
    base = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in [base, *base.parents]:
        if is_bucket_root(candidate):
            return candidate
    raise SmError(
        "bucket repo not found: no ancestor of the cwd holds both bucket/ and "
        f"README.md, and {installed or SCOOP_ENV_VAR} is not such a directory. "
        "Set the Scoop environment variable, pass --repo, or run from inside the repo."
    )


def bucket_dir(repo_root: Path) -> Path:
    return repo_root / "bucket"


# --------------------------------------------------------------------------
# 2. Manifest serialization
# --------------------------------------------------------------------------


# Canonical key order. Shared by the top level and nested levels; architecture has its own.
CANONICAL_ORDER = [
    "##",
    "version",
    "description",
    "homepage",
    "license",
    "notes",
    "architecture",
    "url",
    "hash",
    "pre_install",
    "installer",
    "innosetup",
    "extract_dir",
    "extract_to",
    "post_install",
    "psmodule",
    "bin",
    "shortcuts",
    "persist",
    "env_set",
    "env_add_path",
    "suggest",
    "depends",
    "uninstaller",
    "pre_uninstall",
    "post_uninstall",
    "checkver",
    "autoupdate",
]

ARCH_ORDER = ["64bit", "arm64"]
ARCH_MEMBER_ORDER = [
    "url",
    "hash",
    "pre_install",
    "installer",
    "innosetup",
    "extract_dir",
    "extract_to",
    "post_install",
    "psmodule",
    "bin",
    "shortcuts",
    "persist",
]
CHECKVER_ORDER = [
    "github",
    "url",
    "sourceforge",
    "script",
    "jsonpath",
    "xpath",
    "regex",
    "replace",
    "reverse",
    "useragent",
]
# Scoop reads these spellings as synonyms of the canonical keys above, and they
# are not typos. This bucket uses the short forms (upstream ScoopInstaller/Extras
# does too, since the shortening is described on the Scoop wiki): 44 upstream
# manifests reach for `re`, 5 for `jp`. `gen` always emits the canonical
# spelling; `lint` normalises aliases before checking a checkver block, so an
# existing manifest that uses one is not reported as "unknown keys".
CHECKVER_ALIASES = {
    "re": "regex",
    "jp": "jsonpath",
}
AUTOUPDATE_ORDER = ["architecture", "url", "hash", "extract_dir", "bin", "shortcuts"]

# Architecture key -> parameter suffix. The 64bit slot keeps the historical
# "url64" / "hash64" spelling; arm64 uses url_arm64 / hash_arm64.
# 32bit is out of scope by decision, so "32bit" is rejected as an arch value
# and url32 / hash32 are not generated. Upstream still carries such manifests
# (596 files combine 32bit with another arch); this catalog does not emit them.
ARCH_PARAM = {"64bit": "url64", "arm64": "url_arm64"}
ARCH_HASH_PARAM = {"64bit": "hash64", "arm64": "hash_arm64"}

# checkver keys Scoop resolves without any url (so no regex is required for them)
CHECKVER_SELFCONTAINED = ("github", "sourceforge")


def _sorted_by(keys: list, order: list[str]) -> list:
    """Stable sort by order; keys absent from order keep their relative position at the end."""
    index = {key: i for i, key in enumerate(order)}
    return sorted(keys, key=lambda key: index.get(key, len(index)))


def order_for(parent_key: str | None) -> list[str]:
    """Canonical key order for each nesting level."""
    if parent_key == "architecture":
        return ARCH_ORDER
    if parent_key == "checkver":
        return CHECKVER_ORDER
    if parent_key == "autoupdate":
        return AUTOUPDATE_ORDER
    if parent_key in ("installer", "uninstaller"):
        return ["script", "args"]
    if parent_key == "hash":
        return ["url", "regex", "jsonpath"]
    if parent_key in ARCH_ORDER:
        return ARCH_MEMBER_ORDER
    return CANONICAL_ORDER


def place_new_keys(original, current, parent_key: str | None = None):
    """Keep existing keys where they are and only place **new** keys at their canonical spot.

    Used by update: it neither reorders a whole old file (avoiding huge diffs)
    nor lets new fields land at the end of the file.
    """
    if not isinstance(current, dict):
        return current
    order = order_for(parent_key)
    index = {key: i for i, key in enumerate(order)}
    if isinstance(original, dict):
        original_keys = set(original.keys())
        kept = [key for key in current if key in original_keys]
        added = _sorted_by([key for key in current if key not in original_keys], order)
    else:
        kept = []
        added = _sorted_by(list(current.keys()), order)

    slots: list[str] = []
    cursor = 0
    for key in kept:
        while cursor < len(added) and index.get(added[cursor], len(order)) < index.get(
            key, len(order)
        ):
            slots.append(added[cursor])
            cursor += 1
        slots.append(key)
    slots.extend(added[cursor:])

    out = OrderedDict()
    for key in slots:
        before = original.get(key) if isinstance(original, dict) else None
        out[key] = place_new_keys(before, current[key], key)
    return out


def order_tree(obj):
    """Canonical key order: reorder the top level and the architecture keys only.

    Deeper levels are left alone -- builder output is already in canonical order,
    and update goes through preserve_order=True, which never calls this function.
    """
    if not isinstance(obj, dict):
        return obj
    out = OrderedDict()
    for key in _sorted_by(list(obj.keys()), CANONICAL_ORDER):
        value = obj[key]
        if key == "architecture" and isinstance(value, dict):
            arch_out = OrderedDict()
            for arch in _sorted_by(list(value.keys()), ARCH_ORDER):
                member = value[arch]
                if isinstance(member, dict):
                    member = OrderedDict(
                        (k, member[k])
                        for k in _sorted_by(list(member.keys()), ARCH_MEMBER_ORDER)
                    )
                arch_out[arch] = member
            out[key] = arch_out
        else:
            out[key] = value
    return out


def load_manifest(path: Path) -> OrderedDict:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SmError(f"{path.name}: not valid UTF-8 ({exc})") from exc
    try:
        data = json.loads(text, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as exc:
        raise SmError(
            f"{path.name}: JSON parse failed (line {exc.lineno} column {exc.colno}: {exc.msg})"
        ) from exc
    if not isinstance(data, dict):
        raise SmError(f"{path.name}: top level must be a JSON object")
    return data


def dumps_manifest(data: dict, preserve_order: bool = False) -> str:
    """Serialize in this repo's style: 4-space indent, CRLF endings, trailing newline, non-ASCII kept literal."""
    tree = data if preserve_order else order_tree(data)
    text = json.dumps(tree, indent=4, ensure_ascii=False)
    return text.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"


def write_manifest(path: Path, data: dict, preserve_order: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        dumps_manifest(data, preserve_order=preserve_order).encode("utf-8")
    )


# --------------------------------------------------------------------------
# 3. Recipe catalog
# --------------------------------------------------------------------------


# The catalog is data, not a Scoop manifest, so it deliberately avoids a .json
# extension. This repo's CI runs Scoop's manifest gate (Import-Bucket-Tests.ps1)
# over every file of a commit whose path matches the -Include pattern '*.json'.
# BuildHelpers filters with -like and its -Path argument only locates the
# repository, so that match is not scoped to a sub-directory: anything named
# *.json is validated against Scoop's schema.json, which requires version /
# homepage / license / url and forbids unknown top-level keys. '*.json' does not
# match 'recipes.jsonc'. The content stays strict JSON: skill-forge maps .jsonc
# to its json-parse checker, and a JSONC comment would fail that gate.
CATALOG_NAME = "recipes.jsonc"


def load_recipes() -> dict:
    path = assets_dir() / CATALOG_NAME
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict
        )
    except FileNotFoundError as exc:
        raise SmError(f"recipe catalog missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmError(f"recipe catalog is invalid JSON: {path} ({exc})") from exc


def recipe_by_id(recipe_id: str) -> dict:
    catalog = load_recipes()
    for item in catalog["recipes"]:
        if item["id"] == recipe_id:
            return item
    known = ", ".join(r["id"] for r in catalog["recipes"])
    raise SmError(f"unknown recipe '{recipe_id}'. Available: {known}")


# ---- builder helpers -----------------------------------------------------


def sub(text: str, mapping: dict) -> str:
    """Replace every {{token}} in template with the value from mapping."""
    out = str(text)
    for key, value in mapping.items():
        out = out.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{(\w+)\}\}", out)
    if leftover:
        raise SmError(
            f"template has unfilled placeholders: {', '.join(sorted(set(leftover)))}"
        )
    return out


def arch_list(arch_spec: str) -> list[str]:
    parts = [
        p.strip() for p in str(arch_spec).replace("+", ",").split(",") if p.strip()
    ]
    unknown = [p for p in parts if p not in ARCH_ORDER]
    if unknown:
        raise SmError(
            f"unsupported architecture {unknown}; available: {', '.join(ARCH_ORDER)}"
        )
    return parts or ["64bit"]


def _pick(spec: dict, *keys):
    for key in keys:
        value = spec.get(key)
        if value not in (None, ""):
            return value
    return None


def _autoupdate_url(url: str | None, version: str | None) -> str | None:
    """Rewrite the version hard-coded in a URL into $version."""
    if not url:
        return None
    if version and str(version) in url:
        return url.replace(str(version), "$version")
    return url


def _place_urls(
    manifest: OrderedDict, urls: dict, hashes: dict, force_arch: bool = False
) -> None:
    """Lift url/hash to the top level when there is one architecture and it is not forced."""
    if len(urls) == 1 and not force_arch:
        only = next(iter(urls))
        manifest["url"] = urls[only]
        if hashes.get(only):
            manifest["hash"] = hashes[only]
        return
    block = OrderedDict()
    for arch, url in urls.items():
        entry = OrderedDict()
        entry["url"] = url
        if hashes.get(arch):
            entry["hash"] = hashes[arch]
        block[arch] = entry
    manifest["architecture"] = block


def _apply_autoupdate(
    manifest: OrderedDict, urls: dict, spec: dict, extra: dict | None = None
) -> None:
    au = OrderedDict()
    if "architecture" in manifest:
        arch_au = OrderedDict()
        for arch, arch_url in urls.items():
            key = ARCH_PARAM[arch]
            template = _pick(spec, f"{key}_au", "url_au") or _autoupdate_url(
                arch_url, spec.get("version")
            )
            entry = OrderedDict()
            if template:
                entry["url"] = template
            if entry:
                arch_au[arch] = entry
        if arch_au:
            au["architecture"] = arch_au
    else:
        base_url = next(iter(urls.values())) if urls else manifest.get("url")
        template = _pick(spec, "url_au") or _autoupdate_url(
            base_url, spec.get("version")
        )
        if template:
            au["url"] = template
    if extra:
        au.update(extra)
    au.update(_au_hash_block(spec))
    # Keep the canonical autoupdate key order whatever sequence built it.
    manifest["autoupdate"] = OrderedDict(
        (key, au[key]) for key in _sorted_by(list(au.keys()), AUTOUPDATE_ORDER)
    )


def _apply_checkver(manifest: OrderedDict, spec: dict) -> None:
    """Emit checkver in one of Scoop's supported shapes.

    `github` / `sourceforge` resolve the version without any url, so they need
    no regex; `url` and `script` must be paired with one. A regex on its own
    collapses to the bare string shorthand, which Scoop applies to the
    homepage.
    """
    url = spec.get("checkver_url")
    script = spec.get("checkver_script")
    sourceforge = spec.get("checkver_sourceforge")
    github = _pick(spec, "checkver_github") or (
        None if (url or script or sourceforge) else spec.get("repo_url")
    )

    block = OrderedDict()
    if github:
        block["github"] = github
    if url:
        block["url"] = url
    if sourceforge:
        block["sourceforge"] = sourceforge
    if script:
        block["script"] = script
    for key, param in (
        ("jsonpath", "checkver_jsonpath"),
        ("xpath", "checkver_xpath"),
        ("regex", "checkver_regex"),
        ("replace", "checkver_replace"),
    ):
        if spec.get(param):
            block[key] = spec[param]
    if spec.get("checkver_useragent"):
        block["useragent"] = spec["checkver_useragent"]
    if spec.get("checkver_reverse"):
        block["reverse"] = spec["checkver_reverse"]

    if not block:
        manifest["checkver"] = "github"
        return
    if list(block.keys()) == ["regex"]:
        # Scoop falls back to $json.homepage when checkver.url is absent, so a
        # bare regex string is the shorthand for "scrape the homepage".
        manifest["checkver"] = block["regex"]
        return
    manifest["checkver"] = OrderedDict(
        (key, block[key]) for key in _sorted_by(list(block.keys()), CHECKVER_ORDER)
    )


def _apply_comment(manifest: OrderedDict, spec: dict) -> None:
    """The `##` key is the documented Scoop convention for an in-manifest comment."""
    if spec.get("comment"):
        manifest["##"] = spec["comment"]


def _apply_shortcut(manifest: OrderedDict, spec: dict) -> None:
    if spec.get("shortcut_entries"):
        manifest["shortcuts"] = spec["shortcut_entries"]
        return
    exe = spec.get("shortcut_exe")
    if not exe:
        return
    name = spec.get("shortcut_name") or spec.get("app_name") or exe
    manifest["shortcuts"] = [[exe, name]]


def _apply_bin(manifest: OrderedDict, spec: dict) -> None:
    if spec.get("bin_entries"):
        manifest["bin"] = spec["bin_entries"]
        return
    exe = spec.get("bin_exe")
    if not exe:
        return
    alias = spec.get("bin_alias")
    manifest["bin"] = [[exe, alias]] if alias else [exe]


def _apply_notes(manifest: OrderedDict, spec: dict) -> None:
    if spec.get("notes"):
        manifest["notes"] = spec["notes"]


def _apply_env(manifest: OrderedDict, spec: dict) -> None:
    if spec.get("env_set"):
        manifest["env_set"] = spec["env_set"]
    if spec.get("env_add_path"):
        manifest["env_add_path"] = spec["env_add_path"]


def _apply_uninstall_hooks(manifest: OrderedDict, spec: dict) -> None:
    if spec.get("pre_uninstall"):
        manifest["pre_uninstall"] = spec["pre_uninstall"]
    if spec.get("post_uninstall"):
        manifest["post_uninstall"] = spec["post_uninstall"]


def _arch_urls(spec: dict, arches: list[str]) -> tuple[OrderedDict, OrderedDict]:
    """Per-architecture url / hash, keyed by the arch name.

    The parameter names follow Scoop's historical spelling: 64bit keeps
    `url64`, arm64 is `url_arm64`.
    """
    urls: OrderedDict = OrderedDict()
    hashes: OrderedDict = OrderedDict()
    for arch in arches:
        urls[arch] = _pick(spec, ARCH_PARAM[arch])
        hashes[arch] = _pick(spec, ARCH_HASH_PARAM[arch], "hash") or None
    return urls, hashes


def _extract_dir_au(manifest: OrderedDict, spec: dict) -> dict:
    """autoupdate.extract_dir, but only when the directory name embeds the version.

    Upstream archives are commonly named `<app>-<version>`, so the extraction
    directory moves with every release and has to be templated too.
    """
    current = manifest.get("extract_dir")
    version = spec.get("version")
    if isinstance(current, str) and version and str(version) in current:
        return {"extract_dir": current.replace(str(version), "$version")}
    return {}


def _au_hash_block(spec: dict) -> dict:
    """The `autoupdate.hash` block, when a checksum source was declared."""
    if not spec.get("au_hash_url"):
        return {}
    block = OrderedDict([("url", spec["au_hash_url"])])
    if spec.get("au_hash_regex"):
        block["regex"] = spec["au_hash_regex"]
    return {"hash": block}


NSIS_PAYLOAD_DEFAULT = "app-64.7z"
NSIS_PAYLOAD_ARM64 = "app-arm64.7z"


# ---- the builders --------------------------------------------------------


def _base(spec: dict) -> OrderedDict:
    """`##` comment plus the five fields every manifest opens with."""
    manifest = OrderedDict()
    _apply_comment(manifest, spec)
    manifest["version"] = spec["version"]
    manifest["description"] = spec["desc"]
    manifest["homepage"] = spec["homepage"]
    manifest["license"] = spec["license"]
    _apply_notes(manifest, spec)
    return manifest


def _finish(manifest: OrderedDict, urls: dict, spec: dict) -> OrderedDict:
    """Shared tail: persist / suggest / depends / env / uninstall hooks, checkver, autoupdate."""
    if spec.get("persist"):
        manifest["persist"] = spec["persist"]
    if spec.get("suggest"):
        manifest["suggest"] = spec["suggest"]
    if spec.get("depends"):
        manifest["depends"] = spec["depends"]
    _apply_env(manifest, spec)
    _apply_uninstall_hooks(manifest, spec)
    _apply_checkver(manifest, spec)
    _apply_autoupdate(manifest, urls, spec, extra=_extract_dir_au(manifest, spec))
    return order_tree(manifest)


def _b_github_portable_zip(spec: dict) -> OrderedDict:
    arches = arch_list(spec.get("arch", "64bit"))
    manifest = _base(spec)
    urls, hashes = _arch_urls(spec, arches)
    _place_urls(manifest, urls, hashes)
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_github_nsis_7z(spec: dict) -> OrderedDict:
    arches = arch_list(spec.get("arch", "64bit"))
    per_arch_script = len(arches) > 1
    manifest = _base(spec)
    urls, hashes = _arch_urls(spec, arches)
    payload = spec.get("nsis_payload") or NSIS_PAYLOAD_DEFAULT
    script_tpl = '7z x $original_dir/`$PLUGINSDIR/{{payload}} -o"$original_dir"'
    if per_arch_script:
        block = OrderedDict()
        for arch in arches:
            entry = OrderedDict()
            entry["url"] = urls[arch]
            if hashes.get(arch):
                entry["hash"] = hashes[arch]
            if arch == "arm64" and not spec.get("nsis_payload"):
                entry["installer"] = OrderedDict(
                    [("script", sub(script_tpl, {"payload": NSIS_PAYLOAD_ARM64}))]
                )
            else:
                entry["installer"] = OrderedDict(
                    [("script", sub(script_tpl, {"payload": payload}))]
                )
            block[arch] = entry
        manifest["architecture"] = block
    else:
        manifest["url"] = urls[arches[0]]
        if hashes.get(arches[0]):
            manifest["hash"] = hashes[arches[0]]
        manifest["installer"] = OrderedDict(
            [("script", sub(script_tpl, {"payload": payload}))]
        )
    manifest["extract_dir"] = "$PLUGINSDIR"
    manifest["extract_to"] = "PLUGINSDIR"
    manifest["post_install"] = "Remove-Item -RECURSE $original_dir/`$PLUGINSDIR"
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_github_innosetup(spec: dict) -> OrderedDict:
    arches = arch_list(spec.get("arch", "64bit"))
    manifest = _base(spec)
    urls, hashes = _arch_urls(spec, arches)
    _place_urls(manifest, urls, hashes, force_arch=len(arches) > 1)
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    manifest["innosetup"] = True
    return _finish(manifest, urls, spec)


def _b_github_exe_installer(spec: dict) -> OrderedDict:
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url64"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    if spec.get("pre_install"):
        manifest["pre_install"] = spec["pre_install"]
    if spec.get("installer_file"):
        block = OrderedDict([("file", spec["installer_file"])])
        if spec.get("installer_args"):
            block["args"] = spec["installer_args"]
        manifest["installer"] = block
    elif spec.get("installer_script"):
        manifest["installer"] = OrderedDict([("script", spec["installer_script"])])
    else:
        raise SmError(
            "github-exe-installer needs installer_script, "
            "or installer_file (plus installer_args)"
        )
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    if spec.get("uninstaller_script"):
        manifest["uninstaller"] = OrderedDict([("script", spec["uninstaller_script"])])
    if spec.get("post_install"):
        manifest["post_install"] = spec["post_install"]
    return _finish(manifest, urls, spec)


def _b_github_single_exe(spec: dict) -> OrderedDict:
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url64"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_webpage_regex(spec: dict) -> OrderedDict:
    arches = arch_list(spec.get("arch", "64bit"))
    manifest = _base(spec)
    urls = OrderedDict()
    hashes = OrderedDict()
    for arch in arches:
        key = "url" if arch == "64bit" else ARCH_PARAM[arch]
        urls[arch] = _pick(spec, key, "url64")
        hashes[arch] = _pick(spec, ARCH_HASH_PARAM[arch], "hash64", "hash") or None
    _place_urls(manifest, urls, hashes, force_arch=len(arches) > 1)
    if spec.get("pre_install"):
        manifest["pre_install"] = spec["pre_install"]
    if spec.get("installer_script"):
        manifest["installer"] = OrderedDict([("script", spec["installer_script"])])
    if spec.get("innosetup"):
        manifest["innosetup"] = True
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_api_jsonpath(spec: dict) -> OrderedDict:
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    if spec.get("installer_script"):
        manifest["installer"] = OrderedDict([("script", spec["installer_script"])])
    if spec.get("uninstaller_script"):
        manifest["uninstaller"] = OrderedDict([("script", spec["uninstaller_script"])])
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_redirect_arch(spec: dict) -> OrderedDict:
    """A permanent redirect URL carries no version, so neither does autoupdate."""
    arches = arch_list(spec.get("arch", "64bit+arm64"))
    manifest = _base(spec)
    urls, _ = _arch_urls(spec, arches)
    hashes = OrderedDict((arch, None) for arch in arches)
    _place_urls(manifest, urls, hashes)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_github_git_clone(spec: dict) -> OrderedDict:
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    manifest["installer"] = OrderedDict([("script", spec["installer_script"])])
    if spec.get("uninstaller_script"):
        manifest["uninstaller"] = OrderedDict([("script", spec["uninstaller_script"])])
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    return _finish(manifest, urls, spec)


def _b_github_asset_jsonpath(spec: dict) -> OrderedDict:
    """Version comes from the GitHub API asset list, so autoupdate needs $match* placeholders."""
    arches = arch_list(spec.get("arch", "64bit"))
    manifest = _base(spec)
    urls, hashes = _arch_urls(spec, arches)
    _place_urls(manifest, urls, hashes)
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_github_source_archive(spec: dict) -> OrderedDict:
    """Source tag archive; extract_dir normally embeds the version, so autoupdate re-templates it."""
    arches = arch_list(spec.get("arch", "64bit"))
    manifest = _base(spec)
    urls, hashes = _arch_urls(spec, arches)
    _place_urls(manifest, urls, hashes)
    if spec.get("pre_install"):
        manifest["pre_install"] = spec["pre_install"]
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _msi_on_disk_name(spec: dict, default: str) -> str:
    """The file name the `#/` fragment gives the MSI; the trailing `_` keeps Scoop from unpacking it."""
    url = str(spec.get("url64") or "")
    if "#" in url:
        return url.rsplit("#", 1)[1].split("/")[-1]
    return default


def _b_github_msi(spec: dict) -> OrderedDict:
    mode = str(spec.get("msi_mode") or "extract").lower()
    if mode not in ("extract", "install"):
        raise SmError(f"msi_mode must be 'extract' or 'install', got '{mode}'")
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url64"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    name = _msi_on_disk_name(spec, "dl.msi_" if mode == "extract" else "setup.msi_")
    if mode == "extract":
        manifest["pre_install"] = [
            f'Expand-MsiArchive "$dir\\{name}" "$dir" | Out-Null',
            f'Remove-Item "$dir\\{name}"',
        ]
    else:
        admin = 'if (!(is_admin)) { error "$app requires admin rights to $cmd"; break }'
        flags = ", ".join(
            f"'{flag}'" for flag in (spec.get("msi_args") or ["/qn", "/norestart"])
        )
        target = f'"`"$dir\\{name}`""'
        manifest["pre_install"] = [
            admin,
            f"Start-Process msiexec -ArgumentList @('/i', {target}, {flags}) -Wait -Verb RunAs",
        ]
        manifest["pre_uninstall"] = [
            admin,
            f"Start-Process msiexec -ArgumentList @('/x', {target}, {flags}) -Wait -Verb RunAs",
        ]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_powershell_gallery(spec: dict) -> OrderedDict:
    manifest = _base(spec)
    urls = OrderedDict([("64bit", spec["url"])])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    if spec.get("pre_install"):
        manifest["pre_install"] = spec["pre_install"]
    else:
        manifest["pre_install"] = [
            'Remove-Item "$dir\\_rels", "$dir\\package" -Force -Recurse',
            'Remove-Item "$dir\\*Content*.xml" -Force',
        ]
    module = OrderedDict([("name", spec["psmodule_name"])])
    if spec.get("psmodule_path"):
        module["path"] = spec["psmodule_path"]
    manifest["psmodule"] = module
    return _finish(manifest, urls, spec)


def _b_non_github_single(spec: dict) -> OrderedDict:
    """One download URL from a non-GitHub source (web page, SourceForge, or a script-probed page)."""
    manifest = _base(spec)
    urls = OrderedDict([("64bit", _pick(spec, "url", "url64"))])
    hashes = OrderedDict([("64bit", _pick(spec, "hash64", "hash") or None)])
    _place_urls(manifest, urls, hashes)
    if spec.get("pre_install"):
        manifest["pre_install"] = spec["pre_install"]
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    return _finish(manifest, urls, spec)


def _b_portable_multifile(spec: dict) -> OrderedDict:
    """A portable package made of a main archive plus sidecar files, so url/hash become arrays."""
    manifest = _base(spec)
    main_url = _pick(spec, "url64", "url")
    main_hash = _pick(spec, "hash64", "hash")
    extra_urls = list(spec.get("extra_urls") or [])
    extra_hashes = list(spec.get("extra_hashes") or [])
    if len(extra_urls) != len(extra_hashes):
        raise SmError(
            f"extra_urls has {len(extra_urls)} entries but extra_hashes has "
            f"{len(extra_hashes)}; they must correspond"
        )
    manifest["url"] = [main_url, *extra_urls]
    manifest["hash"] = [main_hash, *extra_hashes]
    if spec.get("extract_dir"):
        manifest["extract_dir"] = spec["extract_dir"]
    _apply_bin(manifest, spec)
    _apply_shortcut(manifest, spec)
    # autoupdate only tracks the main download; Scoop cannot re-derive a sidecar URL.
    urls = OrderedDict([("64bit", main_url)])
    return _finish(manifest, urls, spec)


BUILDERS = {
    "github_portable_zip": _b_github_portable_zip,
    "github_nsis_7z": _b_github_nsis_7z,
    "github_innosetup": _b_github_innosetup,
    "github_exe_installer": _b_github_exe_installer,
    "github_single_exe": _b_github_single_exe,
    "webpage_regex": _b_webpage_regex,
    "api_jsonpath": _b_api_jsonpath,
    "redirect_arch": _b_redirect_arch,
    "github_git_clone": _b_github_git_clone,
    "github_asset_jsonpath": _b_github_asset_jsonpath,
    "github_source_archive": _b_github_source_archive,
    "github_msi": _b_github_msi,
    "powershell_gallery": _b_powershell_gallery,
    "non_github_single": _b_non_github_single,
    "portable_multifile": _b_portable_multifile,
}


def build_manifest(spec: dict) -> OrderedDict:
    """Build a manifest from spec['recipe']. recipe may be omitted, defaulting to default_recipe."""
    catalog = load_recipes()
    raw_id = spec.get("recipe") or catalog.get("default_recipe")
    if not isinstance(raw_id, str):
        raise SmError(
            f"no recipe given: pass spec['recipe'], or set default_recipe in {CATALOG_NAME}"
        )
    recipe_id = raw_id
    recipe = recipe_by_id(recipe_id)
    merged = dict(recipe.get("defaults") or {})
    merged.update({k: v for k, v in spec.items() if v is not None})
    merged.setdefault("app_name", spec.get("name"))
    missing = [k for k in recipe.get("required", []) if merged.get(k) in (None, "")]
    if missing:
        docs = catalog.get("param_docs", {})
        lines = [f"recipe '{recipe_id}' is missing required parameters:"]
        for key in missing:
            lines.append(f"  - {key}: {docs.get(key, '')}")
        raise SmError("\n".join(lines))
    builder = BUILDERS.get(recipe["builder"])
    if builder is None:
        raise SmError(
            f"recipe '{recipe_id}' has no implementation for builder '{recipe['builder']}'"
        )
    return builder(merged)


# --------------------------------------------------------------------------
# 4. HTTP / hashing
# --------------------------------------------------------------------------


def http_get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def sha256_url(url: str, timeout: int = 120) -> str:
    """Stream the download and compute sha256; the #/fragment anchor is dropped."""
    clean = url.split("#", 1)[0]
    request = urllib.request.Request(clean, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 5. checkver engine
# --------------------------------------------------------------------------


def github_repo_of(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"github\.com[/:]([^/]+)/([^/#?]+)", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"


def _all_urls(manifest: dict) -> list[str]:
    found: list[str] = []
    if isinstance(manifest.get("url"), str):
        found.append(manifest["url"])
    elif isinstance(manifest.get("url"), list):
        found.extend(u for u in manifest["url"] if isinstance(u, str))
    for entry in (manifest.get("architecture") or {}).values():
        if isinstance(entry, dict) and isinstance(entry.get("url"), str):
            found.append(entry["url"])
    return found


def _repo_from_manifest(manifest: dict) -> str | None:
    for url in _all_urls(manifest):
        repo = github_repo_of(url)
        if repo:
            return repo
    return github_repo_of(manifest.get("homepage"))


def _regex_version(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    if "version" in match.re.groupindex:
        return match.group("version")
    if match.groups():
        return match.group(1)
    return match.group(0)


def jsonpath_get(data, path: str):
    """Minimal jsonpath: supports $.a.b, $.a[0].b, $.a[*].b."""
    path = path.removeprefix("$")
    tokens = re.findall(r"\.([^.\[]+)|\[(\d+|\*)\]", path)
    current = data
    for name, index in tokens:
        if name:
            if not isinstance(current, dict) or name not in current:
                return None
            current = current[name]
        elif index == "*":
            if not isinstance(current, list) or not current:
                return None
            current = current[0]
        else:
            if not isinstance(current, list) or int(index) >= len(current):
                return None
            current = current[int(index)]
    return current


def normalize_checkver(checkver: dict) -> dict:
    """Map alias keys onto their canonical spelling, keeping the original order.

    A manifest may carry both spellings; the canonical key wins, which matches
    Scoop's own precedence.
    """
    out: OrderedDict = OrderedDict()
    for key, value in checkver.items():
        canonical = CHECKVER_ALIASES.get(key, key)
        if canonical in out:
            continue
        out[canonical] = value
    return out


def detect_latest(manifest: dict, name: str = "") -> tuple[str | None, str]:
    """Return (latest version, note). version is None when detection fails."""
    checkver = manifest.get("checkver")
    if checkver is None:
        return None, "manifest declares no checkver"
    if isinstance(checkver, str) and checkver.lower() != "github":
        # Regex shorthand: Scoop scrapes the homepage with it.
        homepage = manifest.get("homepage")
        if not homepage:
            return None, "bare-string checkver needs a homepage to scrape"
        checkver = OrderedDict([("url", homepage), ("regex", checkver)])
    if isinstance(checkver, str):
        repo = _repo_from_manifest(manifest)
        if not repo:
            return (
                None,
                "checkver is github but no repo can be derived from url/homepage",
            )
        checkver = OrderedDict([("github", f"https://github.com/{repo}")])
    if not isinstance(checkver, dict):
        return None, "checkver structure is invalid"
    if "re" in checkver or "jp" in checkver:
        checkver = normalize_checkver(checkver)

    if checkver.get("script"):
        return (
            None,
            "checkver uses the script form and needs a Scoop environment (bin/checkver.ps1) to probe",
        )

    target = checkver.get("github") or checkver.get("url")
    if not target:
        return None, "checkver has neither github nor url"
    if checkver.get("github"):
        repo = github_repo_of(checkver["github"]) or _repo_from_manifest(manifest)
        if not repo:
            return None, "cannot derive owner/repo from checkver.github"
        api = f"https://api.github.com/repos/{repo}/releases?per_page=30"
        try:
            payload = json.loads(http_get(api).decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            return None, f"GitHub API returned {exc.code} ({api})"
        except Exception as exc:  # noqa: BLE001
            return None, f"GitHub API request failed: {exc}"
        if not isinstance(payload, list):
            return None, "GitHub API response is not a release list"
        for release in payload:
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = release.get("tag_name") or ""
            return tag.lstrip("vV"), f"github releases of {repo}"
        return None, f"{repo} has no usable stable release"

    try:
        body = http_get(target).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return None, f"request to {target} returned {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, f"request to {target} failed: {exc}"

    if checkver.get("jsonpath"):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            return None, f"checkver.url response is not valid JSON: {exc}"
        value = jsonpath_get(payload, checkver["jsonpath"])
        if value is None:
            return None, f"jsonpath {checkver['jsonpath']} matched nothing"
        body = str(value)

    version = None
    if checkver.get("regex"):
        version = _regex_version(checkver["regex"], body)
        if version is None:
            return None, f"regex {checkver['regex']} matched nothing"
    else:
        version = body.strip()

    if checkver.get("replace"):
        template = checkver["replace"]
        match = re.search(checkver["regex"], body) if checkver.get("regex") else None
        if match and match.groupdict():
            for key, value in match.groupdict().items():
                template = template.replace("${" + key + "}", value or "")
        version = template
    return version, f"checkver {target}"


# --------------------------------------------------------------------------
# 6. lint engine
# --------------------------------------------------------------------------


RULES = OrderedDict(
    [
        ("E001", ("error", "manifest is not valid JSON / top level is not an object")),
        ("E002", ("error", "file is not UTF-8, or contains a BOM")),
        (
            "E003",
            (
                "error",
                "missing required field (version/description/homepage/license/checkver/autoupdate)",
            ),
        ),
        ("E004", ("error", "version is missing or not a string")),
        ("E005", ("error", "checkver structure is invalid")),
        (
            "E006",
            ("error", "autoupdate has neither a top-level url nor architecture.url"),
        ),
        ("E007", ("error", "architecture exists but has no 64bit entry")),
        ("E008", ("error", "shortcut entry does not start with [exe, name]")),
        ("E009", ("error", "file name does not match ^[a-z0-9][a-z0-9-]*$")),
        (
            "E010",
            (
                "error",
                "script matches a dangerous pattern (Invoke-Expression / -EncodedCommand / plaintext credentials, etc.)",
            ),
        ),
        (
            "E011",
            (
                "error",
                "hash is not a 64-char lowercase sha256 and no autoupdate hash source is given",
            ),
        ),
        (
            "W101",
            (
                "warning",
                "description ends with a period / exceeds 120 chars / starts lowercase",
            ),
        ),
        ("W102", ("warning", "download URL uses plaintext http://")),
        (
            "W103",
            (
                "warning",
                "architecture exists but autoupdate does not cover per-architecture URLs",
            ),
        ),
        (
            "W104",
            (
                "warning",
                "version hard-coded in the URL does not match the version field",
            ),
        ),
        (
            "W105",
            (
                "warning",
                "app is missing from the README summary table / listed more than once",
            ),
        ),
        (
            "W106",
            (
                "warning",
                "license is neither an SPDX identifier nor an {identifier,url} object",
            ),
        ),
        (
            "W107",
            (
                "warning",
                "version contains non-numeric characters, autoupdate may misbehave",
            ),
        ),
        (
            "W108",
            ("warning", "top-level url and architecture coexist; redundant field"),
        ),
        (
            "W109",
            (
                "warning",
                "formatting does not match .editorconfig (indentation / CRLF / trailing newline)",
            ),
        ),
        (
            "W110",
            (
                "warning",
                "autoupdate URL has no $version, so the download URL stays stale after a bump",
            ),
        ),
        (
            "W111",
            (
                "warning",
                "checkver.github points at api.github.com, which Scoop turns into a 404",
            ),
        ),
    ]
)

SPDX_LIKE = re.compile(r"^[A-Za-z0-9.+\-]+$")
DANGEROUS = [
    # Every pattern needs a launcher that actually reaches the network. Running
    # a PowerShell snippet that a *package on disk* just printed is a documented
    # Scoop idiom, not remote code execution: `miniforge-cn` ends its install
    # with `(& $dir\scripts\conda.exe shell.powershell hook) | ... | Invoke-Expression`,
    # which is verbatim what upstream conda's own hook recipe prescribes.
    (
        re.compile(
            r"Invoke-Expression|\biex\b",
            re.IGNORECASE,
        ),
        "Invoke-Expression / iex",
    ),
    (re.compile(r"-EncodedCommand", re.IGNORECASE), "-EncodedCommand"),
    (re.compile(r"IEX\s*\(", re.IGNORECASE), "IEX("),
    (re.compile(r"\| *(powershell|pwsh)\b", re.IGNORECASE), "piped into powershell"),
    (
        re.compile(
            r"(?i)(password|passwd|api[_-]?key|secret|token)\s*=\s*[\"'][^\"'$]{6,}[\"']"
        ),
        "looks like a plaintext credential",
    ),
    (
        re.compile(r"(?i)Set-ExecutionPolicy\s+Unrestricted"),
        "Set-ExecutionPolicy Unrestricted",
    ),
    (
        # A recursive delete rooted at a drive root. Written as `C:\\` inside a
        # raw string so the engine sees `C:\`; the inherited `C:\\\\` form
        # compiled to `C:\\` and could never match, making the rule dead code.
        re.compile(r"(?i)Remove-Item\s+.*-Recurse\s+.*[A-Za-z]:\\"),
        "recursive delete of a drive root",
    ),
]

# A launcher that can pull remote content into the pipeline, which is what turns
# an otherwise-innocuous Invoke-Expression into remote code execution.
REMOTE_LAUNCH_RE = re.compile(
    r"(?i)\b(?:Invoke-WebRequest|iwr|Invoke-RestMethod|irm|curl|wget|DownloadString|DownloadFile|Start-BitsTransfer|Net\.WebClient)\b"
)
# Resolving a path with one of these keeps the data on disk, so no exemption is
# needed even when a download verb appears in the same snippet.
LOCAL_RESOLVER_RE = re.compile(
    r"(?i)\b(?:Join-Path|Split-Path|Resolve-Path|Find-BucketDirectory|\$dir|\$original_dir|\$persist_dir)\b"
)


def is_dangerous_snippet(script: str) -> str | None:
    """Return the label of the first dangerous pattern in the snippet, or None.

    The plain `Invoke-Expression` / `iex` pattern is only reported when the same
    snippet has a way to reach the network and no local path resolver; that
    combination is what distinguishes a supply-chain risk from a package
    invoking a hook script it just installed. The unconditional patterns
    (`-EncodedCommand`, a plaintext credential, `Set-ExecutionPolicy
    Unrestricted`, a piped shell, a recursive delete of `C:\\`) still fire on
    their own.
    """
    for index, (pattern, label) in enumerate(DANGEROUS):
        if not pattern.search(script):
            continue
        if index == 0:
            if REMOTE_LAUNCH_RE.search(script) and not LOCAL_RESOLVER_RE.search(script):
                return label
            continue
        return label
    return None


HTTP_ALLOW_HOSTS = ("mirror.ctan.org",)
REQUIRED_FIELDS = [
    "version",
    "description",
    "homepage",
    "license",
    "checkver",
    "autoupdate",
]


class Finding:
    __slots__ = ("key", "message", "rule", "severity")

    def __init__(self, rule: str, message: str, key: str = ""):
        self.rule = rule
        self.severity = RULES.get(rule, ("error", ""))[0]
        self.message = message
        self.key = key

    @property
    def title(self) -> str:
        return RULES.get(self.rule, ("", ""))[1]

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "key": self.key,
        }


def _iter_urls(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _iter_urls(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str) and re.match(r"^https?://", node):
        yield path, node
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_urls(value, f"{path}[{index}]")


def _script_texts(manifest: dict) -> list[str]:
    texts: list[str] = []
    for key in ("pre_install", "post_install", "pre_uninstall", "post_uninstall"):
        value = manifest.get(key)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, list):
            texts.extend(v for v in value if isinstance(v, str))
    for key in ("installer", "uninstaller"):
        block = manifest.get(key)
        if isinstance(block, dict):
            script = block.get("script")
            if isinstance(script, str):
                texts.append(script)
            elif isinstance(script, list):
                texts.extend(v for v in script if isinstance(v, str))
    for entry in (manifest.get("architecture") or {}).values():
        if not isinstance(entry, dict):
            continue
        for key in ("installer", "post_install", "pre_install"):
            block = entry.get(key)
            if isinstance(block, dict) and isinstance(block.get("script"), str):
                texts.append(block["script"])
            elif isinstance(block, str):
                texts.append(block)
    return texts


def _hash_entries(manifest: dict) -> list[tuple[str, object]]:
    entries: list[tuple[str, object]] = []
    if "hash" in manifest:
        entries.append(("hash", manifest["hash"]))
    for arch, value in (manifest.get("architecture") or {}).items():
        if isinstance(value, dict) and "hash" in value:
            entries.append((f"architecture.{arch}.hash", value["hash"]))
    return entries


def lint_manifest_text(
    text: str, name: str, readme_text: str | None = None
) -> list[Finding]:
    findings: list[Finding] = []

    # E002 encoding / BOM
    if text.startswith("\ufeff"):
        findings.append(Finding("E002", "file has a BOM (should be UTF-8 without BOM)"))
    raw = text.replace("\ufeff", "")
    # W109 formatting
    formatting: list[str] = []
    if "\r\n" not in raw and "\n" in raw:
        formatting.append("line endings are LF, expected CRLF")
    if raw and not raw.endswith("\n"):
        formatting.append("missing trailing newline")
    if re.search(r"^\{\n {2,3}\"", raw, re.MULTILINE) or re.search(
        r"^\{\n {5,}\"", raw, re.MULTILINE
    ):
        formatting.append("indent is not 4 spaces")
    if formatting:
        findings.append(Finding("W109", "; ".join(formatting)))

    try:
        manifest = json.loads(raw, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as exc:
        findings.append(
            Finding(
                "E001",
                f"JSON parse failed: line {exc.lineno} column {exc.colno} {exc.msg}",
            )
        )
        return findings
    if not isinstance(manifest, dict):
        findings.append(Finding("E001", "top level is not a JSON object"))
        return findings

    # E003 required fields
    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    if missing:
        findings.append(
            Finding("E003", "missing required fields: " + ", ".join(missing))
        )

    # E004 version
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        findings.append(Finding("E004", f"invalid version: {version!r}", "version"))
        version = None

    # W101 description (the phrasing rules are Latin-script only; this bucket
    # writes 57 of its 88 descriptions in Chinese, so a Chinese string is exempt)
    desc = manifest.get("description")
    if isinstance(desc, str) and not has_cjk(desc):
        problems = []
        if desc.rstrip().endswith("."):
            problems.append("ends with a period")
        if len(desc) > 120:
            problems.append(f"length {len(desc)} > 120")
        if desc and desc[0].islower():
            problems.append("starts lowercase")
        if problems:
            findings.append(
                Finding("W101", "description " + "; ".join(problems), "description")
            )

    # W106 license
    license_value = manifest.get("license")
    if license_value is None:
        pass
    elif isinstance(license_value, str):
        if not SPDX_LIKE.match(license_value):
            findings.append(
                Finding(
                    "W106",
                    f"license '{license_value}' does not look like an SPDX identifier",
                    "license",
                )
            )
    elif isinstance(license_value, dict):
        if not (license_value.get("identifier") or license_value.get("url")):
            findings.append(
                Finding("W106", "license object lacks identifier / url", "license")
            )
    else:
        findings.append(
            Finding(
                "W106",
                f"unexpected license type: {type(license_value).__name__}",
                "license",
            )
        )

    # W107 version shape
    if version and not re.fullmatch(r"[\d.]+", version):
        findings.append(
            Finding(
                "W107",
                f"version '{version}' has non-numeric characters, autoupdate may misbehave",
                "version",
            )
        )

    # E007 architecture without 64bit
    if "architecture" in manifest:
        arches = manifest["architecture"]
        if not isinstance(arches, dict) or not arches:
            findings.append(
                Finding(
                    "E007", "architecture is empty or of the wrong type", "architecture"
                )
            )
        elif "64bit" not in arches:
            findings.append(
                Finding(
                    "E007",
                    f"architecture has no 64bit entry (present: {', '.join(arches)})",
                    "architecture",
                )
            )

    # E008 shortcuts (Scoop allows [exe, name] or [exe, name, args, icon]; the first two must be strings)
    def check_shortcuts(node, label: str) -> None:
        if node is None:
            return
        if not isinstance(node, list):
            findings.append(Finding("E008", f"{label} should be an array", "shortcuts"))
            return
        for index, item in enumerate(node):
            if (
                not isinstance(item, list)
                or len(item) < 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
            ):
                findings.append(
                    Finding(
                        "E008",
                        f"{label}[{index}] should start with [exe, name]: {item!r}",
                        "shortcuts",
                    )
                )

    check_shortcuts(manifest.get("shortcuts"), "shortcuts")
    for arch, entry in (manifest.get("architecture") or {}).items():
        if isinstance(entry, dict):
            check_shortcuts(entry.get("shortcuts"), f"architecture.{arch}.shortcuts")

    # E005 checkver / E006 autoupdate
    checkver = manifest.get("checkver")
    if isinstance(checkver, str):
        if checkver.lower() != "github" and not manifest.get("homepage"):
            # Any other string is the regex shorthand, which Scoop runs against
            # the homepage -- so without one there is nothing to scrape.
            findings.append(
                Finding(
                    "E005",
                    "bare-string checkver needs a homepage to scrape",
                    "checkver",
                )
            )
    elif isinstance(checkver, dict):
        # `re` / `jp` are Scoop synonyms, not typos: fold them onto `regex` /
        # `jsonpath` first so the checks below see one spelling throughout.
        checkver = normalize_checkver(checkver)
        if not checkver:
            findings.append(Finding("E005", "checkver is an empty object", "checkver"))
        known = set(CHECKVER_ORDER)
        unknown = [k for k in checkver if k not in known]
        if unknown:
            findings.append(
                Finding(
                    "E005",
                    "checkver has unknown keys: " + ", ".join(unknown),
                    "checkver",
                )
            )
        if not (
            checkver.get("github")
            or checkver.get("url")
            or checkver.get("script")
            or checkver.get("sourceforge")
        ):
            findings.append(
                Finding(
                    "E005",
                    "checkver lacks github / url / sourceforge / script",
                    "checkver",
                )
            )
        if checkver.get("github") or checkver.get("sourceforge"):
            # these two resolve the version themselves and need no regex
            pass
        elif checkver.get("jsonpath") or checkver.get("xpath"):
            # jsonpath / xpath already narrow the source down to the version
            # itself, so Scoop uses the picked value verbatim when there is no
            # regex. 34 of the 210 jsonpath blocks upstream omit it, and
            # hbuilderx / wpsoffice-cn in this bucket do the same.
            pass
        elif checkver.get("script"):
            if not checkver.get("regex"):
                findings.append(
                    Finding(
                        "E005",
                        "checkver using script must also provide regex",
                        "checkver",
                    )
                )
        elif not checkver.get("regex"):
            findings.append(
                Finding(
                    "E005", "checkver using url must also provide regex", "checkver"
                )
            )
    elif checkver is not None:
        findings.append(
            Finding(
                "E005",
                f"unexpected checkver type: {type(checkver).__name__}",
                "checkver",
            )
        )

    # W111 checkver.github pointing at the API host
    if isinstance(checkver, dict):
        github_value = checkver.get("github")
        if isinstance(github_value, str) and "api.github.com" in github_value:
            findings.append(
                Finding(
                    "W111",
                    "checkver.github is an api.github.com URL, but Scoop appends "
                    "'/releases/latest' to it, so the request 404s and the version "
                    "is never detected -- put the API endpoint in checkver.url instead",
                    "checkver",
                )
            )

    autoupdate = manifest.get("autoupdate")
    if isinstance(autoupdate, dict):
        has_url = bool(autoupdate.get("url")) or bool(
            isinstance(autoupdate.get("architecture"), dict)
            and any(
                isinstance(v, dict) and v.get("url")
                for v in autoupdate["architecture"].values()
            )
        )
        if not has_url:
            findings.append(
                Finding(
                    "E006",
                    "autoupdate has neither a top-level url nor architecture.url",
                    "autoupdate",
                )
            )
        unknown_au = [k for k in autoupdate if k not in AUTOUPDATE_ORDER]
        if unknown_au:
            findings.append(
                Finding(
                    "E006",
                    "autoupdate has unknown keys (possible typo): "
                    + ", ".join(unknown_au),
                    "autoupdate",
                )
            )
        if "architecture" in manifest and "architecture" not in autoupdate:
            findings.append(
                Finding(
                    "W103",
                    "manifest uses architecture but autoupdate only has a flat url; Excavator will not update per-architecture URLs",
                    "autoupdate",
                )
            )
    elif autoupdate is not None:
        findings.append(Finding("E006", "autoupdate should be an object", "autoupdate"))

    # E011 hash (Scoop allows a single sha256, a sha256 array matching the url array, or an autoupdate hash source)
    def hash_ok(value) -> bool:
        if isinstance(value, str):
            return bool(re.fullmatch(r"[0-9a-f]{64}", value)) or value.startswith("$")
        if isinstance(value, list):
            return bool(value) and all(
                isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item)
                for item in value
            )
        return isinstance(value, dict)

    hash_sources = _hash_entries(manifest)
    au_has_hash = isinstance(autoupdate, dict) and bool(autoupdate.get("hash"))
    for key, value in hash_sources:
        if hash_ok(value) or au_has_hash:
            continue
        findings.append(
            Finding(
                "E011",
                f"{key} is not a 64-char lowercase sha256 ({type(value).__name__}); add autoupdate.hash if Excavator should fill it",
                key,
            )
        )
    if (
        isinstance(manifest.get("url"), list)
        and isinstance(manifest.get("hash"), list)
        and len(manifest["url"]) != len(manifest["hash"])
    ):
        findings.append(
            Finding(
                "E011",
                f"url has {len(manifest['url'])} entries but hash has {len(manifest['hash'])}; they must correspond",
                "hash",
            )
        )

    # W110 autoupdate URL longevity
    if isinstance(autoupdate, dict) and version:
        au_urls: list[str] = []
        if isinstance(autoupdate.get("url"), str):
            au_urls.append(autoupdate["url"])
        for entry in (autoupdate.get("architecture") or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                au_urls.append(entry["url"])
        current_urls = _all_urls(manifest)
        if (
            au_urls
            and any(re.search(r"\d+\.\d+", url) for url in current_urls)
            and not any("$version" in url for url in au_urls)
        ):
            findings.append(
                Finding(
                    "W110",
                    "the download URL carries a version but the autoupdate URL has no $version -- it will not follow a bump",
                    "autoupdate",
                )
            )

    # E009 file name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        findings.append(
            Finding("E009", f"file name '{name}' does not match ^[a-z0-9][a-z0-9-]*$")
        )

    # E010 dangerous scripts
    for script in _script_texts(manifest):
        label = is_dangerous_snippet(script)
        if label:
            findings.append(
                Finding("E010", f"script matches a dangerous pattern: {label}")
            )

    # W102 http
    for path, url in _iter_urls(manifest):
        if url.startswith("http://") and not any(
            host in url for host in HTTP_ALLOW_HOSTS
        ):
            findings.append(
                Finding(
                    "W102", f"{path or 'url'} uses plaintext http: {url[:70]}", path
                )
            )

    # W104 version consistency
    if version:
        for path, url in _iter_urls(manifest):
            if path.startswith("autoupdate"):
                continue
            found = re.findall(r"\d+\.\d+(?:\.\d+)*", url)
            if not found:
                continue
            if version not in url and not any(version.startswith(f) for f in found):
                findings.append(
                    Finding(
                        "W104",
                        f"version {found[0]} in {path} does not match the version field {version}",
                        path,
                    )
                )

    # W108 top-level url alongside architecture
    if "url" in manifest and "architecture" in manifest:
        findings.append(
            Finding(
                "W108", "top-level url and architecture coexist; redundant field", "url"
            )
        )

    # W105 README listing.  The summary heading itself is localized
    # ("## ⭐️ Summary" in Extras-Plus, "## ⭐️ 总结" in Extras-CN), so the gate is
    # on whether the README actually has summary tables rather than on a fixed
    # title.  The mirror table in Extras-CN lists display names ("Blender-cn")
    # rather than manifest names ("blender-cn"), so a case-only difference is
    # reported as its own, milder finding instead of "missing".
    if readme_text is not None and parse_summary(readme_text):
        occurrences = len(re.findall(rf"\[{re.escape(name)}\]\(", readme_text))
        if occurrences == 0:
            documented = readme_app_names(readme_text)
            cased = next((n for n in documented if n.lower() == name.lower()), None)
            close = difflib.get_close_matches(name, documented, n=1, cutoff=0.75)
            if cased is not None:
                hint = (
                    f"; the README lists it as '{cased}' "
                    "(display-name casing differs from the manifest name)"
                )
            elif close:
                hint = (
                    f"; the README seems to spell it '{close[0]}' (spelling mismatch)"
                )
            else:
                hint = ""
            findings.append(
                Finding(
                    "W105", f"{name} is missing from the README summary table{hint}"
                )
            )
        elif occurrences > 1:
            findings.append(
                Finding(
                    "W105",
                    f"{name} appears {occurrences} times in the README summary table",
                )
            )

    return findings


# --------------------------------------------------------------------------
# 7. README summary table sync
# --------------------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    body = line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in body.split("|")]


def _display_width(text: str) -> int:
    """Terminal/markdown column width: East-Asian wide glyphs occupy two cells.

    The Extras-CN README is padded by hand against display width (so `中文名称`
    counts as 8, not 4). Measuring with `len()` would re-render every Chinese
    table differently on the first write, so widths are computed the same way
    a GitHub-rendered table is laid out.
    """
    return sum(
        2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text
    )


def _center(text: str, width: int) -> str:
    pad = max(width - _display_width(text), 0)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _render_table(
    header: list[str], rows: list[list[str]], widths: list[int]
) -> list[str]:
    def line(cells: list[str]) -> str:
        return (
            "| "
            + " | ".join(_center(cell, widths[i]) for i, cell in enumerate(cells))
            + " |"
        )

    out = [line(header)]
    out.append(
        "| "
        + " | ".join(
            ":" + "-" * max(widths[i] - 2, 1) + ":" for i in range(len(header))
        )
        + " |"
    )
    out.extend(line(row) for row in rows)
    return out


class SummaryTable:
    """One summary table in the README.

    Layout is detected rather than assumed, because sibling buckets differ:

    - Extras-Plus  : 3 columns, `App` in column 0, cells like `[name](url)`.
    - Extras-CN    : 4 columns, `App` in column 1 (a Chinese display name leads).
    - Extras-CN    : the mirror table has just `App | Auto-Update`, plain text cells.

    `app_col` is the index of the column that carries the app name; `rows` hold
    the raw cells, so a round-trip through `_render_table` is byte-identical.
    """

    def __init__(
        self,
        section: str,
        header: list[str],
        rows: list[list[str]],
        widths: list[int],
        app_col: int = 0,
    ):
        self.section = section
        self.header = header
        self.rows = rows
        self.widths = widths
        self.app_col = app_col

    def app_name(self, row: list[str]) -> str | None:
        """The app name in a row, whether it is linked or plain text."""
        if self.app_col >= len(row):
            return None
        return _cell_app_name(row[self.app_col])

    def find(self, name: str) -> int | None:
        for index, row in enumerate(self.rows):
            if self.app_name(row) == name:
                return index
        return None


def _cell_app_name(cell: str) -> str | None:
    """`[aboboo](http://aboboo.com)` -> 'aboboo'; `Blender-cn` -> 'Blender-cn'."""
    match = re.match(r"\[([^\]]+)\]\(", cell)
    if match:
        return match.group(1)
    text = cell.strip()
    return text or None


def _table_app_col(header: list[str]) -> int | None:
    """Column index carrying the app name, or None if this is not a summary table."""
    for index, cell in enumerate(header):
        if cell.strip().lower() == "app":
            return index
    return None


def readme_app_names(readme_text: str) -> list[str]:
    """Every app name that appears in a summary table."""
    names: list[str] = []
    for table in parse_summary(readme_text):
        for row in table.rows:
            name = table.app_name(row)
            if name:
                names.append(name)
    return names


def parse_summary(readme_text: str) -> list[SummaryTable]:
    """Every summary table under any heading, at any heading level.

    Sections nest differently per bucket: Extras-Plus tables sit directly under a
    `###` heading, while Extras-CN groups its tables under `####` sub-headings
    (with `### 跨平台` as the umbrella). The section label is therefore the
    nearest heading of any level above the table.
    """
    lines = readme_text.splitlines()
    tables: list[SummaryTable] = []
    section = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.match(r"^#{2,6}\s", line):
            section = re.sub(r"^#+\s*", "", line).strip()
            index += 1
            continue
        if line.strip().startswith("|"):
            block: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            if len(block) >= 3:
                header = _split_row(block[0])
                app_col = _table_app_col(header)
                if app_col is not None:
                    separator = _split_row(block[1])
                    widths = [len(cell) for cell in separator]
                    rows = [_split_row(row) for row in block[2:]]
                    tables.append(SummaryTable(section, header, rows, widths, app_col))
            continue
        index += 1
    return tables


def summary_entry(
    name: str, homepage: str, note: str = "", auto: str = "✓"
) -> list[str]:
    return [f"[{name}]({homepage})", auto, note]


def _heading_matches(line: str, section: str) -> bool:
    """True when `line` is a heading whose text is exactly `section`.

    Some buckets decorate headings with emoji or trailing markers, so the test
    is on the heading text rather than the raw line.
    """
    if not re.match(r"^#{2,6}\s", line):
        return False
    return re.sub(r"^#+\s*", "", line).strip() == section


def _locate_summary_table(lines: Sequence[str], section: str) -> tuple[int, int] | None:
    """Return (header row, end row) of the summary table under a section heading.

    The table may be nested under further sub-headings, so the search descends
    until it finds the first table block under the section heading.
    """
    head_index = None
    for index, line in enumerate(lines):
        if _heading_matches(line, section):
            head_index = index
            break
    if head_index is None:
        return None
    start = None
    for index in range(head_index + 1, len(lines)):
        if lines[index].strip().startswith("|"):
            start = index
            break
    if start is None or start + 1 >= len(lines):
        return None
    end = start
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    return start, end


def insert_summary_row(
    readme_text: str, section: str, name: str, homepage: str, note: str | None = None
) -> tuple[str, str]:
    """Insert or update a row in a section's summary table, in alphabetical order.

    Returns (new text, note). When note is None: an existing row keeps its note,
    a new row gets an empty one.
    """
    lines = readme_text.splitlines()
    found = _locate_summary_table(lines, section)
    if found is None:
        known = ", ".join(t.section for t in parse_summary(readme_text))
        return (
            readme_text,
            f"no summary table found for section '{section}' (present: {known}); README untouched",
        )

    header_row, end = found
    header = _split_row(lines[header_row])
    app_col = _table_app_col(header)
    if app_col is None:
        return (
            readme_text,
            f"section '{section}' has no App column; README untouched",
        )

    separator_index = header_row + 1
    widths = [len(cell) for cell in _split_row(lines[separator_index])]
    rows = [_split_row(row) for row in lines[separator_index + 1 : end]]

    # Extras-CN's mirror table is plain text (no markdown link); elsewhere the
    # app cell is a markdown link. The auto-update column follows the App column
    # and the note column (when present) follows that.
    plain = not any(re.match(r"\[[^\]]+\]\(", row[app_col]) for row in rows)
    app_cell = name if plain else f"[{name}]({homepage})"
    row = ["" for _ in header]
    row[app_col] = app_cell
    auto_col = app_col + 1
    note_col = app_col + 2
    if auto_col < len(header):
        row[auto_col] = "✓"
    if note_col < len(header):
        row[note_col] = note or ""

    position = next(
        (
            i
            for i, existing in enumerate(rows)
            if _cell_app_name(existing[app_col]) == name
        ),
        None,
    )
    if position is None:
        insert_at = len(rows)
        for index, existing in enumerate(rows):
            existing_name = _cell_app_name(existing[app_col]) or ""
            if existing_name > name:
                insert_at = index
                break
        rows.insert(insert_at, row)
        action = "inserted"
    else:
        if note is None:
            row = list(rows[position])
            row[app_col] = app_cell
        rows[position] = row
        action = "updated"

    for i in range(len(header)):
        widest = (
            max(_display_width(r[i]) for r in [header] + rows) if rows else widths[i]
        )
        widths[i] = max(widths[i], widest)

    rendered = _render_table(header, rows, widths)
    out = lines[:header_row] + rendered + lines[end:]
    newline = "\r\n" if "\r\n" in readme_text else "\n"
    return newline.join(
        out
    ) + newline, f"{action} README row in section '{section}': {name}"
