# Coverage: where the recipes come from

`assets/recipes.jsonc` was not drawn from a blank page, and it is not meant to be
exhaustive. This document records the survey of the upstream bucket that sized the
catalog, maps every recipe onto the upstream population it covers, and states what
was deliberately left out. Read it when a manifest in front of you does not
obviously match a recipe: the two questions are "which upstream shape is this?"
and "is it one of the known gaps?".

Sections 1-6 are the survey, 7 is the mapping, 8 the gaps, 9 the rejected ideas
and 10 the re-run recipe.

The survey numbers below describe the **upstream `ScoopInstaller/Extras`
bucket**, which is what the recipe catalog was sized against. They are shared
verbatim with the Extras-Plus build of this skill, because the catalog is shared.
What differs is the local corpus the proportions get compared against: this
bucket carries 88 manifests, not 56, and its shape distribution is different in
one important way -- it leans non-GitHub much harder, so `webpage-regex` covers a
larger share of local apps than the upstream proportions would suggest.

## 1. Method

- Corpus: `C:\Scoop\buckets\extras\bucket` — the upstream
  `ScoopInstaller/Extras` bucket, **2389** `*.json` manifests, against the 88 in
  this repo.
- Offline and read-only: every file is `json.loads`-ed and tallied with
  `Counter` over top-level keys, checkver shapes, autoupdate shapes, URL
  extensions, `#` fragments and feature flags. Nothing is downloaded.
- "manifests" below means *how many files* show a trait, and one file counts at
  most once per trait. Tables that count URLs instead of files say so.
- Measured 2026-09-19. Upstream moves, so the absolute numbers are a snapshot and
  the proportions are the durable part. Section 9 has the re-run recipe.
- The **local** figures quoted alongside (88 manifests, 62 with `architecture`,
  21 flat `url` + `regex`, 86 with `checkver`, 15 with plaintext `http://`) were
  re-measured against this repo on 2026-09-22 with the shipped `lint` and
  `sm_selftest.py` rather than the throwaway tallying script.

## 2. Corpus shape

The four required fields are on all 2389 files by definition. Everything else:

| Field                      |     Files | Field            | Files |
| :------------------------- | --------: | :--------------- | ----: |
| `version` / `description`  |      2389 | `installer`      |   154 |
| `homepage` / `license`     |      2389 | `uninstaller`    |   127 |
| `autoupdate`               |      2210 | `innosetup`      |   124 |
| `checkver`                 |      2199 | `pre_uninstall`  |    93 |
| `shortcuts`                |      1843 | `depends`        |    67 |
| `architecture`             |      1688 | `##`             |    54 |
| `bin`                      |      1428 | `env_set`        |    44 |
| `url` + `hash` (top level) |       831 | `extract_to`     |    29 |
| `persist`                  |       704 | `env_add_path`   |    28 |
| `pre_install`              |       612 | `post_uninstall` |    18 |
| `extract_dir`              |       566 | `psmodule`       |    18 |
| `notes`                    |       318 | `_comment`       |     1 |
| `suggest` / `post_install` | 315 / 227 |                  |       |

Three figures matter for maintenance:

- **175 manifests have neither `checkver` nor `autoupdate`** (190 lack checkver
  alone, 179 lack autoupdate alone). Excavator can never refresh those: they are
  hand-bumped or already stale. `lint` reports this as a warning, not an error,
  because it is a legitimate choice for abandoned software.
- **54 manifests use the `##` key** and exactly one uses `_comment`. `##` is
  Scoop's documented in-manifest comment; `_comment` is not, and is a typo.
- `pre_install` (612) outnumbers `post_install` (227) by almost three to one, so
  preparation before extraction is far more common than cleanup after it.

## 3. checkver shapes

The shape is `json`-normalised: `str:` means the value is a bare string,
`{a,b}` means an object with exactly those keys.

| Shape                                                                       |  Files | Covered by                               |
| :-------------------------------------------------------------------------- | -----: | :--------------------------------------- |
| `{github}`                                                                  |    579 | every `github-*` recipe                  |
| `str:github`                                                                |    563 | every `github-*` recipe                  |
| `{regex,url}`                                                               |    474 | `webpage-regex`                          |
| *(no checkver)*                                                             |    190 | —                                        |
| `str:<regex>`                                                               |    147 | `webpage-regex`                          |
| `{github,jsonpath,regex}`                                                   |    146 | `github-asset-jsonpath`                  |
| `{github,regex}`                                                            |     60 | `github-asset-jsonpath`                  |
| `{regex,script}`                                                            |     38 | `checkver-script`                        |
| `{regex,replace,url}`                                                       |     34 | `webpage-regex`                          |
| `{jsonpath,url}`                                                            |     31 | `api-jsonpath`                           |
| `{regex,reverse,url}`                                                       |     25 | `webpage-regex`                          |
| `{jsonpath,regex,url}`                                                      |     14 | `api-jsonpath`                           |
| `{regex}`                                                                   |     13 | `checkver-script`                        |
| `{regex,sourceforge}`                                                       |     10 | `sourceforge`                            |
| `{regex,script,url}`                                                        |     10 | `checkver-script`                        |
| `{regex,url,xpath}`                                                         |     10 | `webpage-regex`                          |
| `{github,jsonpath,regex,replace}`                                           |      7 | `github-asset-jsonpath`                  |
| `{regex,url,useragent}`                                                     |      5 | `webpage-regex`                          |
| `{url,xpath}`                                                               |      5 | `webpage-regex`                          |
| `{github,jsonpath,regex,script}`                                            |      4 | `checkver-script`                        |
| `{github,jsonpath,regex,replace,script}`                                    |      1 | —                                        |
| `{regex,replace}`                                                           |      4 | hand-written                             |
| `{sourceforge}` / `str:sourceforge`                                         |  3 / 2 | `sourceforge`                            |
| `{re,url}`                                                                  |      3 | `webpage-regex`                          |
| `{github,jsonpath}`                                                         |      2 | `github-asset-jsonpath`                  |
| `{regex,replace,sourceforge}` / `{regex,replace,script}`                    |  2 / 2 | hand-written                             |
| `{jp,regex,url}` / `{jp,url}`                                               |  1 / 1 | `api-jsonpath` (`jp` aliases `jsonpath`) |
| `{github,regex,replace}`, `{regex,reverse}`, `{jsonpath,regex,replace,url}` | 1 each | hand-written                             |

**147 files put a bare regex string straight into `checkver`** — `"Version
([\d.]+)"`, `"Latest version: ([\d.]+)"`, … — which makes it the largest single
non-GitHub form and the reason `webpage-regex` accepts a recipe without
`checkver_url`. Scoop reads that string as a regex and runs it against
`$json.homepage`, because the default for the scrape target is the homepage
(`bin/checkver.ps1`, "Not Specified"). The builder emits this shorthand only
when the regex is the sole `checkver` key: `replace`, `reverse` and `useragent`
all require the object form.

Per-modifier totals, which the recipes accept as optional parameters:

| Modifier                                    | Files | Recipe parameter               |
| :------------------------------------------ | ----: | :----------------------------- |
| GitHub checkver (string **or** object form) |  1363 | `repo_url` / `checkver_github` |
| `checkver.script`                           |    55 | `checkver_script`              |
| `checkver.reverse`                          |    26 | `checkver_reverse`             |
| `checkver.sourceforge`                      |    15 | `checkver_sourceforge`         |
| `checkver.xpath`                            |    15 | `checkver_xpath`               |
| `checkver.useragent`                        |     5 | `checkver_useragent`           |

GitHub is 57% of the corpus, which is why six of the sixteen recipes are
GitHub-specific and why the non-GitHub ones lean on `url` + `regex`.

> **Locally the balance is the other way round.** This bucket has 86 manifests
> with a `checkver`, and they split as: **50 `url` + `regex` against a vendor
> site**, 26 that resolve through GitHub (in either spelling), 7 `jsonpath` and 3
> `script`. Non-GitHub scraping is therefore the single largest group here, 2.4x
> the GitHub group, which is the mirror image of upstream. That is why
> `webpage-regex` is the recipe a new China-only app usually needs, and why
> `references/recipes.md` cites eight local manifests for it.

## 4. autoupdate shapes

| Shape                                                                                                                |  Files |
| :------------------------------------------------------------------------------------------------------------------- | -----: |
| `{architecture}`                                                                                                     |   1106 |
| `{url}`                                                                                                              |    520 |
| `{architecture,hash}`                                                                                                |    318 |
| *(no autoupdate)*                                                                                                    |    179 |
| `{hash,url}`                                                                                                         |    124 |
| `{extract_dir,url}`                                                                                                  |     65 |
| `{architecture,extract_dir}`                                                                                         |     31 |
| `{extract_dir,hash,url}`                                                                                             |     24 |
| `{architecture,extract_dir,hash}`                                                                                    |     16 |
| `{architecture,url}`, `{persist,url}`, `{architecture,notes}`, `{architecture,bin,hash}`, `{bin,hash,shortcuts,url}` | 1 each |

Inside `autoupdate.architecture.<arch>` the member shape is almost always
minimal: `{url}` on 1880 branches, `{hash,url}` on 185, `{extract_dir,url}` on
185, with `{extract_dir,hash,url}` at 3 and `{bin,shortcuts}` at 2.

The single defect worth naming: **148 manifests carry `architecture` but give
`autoupdate` only a flat `url`**, so Excavator refreshes one URL and silently
leaves the per-architecture ones pinned. This is rule `W103`; 2 manifests in this
repo hit it.

## 5. Architecture combinations

| Combination                                      | Files |
| :----------------------------------------------- | ----: |
| `64bit` only                                     |   860 |
| `32bit` + `64bit`                                |   468 |
| `64bit` + `arm64`                                |   230 |
| `32bit` + `64bit` + `arm64`                      |   128 |
| `arm64` only                                     |     2 |
| no `architecture` block (top-level `url`/`hash`) |   701 |

Two consequences for the builders. First, 701 manifests skip `architecture`
entirely, so a recipe must be able to emit a flat `url`/`hash` pair and not a
one-key `architecture` block — that is what `arch` defaulting to a single value
achieves. Second, arm64 is still fringe (~15% of the files, and only 2 are
arm64-only), so arm64 support is an option on each recipe rather than a
first-class branch in the decision tree.

The third consequence is a scope decision rather than a technical one: the
**596** files that pair `32bit` with another architecture are deliberately not
covered. The catalog emits `64bit` and `arm64` only, so `url32` / `hash32` do
not exist here and `32bit` is rejected as an `arch` value. Restoring it means
one entry each in `ARCH_PARAM` / `ARCH_HASH_PARAM` in `sm_lib.py`, the matching
`--url32` / `--hash32` flags in `scoop_manifest.py`, and the `param_docs` /
recipe lists in `recipes.jsonc`.

## 6. Download shapes

Counted **per URL**, not per file, across every `url` / `url64` / `url32` /
`url_arm64` at any nesting depth — **7853** URLs in total:

| Extension | URLs |      | Extension                |   URLs |
| :-------- | ---: | :--- | :----------------------- | -----: |
| `.zip`    | 3184 |      | `.jar`                   |     27 |
| `.exe`    | 1900 |      | `.msix`                  |     12 |
| `.7z`     |  321 |      | `.rar`                   |     11 |
| `.msi`    |  289 |      | `.cab`                   |      8 |
| `.nupkg`  |  111 |      | `.tgz` / `.whl` / `.ps1` | 4 each |
| `.tar.gz` |   68 |      | `.tar.xz` / `.gz`        |  2 / 3 |

Note the ordering: once the fragment is stripped, **`.exe` outnumbers `.7z` by
roughly six to one**, which is the opposite of the impression a coarse count
gives. Matching on the raw URL tail puts `app.exe#/dl.7z` in the `.7z` bucket —
see the fragment table below for why that is the wrong reading.

The remaining **1905 URLs carry no extension at all**, and most of those are not
packages. **467** point at a checksum file or a `latest*.yml`, across 432 files,
and 301 at a licence / EULA / terms page; the rest are bare download endpoints
(`?download`, `?latest`, `?releases`, `?p=windows&type=release`). That
467-URL checksum population is the reason `autoupdate.hash` exists, and **484**
manifests declare it.

`#` fragments, again per URL:

| Fragment                                         |   URLs | Meaning                                                 |
| :----------------------------------------------- | -----: | :------------------------------------------------------ |
| `#/dl.7z`                                        |    956 | rename an NSIS shell so Scoop unpacks it as 7z          |
| `#/<name>.exe`                                   |    383 | pin the saved file name and keep it unpacked            |
| `#/dl.zip`                                       |     54 | the same rename trick, for a zip payload                |
| `#/dl.exe`                                       |     16 | keep the bare exe, do not unpack                        |
| any `*.msi*` fragment                            |     17 | hand an MSI to Scoop untouched, `_msi_` being canonical |
| `#/dl.7z_` / `#/dl.zip_`                         |  7 / 6 | the trailing underscore, same purpose as `_msi_`        |
| trailing-underscore fragments of all forms       |     28 |                                                         |
| `#/cosi.7z`, `#/didder.exe`, `#/hysteria.exe`, … | 6 each | the long tail of named fragments                        |

`#/dl.7z` on 956 URLs across **365 files**, 213 of which also mention
`$PLUGINSDIR`, is the evidence behind `github-nsis-7z`: it is not an edge case,
it is the default shape of every Electron release.

## 7. Recipe to upstream pattern

"Population" is the number of upstream files whose shape that recipe is built
for. Where a recipe sits across two shapes the larger one is quoted.

| Recipe                  | Upstream shape                                             |    Population |
| :---------------------- | :--------------------------------------------------------- | ------------: |
| `github-portable-zip`   | GitHub release, plain archive, top-level `url`+`hash`      |           831 |
| `github-nsis-7z`        | NSIS shell with `#/dl.7z`, payload under `$PLUGINSDIR`     |           365 |
| `github-innosetup`      | `innosetup: true`                                          |           124 |
| `github-exe-installer`  | an `installer` block the release actually runs             |           154 |
| `github-single-exe`     | bare `.exe`, no fragment, nothing to extract               |             4 |
| `github-source-archive` | source tag archive, or a version-stamped `extract_dir`     |       1 + 566 |
| `github-msi`            | `.msi` among the download URLs                             |           117 |
| `github-asset-jsonpath` | GitHub checkver carrying `jsonpath`                        |           159 |
| `webpage-regex`         | non-GitHub `url` + `regex`, plus the bare-string shorthand |     577 + 147 |
| `api-jsonpath`          | non-GitHub `jsonpath` checkver                             |            47 |
| `checkver-script`       | `checkver.script`                                          |            55 |
| `sourceforge`           | `checkver.sourceforge`                                     |            15 |
| `powershell-gallery`    | a `psmodule` block and a `.nupkg` download                 |            18 |
| `redirect-arch`         | version-less permanent link (`/latest/`)                   |            32 |
| `portable-multifile`    | `url` and `hash` as arrays                                 |            34 |
| `github-git-clone`      | plugin cloned into a host app                              | 0 (Extras-Plus) |

Two of those deserve a caveat rather than a number:

- `sourceforge`: **94** upstream files download from SourceForge, but only 15
  use the dedicated `checkver.sourceforge` key. The other 79 scrape the project
  page with `url` + `regex`, so they land in `webpage-regex`. Prefer the
  dedicated key when writing new ones — it does not break when the page is
  redesigned.
- `github-git-clone`: **zero** upstream manifests contain `git clone`. It is a
  this-repo pattern (`comfyui-manager`) and stays in the catalog for that reason
  alone, not because upstream justified it.

`webpage-regex` is the widest recipe for a reason: it absorbs three separately
counted forms — `url` + `regex` (577 files), the bare-string shorthand (147) and
the `xpath` variant (15) — because all three come down to "fetch one page, pull
the version out of the text".

Sample manifests per recipe are listed in `recipes.md` under **Samples**. Eight of
the sixteen recipes have no example in this bucket at all and cite upstream files
instead; the other eight cite local manifests. The split is stated in
`recipes.md` itself, so the two documents cannot disagree about it.

## 8. Not covered

Known gaps, in rough order of how likely they are to bite:

- **`checkver.script` cannot be probed offline.** The 55 upstream files that use
  it, and `checkver-script`, need a live Scoop environment, so
  `update --checkver` reports that it cannot run rather than guessing. Use
  `bin/checkver.ps1` for those.
- **140 manifests whose `checkver.github` is an `api.github.com` URL.** Scoop
  appends `/releases/latest` unconditionally, so those values resolve to
  `.../releases/latest/releases/latest` and 404. They never detect a version.
  This is rule `W111`, it is a warning rather than an error because the fix is
  to move the endpoint into `checkver.url`, and `86box` and
  `adventuregamestudio` are live examples.
- **MSI customisation.** `github-msi` covers the two mechanical modes (unpack
  with `Expand-MsiArchive`, or hand to `msiexec`). Per-feature install, MST
  transforms and advertised shortcuts are not modelled.
- **Installer interaction.** Anything that needs a click, a licence dialog or a
  driver prompt is out of scope; `github-exe-installer` will scaffold the script,
  but the body has to be written by hand.
- **Archives over 2 GB.** aria2 and hash verification degrade, so no recipe is
  tuned for them.
- **32bit architecture.** The **596** upstream files that pair `32bit` with
  another architecture are out of scope (section 5). An existing `32bit` +
  `64bit` manifest still lints and updates cleanly — `gen` simply cannot build a
  new one, since `32bit` is not an accepted `arch` value.
- **The single `_comment` file.** Not a documented key; `##` is. The linter does
  not currently flag it.
- **The `checkver` shapes in the bottom rows of section 3.** Around a dozen
  files combine `replace` with something else in a way only that manifest needs,
  and section 4's last row is five one-off autoupdate shapes. Left to
  hand-writing by design.

## 9. Ideas that were measured and rejected

Two plausible rules were checked against upstream and deliberately **not**
implemented. They are recorded because the next person to look will have the
same idea, and a wrong rule is worse than no rule.

- **"`$version` glued to a letter is a mistake."** It looks like one — the
  generator can produce `.../7zTM_$versionz` — but 7 upstream manifests do it on
  purpose, because upstream really does glue the version into a suffix:
  `firefox-esr` needs `releases/$versionesr/`, and `codeblocks-mingw` needs
  `codeblocks-$versionmingw-nosetup.zip`. The token is correct in both. A
  warning here would fire on healthy manifests, so `$version` is only checked
  for *presence* (W110), never for its neighbourhood.
- **"`extract_dir` must agree with `version`."** 111 of the 566 upstream
  manifests put a version-like token in `extract_dir`, and only 17 of those
  tokens differ from `version` — but all 17 are legitimate, because
  `extract_dir` names what the archive *actually* extracts to, not what the
  release is called. `ghidra` is `version: 12.1.3-20260817` against
  `extract_dir: ghidra_12.1.3_PUBLIC`; `wing-101` is `12.0.3.0` against
  `Wing 101 12.0.3`. So `update --version` rewrites the version hard-coded in
  **URLs only** and leaves `extract_dir` alone — `--set extract_dir=...` when
  upstream really did rename the directory.

## 10. Refreshing the survey

The survey script is deliberately **not** shipped: it is a one-off analysis, and
keeping it in the package would make it look like a supported tool. To redo it,
point the corpus path in section 1 at the bucket to measure and tally the same
things — top-level keys, the four shape families, and the `#` fragments. If the
proportions move far enough to invalidate a recipe (say arm64-only manifests
stop being two files), update the affected recipe and the corresponding row here
together, the way `sm_selftest.py` requires for `recipes.md`.
