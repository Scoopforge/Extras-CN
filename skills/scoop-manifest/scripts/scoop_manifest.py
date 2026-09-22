"""scoop-manifest skill CLI: three trigger commands -- generate / update / lint.

    python scripts/scoop_manifest.py generate   # generate: build a manifest from a recipe and fill it in
    python scripts/scoop_manifest.py update     # update: edit fields / bump version / rehash / probe upstream
    python scripts/scoop_manifest.py lint       # lint: check bucket/ against this repo's CI standard

All three subcommands accept short aliases: gen, upd, check.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Let the script run from any cwd: the shared library sits next to it
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sm_lib as L

# Windows consoles default to a non-UTF-8 codepage, which mangles non-ASCII output
L.use_utf8_stdio()


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _json_arg(raw: str, flag: str):
    """Parse a JSON command-line value, e.g. '["app.exe", "App"]'."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise L.SmError(f"{flag} needs valid JSON, got {raw!r} ({exc})") from exc


def _key_value_pairs(items: list[str], flag: str) -> OrderedDict:
    """Turn repeated KEY=VALUE flags into an object, e.g. --env-set A=1 B=2."""
    pairs: OrderedDict = OrderedDict()
    for item in items:
        if "=" not in item:
            raise L.SmError(f"{flag} expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        pairs[key] = value
    return pairs


def add_repo_argument(parser: argparse.ArgumentParser, main_parser=None) -> None:
    """Declare --repo so it works before *and* after the subcommand.

    argparse binds an option to whichever parser declares it, so declaring it
    only on the top-level parser makes `scoop_manifest.py lint --repo X` fail
    with "unrecognized arguments" even though `--repo X lint` works. Declaring
    it in both places and merging the two values in repo_root_from keeps both
    spellings usable. The subcommand declares it with `default=argparse.SUPPRESS`
    so that omitting it does not overwrite an earlier top-level value with None.
    """
    kwargs = {"help": "bucket repo root (walks upwards by default)"}
    if main_parser is not None:
        kwargs["default"] = argparse.SUPPRESS
    parser.add_argument("--repo", **kwargs)


def repo_root_from(args) -> Path:
    given = getattr(args, "repo", None)
    return L.find_repo_root(Path(given) if given else None)


def validate_section(spec: dict, catalog: dict, root: Path | None = None) -> None:
    """Reject a --section the target README has no summary table for.

    Otherwise `insert_summary_row` returns the text untouched with a message,
    and the caller reports success while nothing was written.

    The authority is the README itself, because a bucket may nest tables under
    `####` sub-headings that the flat `summary_sections` catalogue does not
    list (Extras-CN's 跨平台 umbrella covers 外语学习 / 学术研究 / 软件开发 /
    日常使用). The catalogue is only a fallback when there is no README.
    """
    section = spec.get("section")
    if not section:
        return
    known: list[str] = []
    if root is not None:
        readme = readme_text_of(root)
        if readme is not None:
            known = [table.section for table in L.parse_summary(readme)]
    if not known:
        known = list(catalog.get("summary_sections") or [])
    if known and section not in known:
        raise L.SmError(
            f"unknown README section '{section}'; available: {', '.join(known)}"
        )


def report_findings(findings: list[L.Finding], strict: bool = False) -> int:
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    for finding in errors:
        print(f"  [ERROR] {finding.rule}  {finding.message}")
    for finding in warnings:
        print(f"  [WARN] {finding.rule}  {finding.message}")
    print(f"  -> {len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        return 1
    if strict and warnings:
        return 1
    return 0


def readme_text_of(root: Path) -> str | None:
    path = root / "README.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_text_keep_eol(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


# --------------------------------------------------------------------------
# Command 1 - generate
# --------------------------------------------------------------------------


def cmd_generate(args: argparse.Namespace) -> int:
    catalog = L.load_recipes()

    if args.list_recipes:
        print(f"Available recipes (assets/{L.CATALOG_NAME}):\n")
        for recipe in catalog["recipes"]:
            print(f"  {recipe['id']}  —  {recipe['label']}")
            print(f"      When: {recipe['when']}")
            print(f"      Required: {', '.join(recipe['required'])}")
            if recipe.get("optional"):
                print(f"      Optional: {', '.join(recipe['optional'])}")
            print(
                f"      Samples: {', '.join(recipe['refs']) or 'see references/coverage.md'}\n"
            )
        print("See references/manifest-fields.md for parameter docs")
        return 0

    specs = _collect_specs(args, catalog)
    if not specs:
        print(
            "error: nothing to generate. Pass --name/--recipe directly, or --from a spec file.",
            file=sys.stderr,
        )
        return 2

    root = repo_root_from(args)
    for spec in specs:
        validate_section(spec, catalog, root)

    out_dir = Path(args.out).resolve() if args.out else L.bucket_dir(root)
    exit_code = 0

    for spec in specs:
        exit_code |= _generate_one(spec, args, root, out_dir)
    return exit_code


def _collect_specs(args: argparse.Namespace, catalog: dict) -> list[dict]:
    specs: list[dict] = []
    if args.from_file:
        path = Path(args.from_file)
        if not path.is_file():
            raise L.SmError(f"--from file does not exist: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise L.SmError(f"--from file is invalid JSON: {exc}") from exc
        specs = payload if isinstance(payload, list) else [payload]
    specs = [dict(s) for s in specs if isinstance(s, dict)]

    overrides = {
        "name": args.name,
        "recipe": args.recipe,
        "version": args.version,
        "desc": args.desc,
        "homepage": args.homepage,
        "license": args.license,
        "comment": args.comment,
        "url": args.url,
        "url64": args.url64,
        "url_arm64": args.url_arm64,
        "hash": args.hash_value,
        "hash64": args.hash64,
        "hash_arm64": args.hash_arm64,
        "repo_url": args.repo_url,
        "arch": args.arch,
        "extract_dir": args.extract_dir,
        "extract_to": args.extract_to,
        "nsis_payload": args.nsis_payload,
        "shortcut_exe": args.shortcut_exe,
        "shortcut_name": args.shortcut_name,
        "shortcut_entries": _json_arg(args.shortcut_entry, "--shortcut-entry")
        if args.shortcut_entry
        else None,
        "bin_exe": args.bin_exe,
        "bin_alias": args.bin_alias,
        "bin_entries": _json_arg(args.bin_entry, "--bin-entry")
        if args.bin_entry
        else None,
        "persist": args.persist,
        "env_add_path": args.env_add_path,
        "env_set": _key_value_pairs(args.env_set, "--env-set")
        if args.env_set
        else None,
        "notes": args.notes,
        "suggest": args.suggest,
        "depends": args.depends,
        "installer_script": args.installer_script,
        "installer_file": args.installer_file,
        "installer_args": args.installer_arg,
        "uninstaller_script": args.uninstaller_script,
        "post_install": args.post_install,
        "pre_install": args.pre_install,
        "pre_uninstall": args.pre_uninstall,
        "post_uninstall": args.post_uninstall,
        "msi_mode": args.msi_mode,
        "msi_args": args.msi_arg,
        "psmodule_name": args.psmodule_name,
        "psmodule_path": args.psmodule_path,
        "extra_urls": args.extra_url,
        "extra_hashes": args.extra_hash,
        "checkver_url": args.checkver_url,
        "checkver_regex": args.checkver_regex,
        "checkver_jsonpath": args.checkver_jsonpath,
        "checkver_xpath": args.checkver_xpath,
        "checkver_replace": args.checkver_replace,
        "checkver_reverse": args.checkver_reverse,
        "checkver_useragent": args.checkver_useragent,
        "checkver_script": args.checkver_script,
        "checkver_sourceforge": args.checkver_sourceforge,
        "au_hash_url": args.au_hash_url,
        "au_hash_regex": args.au_hash_regex,
        "url_au": args.url_au,
        "section": args.section,
    }
    overrides = {k: v for k, v in overrides.items() if v not in (None, "")}

    if not specs:
        specs = [{}]
    for spec in specs:
        spec.update(overrides)
        spec.setdefault("recipe", catalog.get("default_recipe"))
    return specs


def _resolve_hash(spec: dict, args: argparse.Namespace, name: str) -> None:
    """Fill hash into spec from --hash / --hash-from-file / --fetch-hash."""
    if args.hash_from_file:
        digest = L.sha256_file(Path(args.hash_from_file))
        spec["hash64"] = digest
        if spec.get("url_arm64"):
            spec.setdefault("hash_arm64", digest)
        print(f"  hash (from {Path(args.hash_from_file).name}): {digest}")
        return
    if not args.fetch_hash:
        return
    targets = []
    if spec.get("url64"):
        targets.append(("hash64", spec["url64"]))
    if spec.get("url_arm64"):
        targets.append(("hash_arm64", spec["url_arm64"]))
    if spec.get("url") and not spec.get("url64"):
        targets.append(("hash64", spec["url"]))
    for key, url in targets:
        try:
            digest = L.sha256_url(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] {name}: download failed, {key} left empty -- {exc}")
            continue
        spec[key] = digest
        print(f"  {key}: {digest}")


def _generate_one(
    spec: dict, args: argparse.Namespace, root: Path, out_dir: Path
) -> int:
    name = spec.get("name")
    if not name:
        print(
            "error: spec has no name (app name = file name without .json)",
            file=sys.stderr,
        )
        return 2

    print(f"[generate] {name}")
    _resolve_hash(spec, args, name)
    try:
        manifest = L.build_manifest(spec)
    except L.SmError as exc:
        print(f"  [FAIL] {exc}", file=sys.stderr)
        return 1

    text = L.dumps_manifest(manifest)
    findings = L.lint_manifest_text(text, name)
    blockers = [f for f in findings if f.severity == "error"]

    if args.print_json or args.dry_run:
        print(text, end="")
    if blockers:
        print("  generated manifest failed self-check:")
        report_findings(findings)
        if not args.force:
            print(
                "  write aborted; fix the parameters or pass --force.", file=sys.stderr
            )
            return 1

    target = out_dir / f"{name}.json"
    if target.exists() and not args.force and not args.dry_run:
        print(
            f"  [FAIL] {target} already exists; use update to change it, or --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"  (dry-run) would write {target}")
    else:
        L.write_manifest(target, manifest)
        print(f"  OK wrote {target}")

    if findings and not blockers:
        report_findings(findings)

    if not args.no_readme and not args.dry_run:
        _sync_readme(root, spec, manifest, args)

    if (
        not blockers
        and "hash" not in manifest
        and not any(
            "hash" in entry for entry in (manifest.get("architecture") or {}).values()
        )
    ):
        print(
            "  hint: no hash yet. Run update --name "
            + name
            + " --rehash, or bin/checkhashes.ps1 from the repo."
        )
    return 0


def _sync_readme(
    root: Path, spec: dict, manifest: dict, args: argparse.Namespace
) -> None:
    readme = readme_text_of(root)
    if readme is None:
        print("  [SKIP] no README.md at the repo root")
        return
    section = spec.get("section")
    if not section:
        print("  [SKIP] no --section given; README summary table untouched")
        return
    updated, message = L.insert_summary_row(
        readme, section, spec["name"], manifest.get("homepage", ""), note=None
    )
    if updated == readme:
        print(f"  README: {message}")
        return
    if args.dry_run:
        print(f"  (dry-run) README: {message}")
        return
    write_text_keep_eol(root / "README.md", updated)
    print(f"  OK README: {message}")


# --------------------------------------------------------------------------
# Command 2 - update
# --------------------------------------------------------------------------


def _tokenize(path: str) -> list[str]:
    """Normalize shortcuts.0.1 / shortcuts[0][1] into ['shortcuts', '0', '1']."""
    tokens = re.findall(r"[^.\[\]]+", path)
    if not tokens:
        raise L.SmError(f"invalid path: {path!r}")
    return tokens


def _step(current, token: str):
    if isinstance(current, list):
        if not token.isdigit():
            raise L.SmError(f"array index must be numeric, got {token!r}")
        index = int(token)
        if index >= len(current):
            raise L.SmError(
                f"array index out of range: {token} (length {len(current)})"
            )
        return current[index]
    if isinstance(current, dict):
        if token not in current:
            current[token] = OrderedDict()
        return current[token]
    raise L.SmError(f"parent of {token!r} is neither an object nor an array")


def _set_path(root, tokens: list[str], value) -> None:
    current = root
    for token in tokens[:-1]:
        current = _step(current, token)
    last = tokens[-1]
    if isinstance(current, list):
        if not last.isdigit():
            raise L.SmError(f"array index must be numeric, got {last!r}")
        index = int(last)
        if index >= len(current):
            raise L.SmError(f"array index out of range: {last} (length {len(current)})")
        current[index] = value
        return
    if isinstance(current, dict):
        current[last] = value
        return
    raise L.SmError(f"parent of {last!r} is neither an object nor an array")


def _del_path(root, tokens: list[str]) -> None:
    current = root
    for token in tokens[:-1]:
        if isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise L.SmError(f"path not found: {'.'.join(tokens)}")
    last = tokens[-1]
    if isinstance(current, list) and last.isdigit() and int(last) < len(current):
        del current[int(last)]
        return
    if isinstance(current, dict) and last in current:
        del current[last]
        return
    raise L.SmError(f"path not found: {'.'.join(tokens)}")


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _rewrite_version(manifest: dict, old: str, new: str) -> int:
    """Replace the old hard-coded version in every download URL; returns the replacement count."""
    count = 0

    def walk(node, key_path=""):
        nonlocal count
        if isinstance(node, dict):
            for key in list(node.keys()):
                child_path = f"{key_path}.{key}" if key_path else key
                if (
                    isinstance(node[key], str)
                    and "url" in child_path
                    and not child_path.startswith("checkver")
                ):
                    if old and old in node[key]:
                        node[key] = node[key].replace(old, new)
                        count += 1
                else:
                    walk(node[key], child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{key_path}[{index}]")

    walk(manifest)
    return count


def _rehash(manifest: dict, name: str) -> int:
    """Re-download every architecture URL and refill hash. Returns the success count."""
    done = 0
    tasks: list[tuple[str, str]] = []
    if isinstance(manifest.get("url"), str):
        tasks.append(("hash", manifest["url"]))
    for arch, entry in (manifest.get("architecture") or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("url"), str):
            tasks.append((f"architecture.{arch}.hash", entry["url"]))
    for key, url in tasks:
        try:
            digest = L.sha256_url(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] {name}: {key} download failed -- {exc}")
            continue
        if key == "hash":
            manifest["hash"] = digest
        else:
            arch = key.split(".")[1]
            manifest["architecture"][arch]["hash"] = digest
        print(f"  {key} = {digest}")
        done += 1
    return done


def cmd_update(args: argparse.Namespace) -> int:
    root = repo_root_from(args)
    bucket = L.bucket_dir(root)
    names = list(args.name or [])
    if args.all:
        names = [p.stem for p in sorted(bucket.glob("*.json"))]
    if not names:
        print(
            "error: name the target with --name <app>, or use --all.", file=sys.stderr
        )
        return 2

    exit_code = 0
    for name in names:
        exit_code |= _update_one(name, args, root, bucket)
    return exit_code


def _update_one(name: str, args: argparse.Namespace, root: Path, bucket: Path) -> int:
    path = bucket / f"{name}.json"
    if not path.is_file():
        print(f"[update] {name}  ->  [FAIL] not found: {path}", file=sys.stderr)
        return 1

    print(f"[update] {name}")
    manifest = L.load_manifest(path)
    original = copy.deepcopy(manifest)
    version_before = manifest.get("version")
    changed: list[str] = []

    # explicit field replacement
    for item in args.set or []:
        if "=" not in item:
            print(f"  [FAIL] --set expects KEY=VALUE: {item}", file=sys.stderr)
            return 1
        key, raw = item.split("=", 1)
        try:
            _set_path(manifest, _tokenize(key), _parse_value(raw))
        except L.SmError as exc:
            print(f"  [FAIL] --set {key}: {exc}", file=sys.stderr)
            return 1
        changed.append(f"set {key}")
    for key in args.unset or []:
        try:
            _del_path(manifest, _tokenize(key))
            changed.append(f"unset {key}")
        except L.SmError as exc:
            print(f"  [WARN] --unset: {exc}")

    # shortcut fields
    shortcuts = {
        "description": args.desc,
        "homepage": args.homepage,
        "license": args.license,
        "notes": args.notes,
    }
    for key, value in shortcuts.items():
        if value is not None:
            manifest[key] = value
            changed.append(key)
    if args.checkver_url:
        manifest.setdefault("checkver", OrderedDict())
        if isinstance(manifest["checkver"], str):
            manifest["checkver"] = OrderedDict()
        manifest["checkver"]["url"] = args.checkver_url
        changed.append("checkver.url")
    if args.checkver_regex:
        manifest.setdefault("checkver", OrderedDict())
        if isinstance(manifest["checkver"], str):
            manifest["checkver"] = OrderedDict()
        manifest["checkver"]["regex"] = args.checkver_regex
        changed.append("checkver.regex")
    for key, value in (
        ("url", args.url),
        ("url64", args.url64),
        ("url_arm64", args.url_arm64),
    ):
        if value is None:
            continue
        if key == "url" and "architecture" not in manifest:
            manifest["url"] = value
        elif key == "url64":
            manifest.setdefault("architecture", OrderedDict())
            manifest["architecture"].setdefault("64bit", OrderedDict())["url"] = value
        elif key == "url_arm64":
            manifest.setdefault("architecture", OrderedDict())
            manifest["architecture"].setdefault("arm64", OrderedDict())["url"] = value
        else:
            manifest["url"] = value
        changed.append(key)

    # version bump
    if args.version:
        old = str(version_before) if version_before else ""
        manifest["version"] = args.version
        replaced = _rewrite_version(manifest, old, args.version)
        changed.append(
            f"version {old} -> {args.version} ({replaced} URL replacement(s))"
        )

    # recompute hash
    if args.rehash:
        count = _rehash(manifest, name)
        changed.append(f"rehash ({count} hash value(s) updated)")
    if args.hash_from_file:
        digest = L.sha256_file(Path(args.hash_from_file))
        if "architecture" in manifest:
            for entry in manifest["architecture"].values():
                if isinstance(entry, dict):
                    entry["hash"] = digest
        else:
            manifest["hash"] = digest
        changed.append(f"hash (from {Path(args.hash_from_file).name})")

    # probe the upstream version
    if args.checkver:
        latest, note = L.detect_latest(manifest, name)
        if latest is None:
            print(f"  latest version: detection failed ({note})")
        else:
            same = latest == str(manifest.get("version"))
            mark = "up to date" if same else "update available"
            print(f"  latest version: {latest}  [{mark}]  <- {note}")
            if not same and args.apply:
                old = str(manifest.get("version") or "")
                manifest["version"] = latest
                replaced = _rewrite_version(manifest, old, latest)
                changed.append(
                    f"version {old} -> {latest} ({replaced} URL replacement(s))"
                )
                if args.rehash:
                    pass
                if not args.rehash:
                    print(
                        "  hint: version bumped, hash must be recomputed -- run again with --rehash."
                    )
            elif not same:
                print("  (not written; add --apply to bump the version)")

    if not changed:
        print("  nothing to change.")
        return 0

    # key order: keep the original order by default and only slot new fields into their canonical spot; --reorder rewrites everything
    if args.reorder:
        manifest = L.order_tree(manifest)
    else:
        manifest = L.place_new_keys(original, manifest)

    text = L.dumps_manifest(manifest, preserve_order=not args.reorder)
    findings = L.lint_manifest_text(text, name, readme_text=None)
    errors = [f for f in findings if f.severity == "error"]

    print("  changes: " + "; ".join(changed))
    if errors:
        print("  changes failed self-check:")
        report_findings(findings)
        if not args.force:
            print(
                "  write aborted; review the changes or pass --force.", file=sys.stderr
            )
            return 1

    if args.dry_run:
        if args.print_json:
            print(text, end="")
        print("  (dry-run) nothing written")
    else:
        write_text_keep_eol(path, text)
        print(f"  OK wrote {path}")

    if args.readme and not args.dry_run:
        _sync_readme(root, {"name": name, "section": args.section}, manifest, args)

    if errors:
        report_findings(findings)
    return 0


# --------------------------------------------------------------------------
# Command 3 - lint
# --------------------------------------------------------------------------


def cmd_lint(args: argparse.Namespace) -> int:
    if args.rules:
        print("Lint rule catalog (same source as references/lint-rules.md):\n")
        for rule, (severity, title) in L.RULES.items():
            tag = "Error" if severity == "error" else "Warning"
            print(f"  {rule}  [{tag}]  {title}")
        return 0

    root = repo_root_from(args)
    bucket = L.bucket_dir(root)
    if args.path:
        targets = [Path(p) for p in args.path]
    elif args.name:
        targets = [bucket / f"{n}.json" for n in args.name]
    else:
        targets = sorted(bucket.glob("*.json"))

    missing = [t for t in targets if not t.is_file()]
    for path in missing:
        print(f"  [ERROR] not found: {path}", file=sys.stderr)

    readme = readme_text_of(root)
    results: list[tuple[str, list[L.Finding]]] = []
    fixed = 0
    for path in targets:
        if not path.is_file():
            continue
        raw = path.read_bytes().decode("utf-8", "replace")
        if args.fix_format:
            new_text, changelog = _fix_format(path, raw)
            if changelog:
                raw = new_text
                fixed += 1
                print(f"[fix] {path.name}: {'; '.join(changelog)}")
                if not args.dry_run:
                    write_text_keep_eol(path, new_text)
        findings = L.lint_manifest_text(raw, path.stem, readme_text=readme)
        results.append((path.stem, findings))

    total_errors = sum(1 for _, f in results for x in f if x.severity == "error")
    total_warnings = sum(1 for _, f in results for x in f if x.severity == "warning")
    dirty = [(name, findings) for name, findings in results if findings]

    if args.json:
        payload = {
            "files": len(results),
            "errors": total_errors,
            "warnings": total_warnings,
            "reports": {
                name: [x.as_dict() for x in findings] for name, findings in dirty
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for name, findings in dirty:
            print(f"[{name}]")
            report_findings(findings)
        print(
            f"\nlint finished: {len(results)} manifest(s); "
            f"{total_errors} error(s), {total_warnings} warning(s); "
            f"{len(results) - len(dirty)} fully clean."
        )
        if args.fix_format:
            print(
                f"formatting fixed: {fixed} file(s)"
                + (" (dry-run, nothing written)" if args.dry_run else "")
            )

    if missing:
        return 1
    if total_errors:
        return 1
    if args.strict and total_warnings:
        return 1
    return 0


def _fix_format(path: Path, raw: str) -> tuple[str, list[str]]:
    """Fix formatting only: indentation / line endings / trailing newline. JSON semantics unchanged."""
    changelog: list[str] = []
    try:
        manifest = json.loads(raw, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError:
        return raw, []
    if not isinstance(manifest, dict):
        return raw, []
    new_text = L.dumps_manifest(manifest, preserve_order=True)
    if new_text != raw:
        if "\r\n" not in raw and "\n" in raw:
            changelog.append("line endings LF -> CRLF")
        if raw and not raw.endswith("\n"):
            changelog.append("added trailing newline")
        if not changelog:
            changelog.append("normalized to 4-space indent")
        return new_text, changelog
    return raw, []


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scoop_manifest.py",
        description="Scoop bucket manifest generator: generate / update / lint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  generate: python scripts/scoop_manifest.py gen --name myapp --recipe github-nsis-7z \\\n"
            "            --version 1.2.3 --desc 'My app' --homepage https://example.com \\\n"
            "            --license MIT --url64 <url> --shortcut-exe myapp.exe --section 'General Use'\n"
            "  update:   python scripts/scoop_manifest.py upd --name myapp --set 'persist=data'\n"
            "  lint:     python scripts/scoop_manifest.py lint --fix-format\n"
        ),
    )
    parser.add_argument("--repo", help="bucket repo root (walks upwards by default)")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- generate ---
    gen = sub.add_parser(
        "generate",
        aliases=["gen"],
        help="generate a manifest and fill in its fields",
        description="Generate a new manifest.",
    )
    add_repo_argument(gen, parser)
    gen.add_argument(
        "--list-recipes", action="store_true", help="list all recipes and exit"
    )
    gen.add_argument(
        "--from",
        dest="from_file",
        help="read from a JSON spec file (object or array of objects)",
    )
    gen.add_argument("--name", help="app name = file name (without .json)")
    gen.add_argument("--recipe", help="recipe id (see --list-recipes)")
    gen.add_argument("--version", help="upstream version, without the leading v")
    gen.add_argument("--desc", help="one-line English description")
    gen.add_argument("--homepage", help="upstream homepage")
    gen.add_argument("--license", help="SPDX identifier, or Proprietary")
    gen.add_argument("--comment", help="free text for the ## comment key")
    gen.add_argument("--url", help="single-architecture direct download URL")
    gen.add_argument("--url64", help="64bit direct download URL")
    gen.add_argument("--url-arm64", dest="url_arm64", help="arm64 direct download URL")
    gen.add_argument("--hash", dest="hash_value", help="sha256 (single architecture)")
    gen.add_argument("--hash64", help="64bit sha256")
    gen.add_argument("--hash-arm64", dest="hash_arm64", help="arm64 sha256")
    gen.add_argument(
        "--fetch-hash",
        action="store_true",
        help="download the URL and compute sha256 (needs network)",
    )
    gen.add_argument(
        "--hash-from-file", help="compute sha256 from a local file (offline)"
    )
    gen.add_argument(
        "--repo-url",
        dest="repo_url",
        help="GitHub repository URL (used by checkver github)",
    )
    gen.add_argument("--arch", help="architecture set, e.g. 64bit or 64bit+arm64")
    gen.add_argument("--extract-dir", dest="extract_dir")
    gen.add_argument("--extract-to", dest="extract_to")
    gen.add_argument(
        "--nsis-payload",
        dest="nsis_payload",
        help="inner 7z name in an NSIS installer, default app-64.7z",
    )
    gen.add_argument("--shortcut-exe", dest="shortcut_exe")
    gen.add_argument("--shortcut-name", dest="shortcut_name")
    gen.add_argument(
        "--shortcut-entry",
        dest="shortcut_entry",
        action="append",
        metavar="JSON",
        help="verbatim shortcuts array as JSON, repeatable (overrides --shortcut-exe)",
    )
    gen.add_argument("--bin-exe", dest="bin_exe")
    gen.add_argument("--bin-alias", dest="bin_alias")
    gen.add_argument(
        "--bin-entry",
        dest="bin_entry",
        action="append",
        metavar="JSON",
        help='one bin entry as JSON, repeatable, e.g. \'["app.exe","alias"]\'',
    )
    gen.add_argument("--persist")
    gen.add_argument("--env-add-path", dest="env_add_path")
    gen.add_argument(
        "--env-set",
        dest="env_set",
        action="append",
        metavar="KEY=VALUE",
        help="environment variable written on install, repeatable",
    )
    gen.add_argument("--notes")
    gen.add_argument("--suggest")
    gen.add_argument("--depends")
    gen.add_argument("--installer-script", dest="installer_script")
    gen.add_argument(
        "--installer-file",
        dest="installer_file",
        help="run a file that came with the package instead of a script",
    )
    gen.add_argument(
        "--installer-arg",
        dest="installer_arg",
        action="append",
        help="argument for --installer-file, repeatable",
    )
    gen.add_argument("--uninstaller-script", dest="uninstaller_script")
    gen.add_argument("--post-install", dest="post_install")
    gen.add_argument("--pre-install", dest="pre_install")
    gen.add_argument("--pre-uninstall", dest="pre_uninstall")
    gen.add_argument("--post-uninstall", dest="post_uninstall")
    gen.add_argument(
        "--msi-mode",
        dest="msi_mode",
        choices=["extract", "install"],
        help="how to handle an .msi: unpack it (default) or run msiexec as admin",
    )
    gen.add_argument(
        "--msi-arg",
        dest="msi_arg",
        action="append",
        help="extra msiexec flag for --msi-mode install, repeatable",
    )
    gen.add_argument("--psmodule-name", dest="psmodule_name")
    gen.add_argument("--psmodule-path", dest="psmodule_path")
    gen.add_argument(
        "--extra-url",
        dest="extra_url",
        action="append",
        help="sidecar download URL, repeatable (needs a matching --extra-hash)",
    )
    gen.add_argument(
        "--extra-hash",
        dest="extra_hash",
        action="append",
        help="sha256 matching the nth --extra-url, repeatable",
    )
    gen.add_argument("--checkver-url", dest="checkver_url")
    gen.add_argument("--checkver-regex", dest="checkver_regex")
    gen.add_argument("--checkver-jsonpath", dest="checkver_jsonpath")
    gen.add_argument("--checkver-xpath", dest="checkver_xpath")
    gen.add_argument("--checkver-replace", dest="checkver_replace")
    gen.add_argument(
        "--checkver-reverse",
        dest="checkver_reverse",
        action="store_true",
        default=None,
        help="take the last regex match instead of the first",
    )
    gen.add_argument(
        "--checkver-useragent",
        dest="checkver_useragent",
        help="custom User-Agent for the checkver request",
    )
    gen.add_argument(
        "--checkver-script",
        dest="checkver_script",
        help="PowerShell snippet returning the text --checkver-regex runs against",
    )
    gen.add_argument(
        "--checkver-sourceforge",
        dest="checkver_sourceforge",
        help="SourceForge project path, e.g. beebeep/Windows",
    )
    gen.add_argument(
        "--au-hash-url",
        dest="au_hash_url",
        help="checksum file URL autoupdate fetches the hash from",
    )
    gen.add_argument("--au-hash-regex", dest="au_hash_regex")
    gen.add_argument(
        "--url-au", dest="url_au", help="autoupdate URL template (contains $version)"
    )
    gen.add_argument(
        "--section", help="README summary table section, e.g. 'General Use'"
    )
    gen.add_argument("--out", help="output directory (default <repo>/bucket)")
    gen.add_argument(
        "--dry-run", action="store_true", help="preview only, write nothing"
    )
    gen.add_argument(
        "--print-json",
        action="store_true",
        dest="print_json",
        help="print the generated JSON to stdout",
    )
    gen.add_argument(
        "--force",
        action="store_true",
        help="allow overwriting an existing file / ignore self-check errors",
    )
    gen.add_argument(
        "--no-readme",
        action="store_true",
        dest="no_readme",
        help="do not sync the README summary table",
    )
    gen.set_defaults(func=cmd_generate)

    # --- update ---
    upd = sub.add_parser(
        "update",
        aliases=["upd"],
        help="update fields of an existing manifest",
        description="Update an existing manifest.",
    )
    upd.add_argument("--name", action="append", help="target app name (repeatable)")
    add_repo_argument(upd, parser)
    upd.add_argument(
        "--all",
        action="store_true",
        help="run against every manifest (pair with --checkver for a sweep)",
    )
    upd.add_argument(
        "--set",
        action="append",
        metavar="KEY=VALUE",
        help="set a field, dotted path supported, e.g. shortcuts.0.1",
    )
    upd.add_argument("--unset", action="append", metavar="KEY", help="delete a field")
    upd.add_argument(
        "--version",
        help="bump the version and rewrite the old hard-coded version in URLs",
    )
    upd.add_argument("--url")
    upd.add_argument("--url64")
    upd.add_argument("--url-arm64", dest="url_arm64")
    upd.add_argument("--desc")
    upd.add_argument("--homepage")
    upd.add_argument("--license")
    upd.add_argument("--notes")
    upd.add_argument("--checkver-url", dest="checkver_url")
    upd.add_argument("--checkver-regex", dest="checkver_regex")
    upd.add_argument(
        "--checkver", action="store_true", help="probe the latest upstream version"
    )
    upd.add_argument(
        "--apply",
        action="store_true",
        help="with --checkver, actually write the new version",
    )
    upd.add_argument(
        "--rehash",
        action="store_true",
        help="re-download and recompute hashes (needs network)",
    )
    upd.add_argument(
        "--hash-from-file", help="compute sha256 from a local file (offline)"
    )
    upd.add_argument(
        "--readme", action="store_true", help="sync the README summary table"
    )
    upd.add_argument("--section", help="README summary table section (with --readme)")
    upd.add_argument(
        "--reorder",
        action="store_true",
        help="reorder keys canonically (produces a large diff)",
    )
    upd.add_argument(
        "--dry-run", action="store_true", help="preview only, write nothing"
    )
    upd.add_argument(
        "--print-json",
        action="store_true",
        dest="print_json",
        help="print the resulting JSON to stdout",
    )
    upd.add_argument("--force", action="store_true", help="ignore self-check errors")
    upd.set_defaults(func=cmd_update)

    # --- lint ---
    lint = sub.add_parser(
        "lint",
        aliases=["check"],
        help="check manifests against the repo standard",
        description="Check manifest conformance.",
    )
    lint.add_argument(
        "--name", action="append", help="only check the given app (repeatable)"
    )
    add_repo_argument(lint, parser)
    lint.add_argument(
        "--path", action="append", help="manifest path directly (repeatable)"
    )
    lint.add_argument("--json", action="store_true", help="emit a JSON report")
    lint.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failure too (exit code 1)",
    )
    lint.add_argument(
        "--fix-format",
        action="store_true",
        dest="fix_format",
        help="fix formatting only (indent / line endings / trailing newline)",
    )
    lint.add_argument(
        "--dry-run",
        action="store_true",
        help="with --fix-format: report without writing",
    )
    lint.add_argument(
        "--rules", action="store_true", help="print the rule catalog and exit"
    )
    lint.set_defaults(func=cmd_lint)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except L.SmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("aborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
