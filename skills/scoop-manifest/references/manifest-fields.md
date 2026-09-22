# Scoop manifest field reference (this repo's conventions)

This document describes the fields the **Extras-CN** repo (`bucket/*.json`)
actually uses. It is derived from statistics over the 88 manifests here, the
2,389-manifest survey in `references/coverage.md`, and the existing CI config;
nothing is invented about Scoop internals. Treat the
[Scoop Wiki · App Manifests](https://github.com/ScoopInstaller/Scoop/wiki/App-Manifests)
as authoritative.

This repo targets Chinese users, so several conventions differ from the
English-language buckets. Those differences are called out inline and
summarised in section 8.

## 1. File-level conventions

| Item          | Convention                                              | Basis                                                                    |
| :------------ | :------------------------------------------------------ | :----------------------------------------------------------------------- |
| File name     | `<app>.json` where `app` matches `^[a-z0-9][a-z0-9-]*$` | 87/88 comply                                                             |
| Encoding      | UTF-8 without BOM                                       | `.editorconfig`'s `charset = utf-8`                                      |
| Indent        | 4 spaces                                                | `.editorconfig`                                                          |
| Line endings  | CRLF                                                    | `.editorconfig`'s `end_of_line = crlf` plus `.gitattributes`' `eol=crlf` |
| Trailing byte | exactly one newline required                            | `.editorconfig`'s `insert_final_newline = true`                          |
| Non-ASCII     | written literally, never \uXXXX-escaped                 | 57 of the 88 descriptions are Chinese and stored as raw UTF-8            |

Status: all 88 files round-trip byte-identically through the serializer, so no
file currently trips W109. The one file-name deviation is `mpv.net-cm.json`:
its stem contains a `.`, which `^[a-z0-9][a-z0-9-]*$` rejects (E009). Renaming
it would be a breaking change for existing users, so it is left as is.

## 2. Top-level fields

### 2.1 Required fields (CI fails when missing)

| Field         | Type             | Notes                                                                                                 | Sample in this repo                                             |
| :------------ | :--------------- | :---------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------- |
| `version`     | string           | Upstream version, **without the leading `v`**. A github `checkver` strips the tag's `v` automatically | `clash-mi` is `1.0.30.1605`                                     |
| `description` | string           | One-line description. **Chinese is expected here**; an English phrase is also fine                    | 57/88 are Chinese (`douyin` is `抖音`)                          |
| `homepage`    | string           | Upstream homepage or repository URL                                                                   | all 88                                                          |
| `license`     | string or object | Prefer an SPDX identifier; use `{"identifier": ..., "url": ...}` when unsure                          | 10 use the object form (`clash-mi`, `feishu`); 5 of the 78 strings are free text rather than SPDX |
| `checkver`    | string or object | How the version is detected, see section 3                                                            | 86/88 (not `edrawmax8`, `mpv.net-cm`)                           |
| `autoupdate`  | object           | How URLs change on a version bump, see section 4                                                      | 86/88                                                           |

### 2.2 Download and install fields

| Field                              | Type               | Notes                                                                                                                                | Sample in this repo                                |
| :--------------------------------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------- |
| `url`                              | string or string[] | Single-architecture direct download URL. A top-level `url` together with `architecture` is redundant (W108)                          | 30 manifests have no `architecture` block at all    |
| `hash`                             | string or string[] | sha256 of the download. **Must be 64 lowercase hex chars**; when `url` is an array, `hash` must be an array of the same length       | `tts-vue-next` (single, with `#/` fragment)         |
| `architecture`                     | object             | `{"64bit": {...}, "arm64": {...}}`; `64bit` is mandatory                                                                             | 58/88 use it; arm64 is rare here                    |
| `extract_dir`                      | string             | Inner directory name the archive is extracted into                                                                                   | 22 manifests; `msys2-cn`, `vlc-cn`, `quicker`       |
| `extract_to`                       | string             | Subdirectory under `$dir` to extract into, usually the same value as `extract_dir`                                                   | `autotyper`, `utools`, `qunwen`, `feishu`           |
| `innosetup`                        | bool               | Declares an InnoSetup payload so Scoop unpacks it natively, **instead of** a hand-written `installer.script`                         | `lceda`, `lceda-pro`, `edrawmax`, `qingjian`, `navicat-premium-lite-cn` |
| `installer`                        | object             | `{"script": ...}` for a custom install script (string or string array), or `{"file": ..., "args": [...]}` to run a bundled setup exe | `dehelper`, `miniforge-cn`, `neteasemusic`          |
| `uninstaller`                      | object             | `{"script": ...}`, a custom uninstall script                                                                                         | `clash-mi`, `miniforge-cn`                          |
| `pre_install` / `post_install`     | string or string[] | Hooks before and after install                                                                                                       | `miniforge-cn` (both)                               |
| `pre_uninstall` / `post_uninstall` | string or string[] | Hooks before and after uninstall                                                                                                     | `clash-mi`                                          |

### 2.3 Integration fields

| Field          | Type                       | Notes                                                                                                          | Sample in this repo                          |
| :------------- | :------------------------- | :------------------------------------------------------------------------------------------------------------- | :------------------------------------------- |
| `bin`          | string or `[exe, alias][]` | Executables to put on PATH                                                                                     | 20 manifests; `clash-mi` uses a string       |
| `shortcuts`    | `[exe, name][]`            | Start-menu shortcuts. A third and fourth item (arguments, icon) are allowed; **the first two must be strings** | `msys2-cn`, `tts-vue-next` (which passes flags) |
| `persist`      | string or string[]         | Directories / files kept across versions                                                                       | `feishu`, `tim`, `vlc-cn` (21 manifests)     |
| `env_set`      | object                     | Environment variables written on install                                                                       | `mogan-cn`, `baidupcs-go`                    |
| `env_add_path` | string or string[]         | Directories appended to PATH                                                                                   | **none in this bucket**; `texlive` upstream  |
| `psmodule`     | object                     | `{"name": ..., "path": ...}` for a PowerShell module package instead of `bin` / `shortcuts`                    | none here; `completionpredictor` upstream    |
| `suggest`      | object or string           | Packages suggested alongside                                                                                   | `dbeaver-cn`, `libreoffice-cn`               |
| `depends`      | string or string[]         | Hard dependency, **usually pointing at another bucket**: this repo ships no `comfyui`, so a dependency reads `extras/7zip` rather than `scoopforge/comfyui` | **none in this bucket**; `comfyui-manager` upstream |
| `notes`        | string                     | Message printed after install                                                                                  | `wechatdevtools`, `yuque` (13 manifests)     |
| `##`           | string                     | **The documented way to leave a comment inside a manifest.** Scoop ignores it; use it instead of `_comment`    | none here; 54 upstream manifests             |
| `##`           | string                     | **The documented way to leave a comment inside a manifest.** Scoop ignores it; use it instead of `_comment`    | none here; 54 upstream manifests             |

### 2.4 The `#/` fragment in URLs

The trailing `#/name` in a URL decides the file name on disk and
**therefore which way Scoop processes the download**:

| Form                  | Effect                                                                                                              | Sample in this repo                             |
| :-------------------- | :------------------------------------------------------------------------------------------------------------------ | :---------------------------------------------- |
| `...exe#/dl.7z`       | unpack the exe as a 7z archive                                                                                      | 10 manifests; `douyin`, `tim`, `wpsoffice-cn`   |
| `...exe#/name.zip`    | unpack as a zip                                                                                                     | `tts-vue-next` (`#/tts-vue-next.zip`)           |
| `...exe#/setup.exe`   | keep it as an exe and hand it to `installer.script`                                                                 | `dehelper`, `eshelper`, `frhelper`, `dashplayer` |
| `...msi#/setup.msi_`  | keep the MSI as a file; **the trailing `_` hides the extension, so Scoop does not pick `Expand-MsiArchive` for it** | `libreoffice-cn`, `quicker`                     |
| `...?d=x&v=1#/name`   | query string and fragment together                                                                                  | none here; `isobuster` upstream                 |

`lib/decompress.ps1` chooses the extraction function from the **on-disk file
name**, matching `\.zip$`, `\.msi$` and (`innosetup` only) `\.exe$`, then falling
back to "is this 7z-readable". A name ending in `_` matches none of those, which
is the whole point of the convention: without the underscore an `.msi` download
is silently unpacked with `Expand-MsiArchive` instead of reaching your
`installer.script`.

## 3. checkver forms

| Form          | Structure                                            | Use when                                                      | Sample in this repo                      |
| :------------ | :--------------------------------------------------- | :------------------------------------------------------------ | :--------------------------------------- |
| string        | `"checkver": "github"`                               | the GitHub repo can be derived from `url` / `homepage`        | 8 manifests; `baidupcs-go`, `subrenamer` |
| github object | `{"github": "https://github.com/o/r"}`               | the homepage is not GitHub but releases are                   | 18 manifests; `lx-music`, `aigcpanel`    |
| bare regex    | `"checkver": "Version ([\\d.]+)"`                    | the homepage itself lists the version and a regex can read it | none here; 147 upstream manifests        |
| url + regex   | `{"url": ..., "regex": ...}`, optionally `+ replace` | upstream is a website / own CDN                               | 50 manifests; `douyin`, `aboboo`, `tim`  |
| jsonpath      | `{"url": ..., "jsonpath": ...}`, `regex` optional    | only an API or rolling builds are offered                     | 7 manifests; `baidunetdisk`, `kicad-cn`  |
| xpath         | `{"url": ..., "xpath": ..., "regex": ...}`           | the version lives in an XML / RSS document                    | none here; 15 upstream manifests         |
| sourceforge   | `{"sourceforge": "project/path", "regex": ...}`      | upstream is a SourceForge project                             | none here; 15 upstream manifests         |
| script        | `{"script": [...], "regex": ...}`                    | a PowerShell request is needed to get the value               | 3 manifests; `i4tools`, `qqmusic`, `feishu` |

Key points:

- The **`github` and `sourceforge` forms need no `regex`**; `url` and `script`
  must have one.
- **`jsonpath` and `xpath` need no `regex` either.** Scoop uses the picked value
  verbatim, so a regex is optional; `hbuilderx`, `wpsoffice-cn` and
  `baidunetdisk` omit it, and 34 of the 210 upstream `jsonpath` blocks do the
  same.
- **`re` and `jp` are accepted synonyms** for `regex` and `jsonpath`. Scoop
  documents the short forms and the upstream `ScoopInstaller/Extras` bucket uses
  them (44 manifests with `re`, 5 with `jp`); `lyx-cn`, `quarkclouddrive` and
  `clash-mi` use them here. `gen` always emits the canonical spelling, and the
  linter normalises before checking, so neither is reported as a typo.
- **`checkver` with no `url` scrapes `homepage`** — `bin/checkver.ps1` sets
  `$url = $json.homepage` under its "Not Specified" branch. A regex on its own
  is the shorthand for exactly that.
- `reverse`, `replace` and `useragent` need the **object** form; a bare string
  cannot carry them.
- A `checkver.github` value must be a repository URL, **never an
  `api.github.com` one**: Scoop appends `/releases/latest` unconditionally, so
  the API path turns into a 404 (W111). Put the API endpoint in `checkver.url`
  — which is exactly what `clash-mi` and `kicad-cn` do here.
- Prefer a `(?<version>...)` named group; without one Scoop takes the first group.
- A leading `v` in the upstream tag needs no handling; Scoop strips it.
- The `script` form needs a Scoop environment, so this skill's `update --checkver`
  cannot probe it offline and says so explicitly.

## 4. Writing autoupdate

`autoupdate` describes what the URL looks like once the version is `$version`.

| Case                      | Form                                                                            | Sample in this repo             |
| :------------------------ | :------------------------------------------------------------------------------ | :------------------------------ |
| top-level `url`           | `{"url": ".../v$version/app-$version.zip"}`                                     | `douyin`, `partition-assistant` |
| `architecture`            | `{"architecture": {"64bit": {"url": ...}, "arm64": {"url": ...}}}`              | `clash-mi`, `hbuilderx`         |
| hash from a checksum file | `{"url": ..., "hash": {"url": "$url.sha256", "regex": "$sha256\\s+$basename"}}` | none here; `veracrypt` upstream |
| hash from a web page      | `{"url": ..., "hash": {"url": ..., "regex": ...}}`                              | none here; `bitcomet` upstream  |

**Two hard constraints (`lint` checks both)**:

1. If a manifest uses `architecture`, `autoupdate` must also supply
   per-architecture URLs (W103); otherwise Excavator will not update them on
   a bump.
2. If the current download URL carries a version, the `autoupdate` URL must
   carry `$version` (W110); otherwise the version rises while the URL stays put
   and the package goes stale forever. `yuque`, `wegame` and `quarkclouddrive`
   are live examples here.

## 5. Canonical key order

Field order produced by `gen` (`CANONICAL_ORDER` in `sm_lib.py`):

```text
## → version → description → homepage → license → notes → architecture → url
→ hash → pre_install → installer → innosetup → extract_dir → extract_to
→ post_install → psmodule → bin → shortcuts → persist → env_set → env_add_path
→ suggest → depends → uninstaller → pre_uninstall → post_uninstall
→ checkver → autoupdate
```

Nested levels have their own order:

| Parent                      | Order                                                                                                                                          |
| :-------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------- |
| `architecture`              | `64bit` → `arm64`                                                                                                                              |
| `architecture.<arch>`       | `url`, `hash`, `pre_install`, `installer`, `innosetup`, `extract_dir`, `extract_to`, `post_install`, `psmodule`, `bin`, `shortcuts`, `persist` |
| `checkver`                  | `github`, `url`, `sourceforge`, `script`, `jsonpath`, `xpath`, `regex`, `replace`, `reverse`, `useragent`                                      |
| `autoupdate`                | `architecture`, `url`, `hash`, `extract_dir`, `bin`, `shortcuts`                                                                               |
| `installer` / `uninstaller` | `script`, `args`                                                                                                                               |
| `hash`                      | `url`, `regex`, `jsonpath`                                                                                                                     |

Only `64bit` and `arm64` are recognised. `arch` takes one of them, or the two
joined with `+`; anything else is rejected with the list of valid values.
**32bit is out of scope by decision**, so `url32` / `hash32` are neither
accepted nor generated, and `32bit` is not a valid `arch` value.

`update` **does not rewrite the whole file** (avoiding huge diffs): existing
fields keep their position and only new fields are inserted in the order
above. Pass `--reorder` to rewrite everything.

## 6. When not to use this skill

- PowerShell build outputs, MSI customisation, or private unpacking logic
  beyond `$PLUGINSDIR` -- writing the manifest by hand is easier.
- Upstream ships an installer that needs interaction and cannot run silently.
- Archives over 2GB (Scoop's `aria2` and hash verification degrade).
- Anything that would have to modify `scripts/AppsUtils.psm1`. It is this repo's
  own helper module, imported by 3 manifests; a new app may import it, but the
  skill does not generate or edit it.

## 7. Related files

- Which recipe applies, and what it emits: `references/recipes.md`
- Where the recipes came from, and what is not covered: `references/coverage.md`
- Lint rules: `references/lint-rules.md`
- Recipe data (single source of truth): `assets/recipes.jsonc`

## 8. How this repo differs from the English-language buckets

| Area | Extras-CN | Why it matters when writing a manifest |
| :--- | :--- | :--- |
| `description` | Chinese for 57 of 88 | Write it in Chinese when the app is China-only. W101's capitalization / trailing-period / length rules are skipped for CJK text, so `抖音` is fine. |
| README sections | `跨平台` / `Win 专属` / `开源镜像` | `gen --section` takes one of these, not `General Use` / `Win-Only`. The 跨平台 table is further split by `####` sub-headings (外语学习, 学术研究, 软件开发, 日常使用). |
| `depends` / `suggest` | other buckets only | There is no `scoopforge/` app to depend on here; point at `extras/7zip`-style references instead. |
| Download hosts | often no https | 9 manifests carry a plaintext `http://` somewhere; do not "fix" W102 on a vendor that offers no TLS. |
| `version` shape | often a date or a build string | `26H1-25388281`, `2026-06-11`, `1.0.30.1605` are normal; W107 is advisory. |
