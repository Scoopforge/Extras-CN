# Recipe catalog (16 recipes)

A recipe is a template for one combination of fields, autoupdate shape and
checkver form. The data source is `assets/recipes.jsonc`; this document is the
readable version, kept in sync by `scripts/sm_selftest.py`.

Decision order: **look at what upstream publishes first, then at how to unpack
it.**

```text
GitHub Release
  portable archive (.zip/.7z)      → github-portable-zip
  electron-builder NSIS .exe       → github-nsis-7z
  InnoSetup .exe                   → github-innosetup
  .msi installer                   → github-msi
  installer must actually run      → github-exe-installer
  bare .exe (portable build)       → github-single-exe
  source tag archive               → github-source-archive
  asset list carries extra fields  → github-asset-jsonpath
non-GitHub / own CDN
  HTML page / version API          → webpage-regex
  JSON API (rolling build)         → api-jsonpath
  version needs a script           → checkver-script
  SourceForge project              → sourceforge
  PowerShell Gallery module        → powershell-gallery
  fixed redirect URL               → redirect-arch
several downloads in one package   → portable-multifile
plugin (into a host app)           → github-git-clone
```

Where each recipe came from, and what is still uncovered, is in
`references/coverage.md`. The **Samples** line under each recipe cites files
from this repo where a manifest of that shape exists, and says "none in this
bucket" and falls back to the upstream `ScoopInstaller/Extras` bucket otherwise.

The distribution here leans non-GitHub much harder than upstream does: 21 of the
88 manifests are plain `url` + `regex` against a vendor site, which is why
`webpage-regex` is the widest recipe in this bucket's practice as well as in
theory. Eight of the sixteen recipes have no local example at all
(`github-single-exe`, `github-asset-jsonpath`, `github-source-archive`,
`powershell-gallery`, `sourceforge`, `redirect-arch`, `portable-multifile`,
`github-git-clone`) -- they stay in the catalog because a new app can need them
at any time, not because the current corpus exercises them.

## github-portable-zip

**Use when** the release ships an archive that works as-is, with no installer.

**Required** `version`, `desc`, `homepage`, `license`, `url64`

**Optional** `repo_url`, `arch`, `url_arm64`, `extract_dir`,
`shortcut_exe`, `shortcut_name`, `persist`, `suggest`

**Output** with a single architecture the `url` / `hash` pair lands at the top
level; listing several in `arch` emits an `architecture` block instead.

**Samples** `lx-music`, `aigcpanel`, `obs-studio-cn`, `quickbib`, `retain-pdf`,
`local-mini-drama`, `m3u8-downloader`, `tts-vue-next`

```powershell
scoop_manifest.py gen --name myapp --recipe github-portable-zip `
  --version 1.2.3 --desc "Portable note taking app" `
  --homepage https://github.com/acme/myapp --license MIT `
  --url64 "https://github.com/acme/myapp/releases/download/v1.2.3/app.zip" `
  --repo-url https://github.com/acme/myapp --extract-dir myapp-1.2.3 `
  --shortcut-exe myapp.exe --shortcut-name MyApp --section "跨平台"
```

## github-nsis-7z

**Use when** the release is an NSIS installer built by an electron app. The
installer is a self-extracting shell and the real program lives in a 7z under
`$PLUGINSDIR`; treating the shell as a 7z is the cleanest route.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `shortcut_exe`

**Optional** `repo_url`, `arch`, `url_arm64`, `nsis_payload`, `shortcut_name`,
`bin_exe`, `bin_alias`, `persist`

**Key point** the URL must carry `#/dl.7z`. With one architecture the inner
payload defaults to `app-64.7z`; add `url_arm64` and the arm64 branch gets its
own `installer` entry pointing at `app-arm64.7z`, with a matching per
architecture `autoupdate`.

**Samples** `autotyper`, `utools`, `qunwen`, `yuque`, `wechatdevtools`,
`eudic` (the first four are the `#/dl.7z` shape; `wechatdevtools` and `eudic`
carry the same `$PLUGINSDIR` payload handling on top of an explicit
`installer.script`)

Output (single architecture):

```json
{
    "url": "https://github.com/o/r/releases/download/v1.2.3/App-1.2.3.exe#/dl.7z",
    "installer": {
        "script": "7z x $original_dir/`$PLUGINSDIR/app-64.7z -o\"$original_dir\""
    },
    "extract_dir": "$PLUGINSDIR",
    "extract_to": "PLUGINSDIR",
    "post_install": "Remove-Item -RECURSE $original_dir/`$PLUGINSDIR"
}
```

## github-innosetup

**Use when** the release is an InnoSetup `.exe`. Scoop unpacks it natively, so
**just set `"innosetup": true`** and do not write an `installer.script`.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `shortcut_exe`

**Optional** `repo_url`, `arch`, `url_arm64`, `shortcut_name`,
`bin_exe`, `bin_alias`, `persist`

**Samples** `lceda`, `lceda-pro`, `edrawmax`, `qingjian`,
`navicat-premium-lite-cn`, `freetex`

## github-exe-installer

**Use when** the installer genuinely must run -- it writes registry keys,
installs drivers, or files have to move out of a subdirectory into `$dir`.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, plus either
`installer_script` or `installer_file`

**Optional** `repo_url`, `installer_args`, `pre_install`, `uninstaller_script`,
`post_install`, `pre_uninstall`, `post_uninstall`, `shortcut_exe`,
`shortcut_name`, `bin_exe`, `bin_alias`, `persist`

**Note** do not add a `#/dl.*` fragment to the URL, or Scoop unpacks the
installer instead of running it. Use `installer_file` + `installer_args` when
the vendor's own silent flags are enough and no script is needed.

**Samples** `dashplayer`, `esearch`, `dehelper`, `eshelper`, `frhelper`,
`neteasemusic`, `miniforge-cn`, `vmware-workstation-pro`

## github-single-exe

**Use when** the release is one bare exe, usable as-is.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `shortcut_exe`

**Optional** `repo_url`, `shortcut_name`, `bin_exe`, `bin_alias`, `persist`

**Samples** none in this bucket; `configure-defender`, `netlogo`,
`defender-remover` (upstream `ScoopInstaller/Extras`). Every single-exe release
here still needs an `extract_dir` or a shortcut, so it lands on
`github-portable-zip` instead.

## webpage-regex

**Use when** upstream is not GitHub; the version comes from a web page or a
version endpoint that a plain regex can read.

**Required** `version`, `desc`, `homepage`, `license`, `url`, `checkver_regex`

**Optional** `checkver_url` (the page to scrape; **omit it to scrape
`homepage`**, which collapses `checkver` to the bare regex string), `url_au` (an
autoupdate template; when omitted the version in
`url` is swapped for `$version`), `au_hash_url` + `au_hash_regex` (hash from a
checksum file), `checkver_reverse` (take the last match), `checkver_xpath`
(for XML pages), `checkver_useragent`, `extract_dir`, `installer_script`,
`innosetup`, `persist`

**Key point** the bare-string form is the one upstream uses 147 times and it is
what Scoop reads as "run this regex over `homepage`". It is only emitted when
the regex is the sole checkver key, because `replace` / `reverse` / `useragent`
need the object form.

**Samples** `douyin`, `aboboo`, `evcapture`, `edgeless`, `jianying-pro`,
`lky-officetools`, `tencent-meeting`, `partition-assistant` (the dominant shape
in this bucket: 21 manifests)

```powershell
scoop_manifest.py gen --name myapp --recipe webpage-regex `
  --version 2.0.1 --desc "Data recovery utility" `
  --homepage https://example.com --license Shareware `
  --url "https://example.com/dl/MyApp-2.0.1.exe" `
  --checkver-url https://example.com/download.php `
  --checkver-regex "MyApp-([\d.]+)\.exe" `
  --shortcut-exe MyApp.exe --shortcut-name MyApp --section "Win 专属"
```

## api-jsonpath

**Use when** upstream only offers an API, or only rolling builds, so the
version has to be picked out of a JSON document.

**Required** `version`, `desc`, `homepage`, `license`, `url`, `checkver_url`,
`checkver_jsonpath`, `checkver_regex`

**Optional** `checkver_replace` (rearranges named groups into a version),
`checkver_reverse`, `depends`, `installer_script`, `extract_dir`

**Samples** `ainiee`, `baidunetdisk`, `goldendict-ng`, `kicad-cn`, `clash-mi`

`baidunetdisk` reads the version straight out of an API response, with no regex
at all -- the picked value *is* the version, which is why `checkver_regex` is not
required when `checkver_jsonpath` is present:

```json
"checkver": {
    "url": "https://pan.baidu.com/disk/cmsdata?do=client",
    "jsonpath": "$.winclient.version"
}
```

The `replace` form, for when the version has to be assembled from named groups:

```json
"checkver": {
    "url": "https://api.github.com/repos/Comfy-Org/ComfyUI-Manager/commits/main",
    "jsonpath": "$.commit.committer.date",
    "regex": "(?<year>\\d{4})-(?<month>\\d{2})-(?<day>\\d{2})T(?<hour>\\d{2}):(?<min>\\d{2}):(?<sec>\\d{2})Z",
    "replace": "${year}.${month}.${day}.${hour}${min}${sec}"
}
```

## github-asset-jsonpath

**Use when** the release filename carries more than the version -- a build
number, a codename -- so swapping `$version` in the download URL is not enough.
Read the asset list from the GitHub API and carry the extra fields through
`$match*` placeholders.

**Required** `version`, `desc`, `homepage`, `license`, `url64`,
`checkver_url`, `checkver_jsonpath`, `checkver_regex`, `url_au`

**Optional** `arch`, `url_arm64`, `extract_dir`, `shortcut_exe`,
`shortcut_name`, `bin_exe`, `bin_alias`, `persist`, `suggest`

**Key point** put the API endpoint in `checkver_url`, **never** in
`checkver.github`: Scoop appends `/releases/latest` to the `github` value
whatever it holds, which turns an API URL into a 404 (rule W111). A named
group `(?<build>...)` in `checkver_regex` becomes `$matchBuild` in
`url_au`; `(?<name>...)` becomes `$matchName`.

**Samples** none in this bucket; `86box`, `adventuregamestudio`,
`aegisub-arch1t3cht`, `age`, `anki`, `anytype` (all in the upstream
`ScoopInstaller/Extras` bucket)

```json
{
    "checkver": {
        "url": "https://api.github.com/repos/86Box/86Box/releases/latest",
        "jsonpath": "$.assets[*].browser_download_url",
        "regex": "v(?<version>[\\d.]+)/86Box-Windows-64-b(?<build>\\d+)\\.zip"
    },
    "autoupdate": {
        "url": "https://github.com/86Box/86Box/releases/download/v$matchVersion/86Box-Windows-64-b$matchBuild.zip"
    }
}
```

## github-source-archive

**Use when** the release is a source snapshot (`archive/refs/tags/v$version`)
rather than a built binary, or the archive expands to a version-stamped
directory that autoupdate has to re-template.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `extract_dir`

**Optional** `repo_url`, `hash64`, `au_hash_url` + `au_hash_regex`,
`pre_install`, `shortcut_exe`, `bin_exe`, `bin_alias`, `persist`, `depends`

**Key point** when `extract_dir` contains the version, `gen` also writes
`autoupdate.extract_dir` with `$version`, otherwise Excavator would bump the
URL and leave the directory name behind. Apache projects publish
`sha512:` digests, which Scoop accepts only because `autoupdate.hash` says
where to refetch them.

**Samples** none in this bucket; `86box-roms`, `activemq-artemis`, `activemq`,
`aircrack-ng`, `antimicrox`, `audacity` (upstream `ScoopInstaller/Extras`).
`msys2-cn` and `miniforge-cn` both expand to version-stamped directories, but
each resolves it through a `script` or `url` checkver, so they land elsewhere.

## github-msi

**Use when** the download is an `.msi`.

**Required** `version`, `desc`, `homepage`, `license`, `url64`

**Optional** `repo_url`, `msi_mode`, `msi_args`, `shortcut_exe`,
`shortcut_name`, `bin_exe`, `bin_alias`, `persist`, `suggest`

**Key point** name the file with a `#/*.msi_` fragment (`#/dl.msi_`,
`#/setup.msi_`). The trailing `_` tells Scoop not to unpack it. Then pick a
mode:

- `msi_mode=extract` (default) -- `Expand-MsiArchive` into `$dir`, so the
  package stays portable and needs no admin rights
- `msi_mode=install` -- hand it to `msiexec /i`, and `msiexec /x` in
  `pre_uninstall`. Both steps check `is_admin` and re-launch elevated

**Samples** `libreoffice-cn`, `quicker` (both via `msi_mode=extract` behind an
`installer.script`); plain `msi_mode` samples: `libreoffice`, `gtk-sharp`,
`msxml4`, `openvpn` (upstream `ScoopInstaller/Extras`)

## powershell-gallery

**Use when** the package is a PowerShell module published to the PowerShell
Gallery as a `.nupkg`, installed through the `psmodule` block instead of
`bin` / `shortcuts`.

**Required** `version`, `desc`, `homepage`, `license`, `url`, `checkver_url`,
`checkver_regex`, `psmodule_name`

**Optional** `psmodule_path`, `pre_install`, `url_au`

**Key point** the default `pre_install` drops the NuGet packaging leftovers
(`_rels`, `package`, `*Content*.xml`) so Scoop treats the directory as a plain
module folder. `checkver_url` is the gallery page for the module.

**Samples** none in this bucket; `completionpredictor`, `dockercompletion`,
`git-aliases`, `posh-docker`, `leet` (upstream `ScoopInstaller/Extras`)

## checkver-script

**Use when** the version only becomes visible after a request the manifest
itself has to make: following a redirect, or calling an endpoint whose URL is
computed at run time.

**Required** `version`, `desc`, `homepage`, `license`, `url`,
`checkver_script`, `checkver_regex`

**Optional** `url_au`, `au_hash_url` + `au_hash_regex`, `extract_dir`,
`pre_install`, `shortcut_exe`, `bin_exe`, `bin_alias`, `persist`

**Key point** the script's return value is the text `checkver_regex` runs
against. It needs a Scoop environment, so `update --checkver` reports that it
cannot probe it offline and points at `bin/checkver.ps1`.

**Samples** `i4tools`, `qqmusic` (both `script` + `regex`); other
`checkver.script` samples: `airdroid`, `anydesk`, `betterbird`, `bifrost`,
`blender`, `dolphin` (upstream `ScoopInstaller/Extras`)

## sourceforge

**Use when** upstream lives on SourceForge. The `sourceforge` checkver key
queries the project RSS on its own, so no page scraping is involved.

**Required** `version`, `desc`, `homepage`, `license`, `url`,
`checkver_sourceforge`, `checkver_regex`

**Optional** `url_au`, `au_hash_url` + `au_hash_regex`, `extract_dir`,
`pre_install`, `shortcut_exe`, `bin_exe`, `bin_alias`, `persist`

**Samples** none in this bucket; `beebeep`, `cdburnerxp`, `chart-geany`,
`crystaldiskinfo`, `crystaldiskmark`, `cudatext` (upstream
`ScoopInstaller/Extras`)

## redirect-arch

**Use when** upstream serves a permanent `latest/redirect`-style link that
contains **no version number**. The URL never changes, so the version must be
probed elsewhere (e.g. the winget-pkgs commit history).

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `url_arm64`,
`checkver_url`, `checkver_regex`, `shortcut_exe`

**Note** such a manifest **carries no `hash`** -- the content behind the same
URL changes, so a pinned hash would fail as soon as upstream ships.

**Samples** none in this bucket; `claude-desktop` (upstream
`Scoopforge/Extras-Plus`)

## portable-multifile

**Use when** one package needs several downloads: the main archive plus a
helper script, an icon, or a hotfix archive. `url` and `hash` become arrays.

**Required** `version`, `desc`, `homepage`, `license`, `url64`, `hash64`,
`extra_urls`, `extra_hashes`

**Optional** `extract_dir`, `pre_install`, `post_install`, `shortcut_exe`,
`shortcut_name`, `bin_entries`, `persist`, `env_add_path`, `env_set`

**Key point** the two arrays must line up one for one; `gen` refuses a
mismatch instead of writing a manifest Scoop cannot verify. `autoupdate`
tracks only the main download, because Scoop cannot re-derive a sidecar URL.

**Samples** none in this bucket; `7ztm`, `bytecode-viewer`, `camstudio`,
`context-menu-manager`, `appengine-go` (upstream `ScoopInstaller/Extras`)

## github-git-clone

**Use when** the package is not an executable but a plugin / extension for a
host application and must be `git clone`d into the host directory.

**Required** `version`, `desc`, `homepage`, `license`, `url`, `depends`,
`installer_script`, `checkver_url`, `checkver_jsonpath`, `checkver_regex`

**Optional** `checkver_replace`, `extract_dir`, `uninstaller_script`,
`post_uninstall`

**Samples** none in this bucket; `comfyui-manager` (upstream
`Scoopforge/Extras-Plus`) is the only manifest either bucket has of this shape,
and it is a hand-written pattern rather than one upstream justified

## Adding a recipe

1. Add an entry to the `recipes` array in `assets/recipes.jsonc` with `id` /
   `label` / `when` / `builder` / `required` / `optional` / `refs`, and add the
   new parameters to `param_docs`.
2. Register a builder of the same name in `BUILDERS` in `scripts/sm_lib.py`.
3. Add a `## <recipe id>` section to this document.
4. Run `python scripts/sm_selftest.py` -- it catches four kinds of drift:
   no builder for a recipe, an unreferenced builder, an undocumented required
   parameter, and a missing doc section.
