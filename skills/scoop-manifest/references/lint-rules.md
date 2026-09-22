# Lint rule catalog

`RULES` in `scripts/sm_lib.py` is the source of truth. This document is the
readable version, kept in sync by `scripts/sm_selftest.py` -- change both.

Rules follow this repo's CI: `.github/workflows/ci.yml` (Pester +
Import-Bucket-Tests, on `master`), `.github/workflows/schedule.yml` (Excavator),
`.editorconfig`, and the 88 existing manifests' own baseline.
`references/coverage.md` records which upstream pattern each rule came from.

## Errors (E)

Error-level findings break `scoop install` or fail CI, making `lint` exit 1.

| Rule | Severity | Description                                                                                            |
| :--- | :------- | :----------------------------------------------------------------------------------------------------- |
| E001 | Error    | manifest is not valid JSON / top level is not an object                                                |
| E002 | Error    | file is not UTF-8, or contains a BOM                                                                   |
| E003 | Error    | missing required field (version/description/homepage/license/checkver/autoupdate)                      |
| E004 | Error    | version is missing or not a string                                                                     |
| E005 | Error    | checkver structure is invalid                                                                          |
| E006 | Error    | autoupdate has neither a top-level url nor architecture.url                                            |
| E007 | Error    | architecture exists but has no 64bit entry                                                             |
| E008 | Error    | shortcut entry does not start with [exe, name]                                                         |
| E009 | Error    | file name does not match ^[a-z0-9][a-z0-9-]*$                                                          |
| E010 | Error    | script matches a dangerous pattern (Invoke-Expression / -EncodedCommand / plaintext credentials, etc.) |
| E011 | Error    | hash is not a 64-char lowercase sha256 and no autoupdate hash source is given                          |

## Warnings (W)

Warnings do not affect installation but they slow down maintenance. With
`--strict` they also make `lint` exit 1.

| Rule | Severity | Description                                                                     |
| :--- | :------- | :------------------------------------------------------------------------------ |
| W101 | Warning  | description ends with a period / exceeds 120 chars / starts lowercase           |
| W102 | Warning  | download URL uses plaintext http://                                             |
| W103 | Warning  | architecture exists but autoupdate does not cover per-architecture URLs         |
| W104 | Warning  | version hard-coded in the URL does not match the version field                  |
| W105 | Warning  | app is missing from the README summary table / listed more than once            |
| W106 | Warning  | license is neither an SPDX identifier nor an {identifier,url} object            |
| W107 | Warning  | version contains non-numeric characters, autoupdate may misbehave               |
| W108 | Warning  | top-level url and architecture coexist; redundant field                         |
| W109 | Warning  | formatting does not match .editorconfig (indentation / CRLF / trailing newline) |
| W110 | Warning  | autoupdate URL has no $version, so the download URL stays stale after a bump    |
| W111 | Warning  | checkver.github points at api.github.com, which Scoop turns into a 404          |

## How to fix each rule

### E group

- **E001 / E002**: run `python -c "import json;json.load(open('x.json'))"`
  to see the failing line and column. A BOM needs a re-save; no auto-fix exists.
- **E003 / E004**: add what is missing. `version` must be a string (`"1.2"`).
  `edrawmax8` and `mpv.net-cm` currently fail this: neither declares a
  `checkver` or an `autoupdate`, so Excavator can never refresh them.
- **E005**: `github` and `sourceforge` need no `regex`; `url` and `script` must
  have one, and a misspelled key name is reported here too. A bare string is
  the shorthand for "scrape the homepage": Scoop falls back to `homepage` when
  `checkver.url` is absent, so it is only an error when there is no `homepage`
  to scrape. **`jsonpath` and `xpath` need no `regex` either** -- the picked
  value already is the version, and `hbuilderx` / `wpsoffice-cn` rely on that.
  `re` and `jp` are Scoop synonyms for `regex` and `jsonpath`, not typos, and
  are normalised before this check runs.
- **E006**: `autoupdate` needs a top-level `url` or an `architecture.<a>.url`.
- **E007**: `architecture` must contain a `64bit` branch.
- **E008**: each `shortcuts` entry is at least `["exe", "display name"]`; the
  first two items must be strings. Later items (arguments, icon) may follow.
- **E009**: lowercase letters, digits and hyphens only, starting alphanumeric.
  `mpv.net-cm` cannot satisfy this without renaming the file.
- **E010**: the script contains `Invoke-Expression` / `iex` /
  `-EncodedCommand` / a pipe into `powershell` / a plaintext credential /
  `Set-ExecutionPolicy Unrestricted` / a recursive delete of a drive root. Such
  patterns are a supply-chain risk in an auto-updating flow; review by hand.
  **`Invoke-Expression` on its own is not reported**: it is only flagged when the
  same snippet can reach the network and has no local path resolver, because a
  package running a hook script it just installed is legitimate.
  `miniforge-cn` ends with
  `(& $dir\scripts\conda.exe shell.powershell hook) | ... | Invoke-Expression`,
  which is verbatim what upstream conda prescribes.
- **E011**: `hash` must be 64 lowercase hex chars or an equally long array.
  Scoop rejects an `"md5:..."` prefix. If Excavator should fill it, declare a
  `hash` source in `autoupdate`. `feishu` currently fails this.

### W group

- **W101**: Scoop treats `description` as a phrase, not a sentence.
  **A description containing Chinese is exempt**: this bucket targets Chinese
  users and writes 57 of its 88 descriptions in Chinese, so capitalization,
  trailing-period and length are not meaningful signals there. The rule still
  applies to Latin-script descriptions; `libreoffice-cn` (trailing period) and
  `vlc-cn` (168 chars) are the two live hits.
- **W102**: only `http://` is reported. This is the single largest warning group
  here (15 findings across 9 files: `aboboo`, `aboboo-full`, `baidunetdisk`,
  `feeluown`, `kingdraw`, `msys2-cn`, `partition-assistant`, `qqmusic`, `tim`),
  because several Chinese vendors publish no https download endpoint at all.
  Treat it as informational for those.
- **W103**: `architecture` and `autoupdate.architecture` must come in pairs,
  otherwise Excavator bumps the version but not the per-arch URLs.
  `goldendict-ng` and `qingjian` hit it today.
- **W104**: the version in the download URL disagrees with `version`, so the
  release process was hand-edited. `clash-mi` and `jianying-pro` hit this.
- **W105**: the app is missing from, or duplicated in, the README summary table;
  near-miss names get a hint. The hint distinguishes two cases: a *case-only*
  difference (`manifest blender-cn` vs `README Blender-cn`) is the `开源镜像`
  mirror-table convention of listing display names, and a fuzzy match is a
  probable typo. Only a finding with no hint at all is a genuine omission.
  This repo's 88 manifests produce 35 findings: 17 case-only (ignore) and 18
  real gaps (`ainiee`, `pixpin`, `videocaptioner`, …).
- **W106**: prefer an SPDX identifier for `license` (`MIT`, `Apache-2.0`,
  `GPL-3.0-or-later`); when unsure use `{"identifier": ..., "url": ...}`.
  Extra words such as `MIT license`, a bare URL, or a sentence such as
  `Freeware for non-commercial use` are flagged -- 5 manifests here
  (`aigcpanel`, `edgeless`, `msys2-cn`, `partition-assistant`, `wegame`).
- **W107**: when `version` has non-numeric chars (`26.7.2-0`, `2026-06-11`,
  `26H1-25388281`), Excavator's version comparison may misbehave; confirm by hand.
  9 manifests here, mostly `*-cn` mirrors that track a distro release.
- **W108**: a top-level `url` plus `architecture` is redundant and easy to
  update inconsistently.
- **W109**: disagrees with `.editorconfig`; `--fix-format` repairs it
  (formatting only). No manifest here currently hits it -- all 88 round-trip
  byte-identically.
- **W110**: the download URL has a version but the `autoupdate` URL has no
  `$version`, so the URL never follows a bump. `goldendict-ng`, `inkscape-cn`,
  `quarkclouddrive`, `wegame` and `yuque` hit this.
- **W111**: `Scoop` appends `/releases/latest` to whatever `checkver.github`
  holds. Pointing it at `https://api.github.com/repos/o/r/releases/latest`
  therefore requests `.../releases/latest/releases/latest` and gets a 404, so
  the version is never detected and Excavator silently skips the app. Move the
  API endpoint into `checkver.url` instead. No manifest in this bucket hits it
  today, but `clash-mi` and `kicad-cn` put an `api.github.com` URL in
  `checkver.url`, which is the correct place for it.

## Known exceptions (do not "fix" these)

| Symptom                                          | Why it is fine                                          | Sample                                                        |
| :----------------------------------------------- | :------------------------------------------------------ | :------------------------------------------------------------ |
| `autoupdate` uses a fixed URL with no `$version` | upstream serves a permanent link                        | `edgeless`, and several `*-cn` mirrors                        |
| no `checkver` / `autoupdate` at all              | abandoned or single-release software                    | `edrawmax8`, `mpv.net-cm`                                     |
| plaintext `http://`                              | the vendor has no https endpoint at all                 | `kingdraw`, `partition-assistant`                             |
| `version` contains letters or a date             | upstream archives are named `26H1-25388281` / by date   | `vmware-workstation-pro`, `msys2-cn`                          |
| `description` in Chinese                         | this bucket targets Chinese users                       | 57 of the 88 manifests                                        |
| `checkver` uses `re` / `jp`                      | Scoop synonyms for `regex` / `jsonpath`, not typos      | `lyx-cn`, `quarkclouddrive` (`re`); `clash-mi` (`jp`)         |
| `jsonpath` with no `regex`                       | the picked value already is the version                 | `hbuilderx`, `wpsoffice-cn`, `baidunetdisk`                   |
| `Invoke-Expression` on an installed hook script  | the snippet cannot reach the network                    | `miniforge-cn`                                                |

## Usage

```bash
python scripts/scoop_manifest.py lint                        # full run
python scripts/scoop_manifest.py lint --name douyin          # a single app
python scripts/scoop_manifest.py lint --json                 # machine-readable report
python scripts/scoop_manifest.py lint --strict               # warnings fail too
python scripts/scoop_manifest.py lint --fix-format           # formatting only
python scripts/scoop_manifest.py lint --rules                # print the rule catalog
python scripts/scoop_manifest.py lint --repo C:\Scoop\buckets\extras-cn
```

`--repo` is accepted before or after the subcommand; from inside
`C:\Scoop\buckets\extras-cn` it is not needed at all.

## Divergence from the Extras-Plus build

Three rules behave differently here, all because of facts about this bucket or
latent bugs in the original. The **titles and severities in the two tables above
are identical to `RULES` in `sm_lib.py`**, which is what `sm_selftest.py`
enforces; only the *implementation* differs:

| Rule | Extras-Plus | Extras-CN | Why |
| :--- | :--- | :--- | :--- |
| E005 (jsonpath) | `url` + `jsonpath` without `regex` is an error | accepted | 34 of the 210 upstream jsonpath blocks omit the regex; `hbuilderx` / `wpsoffice-cn` do too |
| E005 (aliases) | `re` / `jp` reported as unknown keys | normalised to `regex` / `jsonpath` | they are documented Scoop synonyms |
| E010 | `Invoke-Expression` flagged unconditionally | flagged only with a remote launcher and no local resolver | `miniforge-cn`'s conda hook is the documented upstream pattern |
| E010 (drive root) | pattern was `C:\\\\`, which compiles to `C:\\` and never matched | pattern is `[A-Za-z]:\\`, so it fires | the original was dead code |
| W101 | applies to every description | skipped for CJK text | 57 of 88 descriptions are Chinese |
