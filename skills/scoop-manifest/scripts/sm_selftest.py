"""scoop-manifest skill self-check: offline, validates the skill package and the repo baseline.

python scripts/sm_selftest.py            # full self-check
python scripts/sm_selftest.py --verbose  # print every detail
"""

from __future__ import annotations

import argparse
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

DUMMY = {
    "name": "selftest-app",
    "version": "9.9.9",
    "desc": "Selftest placeholder application",
    "homepage": "https://example.com",
    "license": "MIT",
    "url": "https://example.com/app-9.9.9.zip",
    "url64": "https://example.com/app-9.9.9-x64.zip",
    "url_arm64": "https://example.com/app-9.9.9-arm64.zip",
    "hash": "0" * 64,
    "hash64": "0" * 64,
    "hash_arm64": "1" * 64,
    "repo_url": "https://github.com/example/app",
    "shortcut_exe": "app.exe",
    "shortcut_name": "App",
    "bin_exe": "app.exe",
    "bin_alias": "app",
    "persist": "data",
    "notes": "Selftest notes.",
    "suggest": "extras/7zip",
    "depends": "scoopforge/comfyui",
    "installer_script": 'Start-Process -Wait "$dir\\setup.exe"',
    "uninstaller_script": 'Remove-Item "$dir\\leftover" -Recurse -Force',
    "post_install": "Write-Host 'done'",
    "pre_install": 'Remove-Item "$dir\\updater" -Force -Recurse',
    "extract_dir": "app-9.9.9",
    "extract_to": "app",
    "nsis_payload": "app-64.7z",
    "msi_mode": "extract",
    "msi_args": ["/qn"],
    "psmodule_name": "SelftestModule",
    "psmodule_path": "lib",
    "extra_urls": ["https://example.com/helper.ps1"],
    "extra_hashes": ["2" * 64],
    "env_add_path": "bin",
    "env_set": {"APP_HOME": "$dir"},
    "bin_entries": ["a.exe", ["b.exe", "b"]],
    "shortcut_entries": [["a.exe", "App"], ["b.exe", "App\\B"]],
    "comment": "Selftest comment.",
    "checkver_url": "https://example.com/downloads",
    "checkver_regex": "app-([\\d.]+)-x64\\.zip",
    "checkver_jsonpath": "$.tag_name",
    "checkver_xpath": "/pkg/version",
    "checkver_replace": "${version}",
    "checkver_reverse": True,
    "checkver_script": ["return 'app-9.9.9-x64.zip'"],
    "checkver_sourceforge": "example/app",
    "checkver_useragent": "Mozilla/5.0 (selftest)",
    "au_hash_url": "https://example.com/app-9.9.9.sha256",
    "au_hash_regex": "$sha256\\s+$basename",
    "url_au": "https://example.com/app-$version.zip",
}


class Checker:
    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, title: str, detail: str = "") -> None:
        print(f"  ✓ {title}" + (f"  {detail}" if detail else ""))
        if self.verbose and detail:
            print(f"      {detail}")

    def fail(self, title: str, detail: str = "") -> None:
        self.failures.append(f"{title} {detail}".strip())
        print(f"  ✗ {title}" + (f"  {detail}" if detail else ""))

    def warn(self, title: str, detail: str = "") -> None:
        self.warnings.append(f"{title} {detail}".strip())
        print(f"  ! {title}" + (f"  {detail}" if detail else ""))

    def expect(self, condition: bool, title: str, detail: str = "") -> bool:
        if condition:
            self.ok(title, detail)
        else:
            self.fail(title, detail)
        return condition


def check_recipes(check: Checker) -> None:
    print("\n[1] recipe catalog <-> builders consistency")
    catalog = L.load_recipes()
    param_docs = catalog.get("param_docs", {})
    recipes = catalog["recipes"]
    check.expect(
        bool(recipes), "recipe catalog is not empty", f"{len(recipes)} recipes"
    )

    stray_json = sorted(
        path.relative_to(L.skill_root()).as_posix()
        for path in L.skill_root().rglob("*")
        if path.is_file() and path.suffix == ".json"
    )
    check.expect(
        not stray_json,
        "no .json file in the package (the CI manifest gate would validate it)",
        ", ".join(stray_json) if stray_json else L.CATALOG_NAME,
    )

    ids = [r["id"] for r in recipes]
    check.expect(len(ids) == len(set(ids)), "recipe ids are unique")
    check.expect(
        catalog.get("default_recipe") in ids,
        "default_recipe points at an existing recipe",
        str(catalog.get("default_recipe")),
    )
    check.expect(
        len(catalog.get("summary_sections", [])) > 0, "declares README sections"
    )

    builders_used: set[str] = set()
    structure_ok = True
    for recipe in recipes:
        for field in ("id", "label", "when", "builder", "required", "refs"):
            if field not in recipe:
                check.fail(f"recipe {recipe.get('id')} lacks field {field}")
                structure_ok = False
        builder = recipe.get("builder")
        builders_used.add(builder)
        if builder not in L.BUILDERS:
            check.fail(
                f"recipe {recipe['id']} has no implementation for builder '{builder}'"
            )
            structure_ok = False
        for key in recipe.get("required", []):
            if key not in param_docs:
                check.fail(
                    f"required parameter '{key}' of recipe {recipe['id']} is not documented in param_docs"
                )
                structure_ok = False
    if structure_ok:
        check.ok("every recipe is well-formed and every builder is implemented")

    unimplemented = sorted(set(L.BUILDERS) - builders_used)
    check.expect(
        not unimplemented, "no orphan builders", ", ".join(unimplemented) or "0"
    )


def check_render(check: Checker) -> None:
    print("\n[2] recipe rendering (offline, virtual parameters)")
    catalog = L.load_recipes()
    for recipe in catalog["recipes"]:
        spec = dict(DUMMY)
        spec["recipe"] = recipe["id"]
        try:
            manifest = L.build_manifest(spec)
        except L.SmError as exc:
            check.fail(
                f"{recipe['id']} failed to render", str(exc).replace("\n", " / ")
            )
            continue
        text = L.dumps_manifest(manifest)
        try:
            reparsed = json.loads(text, object_pairs_hook=OrderedDict)
        except json.JSONDecodeError as exc:
            check.fail(f"{recipe['id']} produced invalid JSON", str(exc))
            continue
        findings = L.lint_manifest_text(text, str(spec["name"]))
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            check.fail(
                f"{recipe['id']} output failed self-check",
                "; ".join(f"{f.rule} {f.message}" for f in errors),
            )
            continue
        keys = list(reparsed.keys())
        if keys != L._sorted_by(keys, L.CANONICAL_ORDER):
            check.fail(
                f"{recipe['id']} top-level key order is not canonical", f"{keys}"
            )
            continue
        check.ok(f"{recipe['id']}", f"{len(keys)} top-level fields")


def check_repo(check: Checker, repo: Path) -> None:
    bucket = L.bucket_dir(repo)
    files = sorted(bucket.glob("*.json"))
    print(f"\n[3] repo round-trip consistency ({repo.name})")
    if not files:
        check.fail("no manifests under bucket/")
        return

    drift: list[str] = []
    for path in files:
        if (
            L.dumps_manifest(L.load_manifest(path), preserve_order=True).encode("utf-8")
            != path.read_bytes()
        ):
            drift.append(path.stem)
    if drift:
        check.warn(
            "formatting differs from the standard (update keeps the original order and will not touch them)",
            ", ".join(drift),
        )
    else:
        check.ok(f"{len(files)} manifests round-trip byte-identically")

    print("\n[5] README summary table round-trip (this repo)")
    readme_path = repo / "README.md"
    if not readme_path.is_file():
        check.warn("no README.md at the repo root, skipping")
        return
    text = readme_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tables = L.parse_summary(text)
    if not tables:
        check.fail("could not parse any summary table")
        return
    mismatched = []
    for table in tables:
        located = L._locate_summary_table(lines, table.section)
        if located is None:
            mismatched.append(f"{table.section} (not located)")
            continue
        start, end = located
        if lines[start:end] != L._render_table(table.header, table.rows, table.widths):
            mismatched.append(table.section)
    check.expect(
        not mismatched,
        f"{len(tables)} summary tables round-trip identically",
        "; ".join(mismatched)
        if mismatched
        else "the centering algorithm matches this repo exactly",
    )

    updated, _msg = L.insert_summary_row(
        text, tables[0].section, "__selftest__", "https://example.com"
    )
    check.expect(
        updated != text, "inserting a row changes the text (the write path works)"
    )
    _reverted, _msg2 = L.insert_summary_row(
        updated, tables[0].section, "__selftest__", "https://example.com"
    )
    check.expect(_reverted == updated, "inserting the same row twice is idempotent")


def check_lint_baseline(check: Checker, repo: Path) -> None:
    print("\n[6] full lint baseline")
    readme = (
        (repo / "README.md").read_text(encoding="utf-8")
        if (repo / "README.md").is_file()
        else None
    )
    files = sorted(L.bucket_dir(repo).glob("*.json"))
    errors = 0
    warnings = 0
    error_detail: list[str] = []
    for path in files:
        raw = path.read_bytes().decode("utf-8", "replace")
        findings = L.lint_manifest_text(raw, path.stem, readme_text=readme)
        for finding in findings:
            if finding.severity == "error":
                errors += 1
                error_detail.append(f"{path.stem}: {finding.rule} {finding.message}")
            else:
                warnings += 1
    print(
        f"      baseline: {len(files)} manifests, {errors} errors, {warnings} warnings"
    )
    if errors:
        for line in error_detail[:10]:
            print(f"        · {line}")
    check.expect(
        errors == 0,
        "the existing bucket has no error-level findings",
        f"{errors} errors" if errors else "",
    )


def check_docs(check: Checker) -> None:
    print("\n[7] docs <-> code consistency")
    refs = L.references_dir()
    catalog = L.load_recipes()
    recipe_ids = [r["id"] for r in catalog["recipes"]]

    # lint-rules.md ↔ RULES
    rules_doc = refs / "lint-rules.md"
    if not rules_doc.is_file():
        check.fail("references/lint-rules.md is missing")
    else:
        text = rules_doc.read_text(encoding="utf-8")
        documented: dict[str, tuple[str, str]] = {}
        for match in re.finditer(
            r"^\|\s*([EW]\d{3})\s*\|\s*(Error|Warning)\s*\|\s*(.+?)\s*\|\s*$",
            text,
            re.MULTILINE,
        ):
            documented[match.group(1)] = (match.group(2), match.group(3))
        code_ids = set(L.RULES)
        doc_ids = set(documented)
        check.expect(
            code_ids == doc_ids,
            "lint-rules.md covers every rule",
            f"missing {sorted(code_ids - doc_ids)}; extra {sorted(doc_ids - code_ids)}"
            if code_ids != doc_ids
            else f"{len(code_ids)} rules",
        )
        drift = []
        for rule, (severity, title) in L.RULES.items():
            if rule not in documented:
                continue
            doc_severity, doc_title = documented[rule]
            want = "Error" if severity == "error" else "Warning"
            if doc_severity != want or doc_title != title:
                drift.append(rule)
        check.expect(
            not drift,
            "rule severity and wording match the code",
            "; ".join(drift) if drift else "",
        )

    # recipes.md ↔ recipes.jsonc
    recipes_doc = refs / "recipes.md"
    if not recipes_doc.is_file():
        check.fail("references/recipes.md is missing")
    else:
        text = recipes_doc.read_text(encoding="utf-8")
        headings = re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
        doc_ids = [h for h in headings if h in recipe_ids]
        missing = [rid for rid in recipe_ids if rid not in doc_ids]
        extra = [h for h in headings if h not in recipe_ids and h != "Adding a recipe"]
        check.expect(
            not missing,
            "recipes.md covers every recipe",
            f"missing {missing}" if missing else f"{len(recipe_ids)} recipes",
        )
        check.expect(
            not extra,
            "recipes.md has no extra sections",
            ", ".join(extra) if extra else "",
        )

    # manifest-fields.md exists
    check.expect(
        (refs / "manifest-fields.md").is_file(), "references/manifest-fields.md exists"
    )

    # coverage.md documents where the recipes come from and what is still uncovered
    check.expect((refs / "coverage.md").is_file(), "references/coverage.md exists")

    # SKILL.md frontmatter matches the directory name
    skill_file = L.skill_root() / "SKILL.md"
    if not skill_file.is_file():
        check.fail("SKILL.md is missing")
        return
    text = skill_file.read_text(encoding="utf-8")
    match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
    check.expect(
        match is not None and match.group(1) == L.skill_root().name,
        "SKILL.md name equals the skill directory name",
        f"name={match.group(1) if match else 'missing'}, dir={L.skill_root().name}",
    )
    missing_commands = [
        cmd for cmd in ("generate", "update", "lint") if cmd not in text
    ]
    check.expect(
        not missing_commands,
        "SKILL.md documents the three trigger commands",
        f"missing {missing_commands}" if missing_commands else "",
    )


def check_readme_parser(check: Checker) -> None:
    """The summary-table layer must cope with both bucket dialects offline.

    Extras-Plus: 3 columns, `App` first, ASCII, `###` headings.
    Extras-CN  : 4 columns with a Chinese display-name column, `####` sub-headings,
                 CJK-padded cells, plus a 2-column plain-text mirror table.
    """
    print("\n[4] README summary table dialects")

    plus = (
        "## \u2b50\ufe0f Summary\n"
        "\n"
        "### AI Specific\n"
        "\n"
        "|          App          | Auto-Update ? | Note  |\n"
        "| :-------------------: | :-----------: | :---: |\n"
        "| [alpha](https://a.example) |       \u2713       |       |\n"
        "| [beta](https://b.example) |               |       |\n"
    )
    cn = (
        "## \u2b50\ufe0f \u603b\u7ed3\n"
        "\n"
        "### \u8de8\u5e73\u53f0\n"
        "\n"
        "#### \u5916\u8bed\u5b66\u4e60\n"
        "\n"
        "|    \u4e2d\u6587\u540d\u79f0    |        App        | \u81ea\u52a8\u66f4\u65b0 |  \u5907\u6ce8  |\n"
        "| :------------: | :---------------: | :------: | :----: |\n"
        "|   阿波波外语   | [aboboo](http://aboboo.com) |    \u2713     | \u7cbe\u7b80\u7248 |\n"
        "\n"
        "### \u5f00\u6e90\u955c\u50cf\n"
        "\n"
        "|    App     | \u81ea\u52a8\u66f4\u65b0 |\n"
        "| :--------: | :------: |\n"
        "| Blender-cn |    \u2713     |\n"
        "|   VLC-cn   |    \u2713     |\n"
    )

    # The historical English-only gate: `### App` heading, `App` in column 0.
    plus_tables = L.parse_summary(plus)
    check.expect(
        len(plus_tables) == 1 and plus_tables[0].section == "AI Specific",
        "Extras-Plus dialect parses (### heading, App in column 0)",
        f"got {[t.section for t in plus_tables]}",
    )
    check.expect(
        plus_tables
        and plus_tables[0].app_col == 0
        and L.readme_app_names(plus) == ["alpha", "beta"],
        "Extras-Plus app names come from the linked cell",
    )

    # The localized dialect: a Chinese heading, `####` nesting and App in column 1.
    cn_tables = L.parse_summary(cn)
    check.expect(
        [t.section for t in cn_tables]
        == ["\u5916\u8bed\u5b66\u4e60", "\u5f00\u6e90\u955c\u50cf"],
        "Extras-CN dialect parses (#### nesting, localized headings)",
        f"got {[t.section for t in cn_tables]}",
    )
    check.expect(
        bool(cn_tables) and cn_tables[0].app_col == 1,
        "Extras-CN app names come from column 1, not column 0",
    )
    check.expect(
        L.readme_app_names(cn) == ["aboboo", "Blender-cn", "VLC-cn"],
        "plain-text and linked app cells both resolve to names",
        str(L.readme_app_names(cn)),
    )

    # Round-trip: CJK cells are padded to display width, not to codepoint count.
    ok = True
    for text in (plus, cn):
        lines = text.splitlines()
        for table in L.parse_summary(text):
            found = L._locate_summary_table(lines, table.section)
            if found is None:
                ok = False
                continue
            start, end = found
            if lines[start:end] != L._render_table(
                table.header, table.rows, table.widths
            ):
                ok = False
    check.expect(ok, "both dialects round-trip byte-identically")
    check.expect(
        L._display_width("\u4e2d\u6587") == 4 and L._display_width("ab") == 2,
        "CJK glyphs count as two columns when padding",
    )

    # Insertion must respect the shape of the target table.
    inserted, _msg = L.insert_summary_row(cn, "\u5916\u8bed\u5b66\u4e60", "zzz", "https://z")
    check.expect(
        "[zzz](https://z)" in inserted and inserted.index("[zzz](https://z)")
        > inserted.index("[aboboo](http://aboboo.com)"),
        "a new row is appended in a 4-column CJK table",
    )
    mirror, _msg2 = L.insert_summary_row(cn, "\u5f00\u6e90\u955c\u50cf", "Zzz-cn", "https://z")
    check.expect(
        "Zzz-cn" in mirror and "[Zzz-cn](" not in mirror,
        "the mirror table keeps plain text (no markdown link)",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sm_selftest.py", description="scoop-manifest skill self-check"
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--repo")
    args = parser.parse_args()

    check = Checker(args.verbose)
    print("scoop-manifest skill self-check")
    print(f"skill package: {L.skill_root()}")

    check_recipes(check)
    check_render(check)
    check_readme_parser(check)

    try:
        repo = L.find_repo_root(Path(args.repo) if args.repo else None)
    except L.SmError as exc:
        check.warn("no bucket repo found, skipping repo-level checks", str(exc))
        repo = None
    if repo is not None:
        check_repo(check, repo)
        check_lint_baseline(check, repo)

    check_docs(check)

    print("\n" + "-" * 56)
    print(f"{len(check.failures)} failures, {len(check.warnings)} warnings")
    for line in check.failures:
        print(f"  failure: {line}")
    return 1 if check.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
