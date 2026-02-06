# 🍨 Extras-CN 🍨

[![Excavator](https://github.com/Scoopforge/Extras-CN/actions/workflows/ci.yml/badge.svg)](https://github.com/Scoopforge/Extras-CN/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/Scoopforge/Extras-CN)](https://github.com/Scoopforge/Extras-CN/blob/master/LICENSE)
[![code size](https://img.shields.io/github/languages/code-size/Scoopforge/Extras-CN.svg)](https://img.shields.io/github/languages/code-size/Scoopforge/Extras-CN.svg)
[![repo size](https://img.shields.io/github/repo-size/Scoopforge/Extras-CN.svg)](https://img.shields.io/github/repo-size/Scoopforge/Extras-CN.svg)

专注于服务国人的 Windows 最佳包管理器 [Scoop](https://github.com/ScoopInstaller/Scoop)扩展库

> ⚠️ 为更好的进行管理，本仓库只收录主要针对国内用户的软件，国际通用软件请添加仓库[Extras-Plus](https://github.com/Scoopforge/Extras-Plus)。
>
> ⚠️ For a better management, this repo now only contains manifests of softwares for Chinese users, for international softwares, please add the bucket [Extras-Plus](https://github.com/Scoopforge/Extras-Plus).

## 🏃 开始

对于熟悉 Scoop 的用户：

```powershell
scoop bucket add extras-cn https://github.com/Scoopforge/Extras-CN
```

## 🚲 安装 Scoop

### 💻 步骤 1：在 PowerShell 中打开远程权限

```powershell
Set-ExecutionPolicy RemoteSigned -scope CurrentUser
```

### ⚙️ 步骤 2：下载并安装 Scoop

```powershell
irm get.scoop.sh -outfile 'install.ps1'
.\install.ps1 -ScoopDir ['Scoop_Path'] -ScoopGlobalDir ['GlobalScoopApps_Path'] -NoProxy
# 例如
.\install.ps1 -ScoopDir 'C:\Scoop' -ScoopGlobalDir 'C:\Program Files' -NoProxy
```

> 如果跳过该步骤，Scoop 将默认把所有用户安装的 App 和 Scoop 本身置于 `c:/users/user_name/scoop`

### 📖 步骤 3：通过`scoop help`查看快速上手方法

更多信息，请访问 Scoop 官网 👉 <https://scoop.sh/> 👈

## 🚗 利用扩展库安装 App

### 🚋 步骤 1：安装 Aria2 来加速下载

```powershell
scoop install aria2
```

如果使用 VPN，需要通过如下命令关闭 aria2

```powershell
scoop config aria2-enabled false
```

### 🎫 步骤 2：安装 Git 来添加新仓库

```powershell
scoop install git
```

### ✈️ 步骤 3：添加本仓库并更新，么么哒~ 💋

```powershell
scoop bucket add extras-cn https://github.com/Scoopforge/Extras-CN
scoop update
```

### 🚀 步骤 4：安装 App

#### 使用 `scoop search` 命令搜索 App 的具体名称

```powershell
scoop search <app_name>
```

#### 利用插件 `scoop-completion` 协助安装

```powershell
scoop install scoop-completion
scoop install <app_name>
```

> 使用`scoop-completion`：键入 App 名称的前几个字母后敲击`tab`键进行补全

## 📝 杂项

### Aria2 的参数自定义

```powershell
# aria2 在 Scoop 中默认开启
scoop config aria2-enabled true
# 关于以下参数的作用，详见 aria2 的相关资料
scoop config aria2-retry-wait 4
scoop config aria2-split 16
scoop config aria2-max-connection-per-server 16
scoop config aria2-min-split-size 4M
```

## ⭐️ 总结

### 跨平台

#### 外语学习

|   中文名称   |                          App                           | 自动更新 |  备注  |
|:------------:|:------------------------------------------------------:|:--------:|:------:|
|  阿波波外语  |              [aboboo](http://aboboo.com)               |    ✓     | 精简版 |
|  阿波波外语  |            [aboboo-full](http://aboboo.com)            |    ✓     | 完整版 |
|   欧路词典   |               [eudic](https://eudic.net)               |    ✓     |        |
|   德语助手   |    [dehelper](https://eudic.net/v4/es/app/dehelper)    |    ✓     |        |
|   西语助手   |    [eshelper](https://eudic.net/v4/es/app/eshelper)    |    ✓     |        |
|   法语助手   |    [frhelper](https://eudic.net/v4/fr/app/frhelper)    |    ✓     |        |
| 每日英语听力 |         [ting-en](http://dict.eudic.net/ting)          |    ✓     |        |
| 每日德语听力 |      [ting-de](https://eudic.net/v4/de/app/ting)       |    ✓     |        |
| 每日西语听力 |      [ting-es](https://eudic.net/v4/es/app/ting)       |    ✓     |        |
| 每日法语听力 |      [ting-fr](https://eudic.net/v4/fr/app/ting)       |    ✓     |        |
|  DashPlayer  | [dashplayer](https://github.com/solidSpoon/DashPlayer) |    ✓     |        |
| Pot-Desktop  |           [pot-desktop](https://pot-app.com)           |    ✓     |        |

#### 学术研究

|   中文名称   |                        App                         | 自动更新 |      备注       |
|:------------:|:--------------------------------------------------:|:--------:|:---------------:|
|  CAJViewer   | [cajviewer](https://cajviewer.cnki.net/index.html) |    ✓     | by @rayinfinite |
|   FreeTex    |        [freetex](https://xdxsb.top/FreeTex)        |    ✓     |                 |
| 全球学术快报 |      [cnkiexpress](https://express.cnki.net)       |    ✓     | by @rayinfinite |
|   KingDraw   |           [kingdraw](http://kingdraw.cn)           |    ✓     |                 |

#### 软件开发

|     中文名称      |                                            App                                            | 自动更新 | 备注 |
|:-----------------:|:-----------------------------------------------------------------------------------------:|:--------:|:----:|
|     HBuilderX     |                       [hbuilderx](https://dcloud.io/hbuilderx.html)                       |    ✓     |      |
| 嘉立创 EDA 标准版 |                                 [lceda](https://lceda.cn)                                 |    ✓     |      |
|  微信小程序 SDK   | [wechatdevtools](https://developers.weixin.qq.com/miniprogram/dev/devtools/devtools.html) |    ✓     |      |

#### 日常使用

|    中文名称     |                               App                                | 自动更新 |                         备注                         |
|:---------------:|:----------------------------------------------------------------:|:--------:|:----------------------------------------------------:|
|    阿里云盘     |                   [adrive](https://alipan.com)                   |    ✓     |                                                      |
|    百度云盘     |          [baidunetdisk](https://pan.baidu.com/download)          |    ✓     |                   推荐 WinGet 安装                   |
|      钉钉       |                 [dingtalk](https://dingtalk.com)                 |    ✓     |                                                      |
|      抖音       |                   [douyin](https://douyin.com)                   |    ✓     |                                                      |
|   哔哩下载姬    |         [downkyi](https://github.com/leiurayer/downkyi)          |    ✓     |                     by @CronusLM                     |
|    Edgeless     |              [edgeless](https://home.edgeless.top)               |    ✓     |                   by @IsaacWangTT                    |
|    亿图图示     |                 [edrawmax](https://edrawsoft.cn)                 |    ✓     |                                                      |
|      飞书       |                   [feishu](https://feishu.cn)                    |    ✓     |                                                      |
|     EV 录屏     |           [evcapture](https://ieway.cn/evcapture.html)           |    ✓     |                                                      |
|      剪映       |                [jianying-pro](https://capcut.cn)                 |    ✓     |                                                      |
|    爱思助手     |               [i4tools](https://i4.cn/pro_pc.html)               |    ✓     |                                                      |
|  洛雪音乐助手   |     [lx-music](https://github.com/lyswhut/lx-music-desktop)      |    ✓     |                                                      |
|   网易云音乐    |              [neteasemusic](https://music.163.com)               |    ✓     |                                                      |
|    腾讯会议     |          [tencent-meeting](https://meeting.tencent.com)          |    ✓     |                    by @Ryanjiena                     |
|    夸克网盘     |             [quarkclouddrive](https://pan.quark.cn)              |    ✓     |                                                      |
|       TIM       |                    [tim](https://tim.qq.com)                     |    ✓     |                                                      |
|     QQ 音乐     |                  [qqmusic](hhttps://y.qq.com/)                   |    ✓     |                                                      |
|     uTools      |                    [utools](https://u.tools)                     |    ✓     |                                                      |
|     小狼毫      |                    [weasel](https://rime.im)                     |    ✓     |                                                      |
|    WPSOffice    |             [wpsoffice-cn](https://wps.com/zh-hant)              |    ✓     |                                                      |
|      语雀       |                    [yuque](https://yuque.com)                    |    ✓     | 复制于 [dorado](https://github.com/chawyehsu/dorado) |
|    AIGCPanel    |                [aigcpanel](https://aigcpanel.com)                |    ✓     |                                                      |
|   BaiduPCS-Go   |      [baidupcs-go](https://github.com/qjfoidnh/BaiduPCS-Go)      |    ✓     |                                                      |
|    Clash-MI     |                 [clash-mi](https://clashmi.app/)                 |    ✓     |                                                      |
|     eSearch     |        [esearch](https://github.com/xushengfeng/eSearch)         |    ✓     |                                                      |
|  Fishing-Funds  |     [fishing-funds](https://github.com/1zilc/fishing-funds)      |    ✓     |                                                      |
|     WeGame      |               [wegame](https://www.wegame.com.cn)                |    ✓     |                                                      |
| M3u8-Downloader | [m3u8-downloader](https://github.com/HeiSir2014/M3U8-Downloader) |    ✓     |                                                      |

### Win 专属

|        中文名称        |                                     App                                     | 自动更新 |     备注     |
|:----------------------:|:---------------------------------------------------------------------------:|:--------:|:------------:|
|    MisakaTranslator    |     [misakatranslator](https://github.com/hanmin0822/MisakaTranslator)      |    ✓     | by @CronusLM |
|       mpv.net_CM       |          [mpv.net-cm](https://hooke007.github.io/index2#mpvnetcm)           |    ✓     |              |
|   HEU_KMS_Activator    |       [heu-kms-activator](https://github.com/zbezj/HEU_KMS_Activator)       |    ✓     |              |
|    LKY-OfficeTools     |     [lky-officetools](https://github.com/OdysseusYuan/LKY_OfficeTools)      |    ✓     |              |
|   PHPStudy2016 scoop   | [phpstudy-lagecy-scoop](https://github.com/chawyehsu/phpstudy-lagecy-scoop) |    ✓     |              |
|         Reader         |                 [reader](https://github.com/binbyu/Reader)                  |    ✓     |              |
|        RegEster        |          [regester](https://deerchao.cn/tools/regester/index.htm)           |    ✓     |              |
|       SubRenamer       |             [subrenamer](https://github.com/arition/SubRenamer)             |    ✓     |              |
|   WiFi 密码暴力破解    |      [wifi-crack-tool](https://github.com/baihengaead/wifi-crack-tool)      |    ✓     |              |
|      傲梅分区助手      |                 [partition-assistant](https://disktool.cn)                  |    ✓     |              |
|       软件屏蔽器       |          [malware-patch](https://github.com/the1812/Malware-Patch)          |    ✓     |              |
| 微信/QQ/TIM 防撤回补丁 |    [revoke-msg-patcher](https://github.com/huiyadanli/RevokeMsgPatcher)     |    ✓     |              |

### 开源镜像

|           App           | 自动更新 |
|:-----------------------:|:--------:|
|       Blender-cn        |    ✓     |
|       DBeaver-cn        |    ✓     |
|         GIMP-cn         |    ✓     |
|       GIMP@dev-cn       |    ✓     |
|       Inkscape-cn       |    ✓     |
|        Julia-cn         |    ✓     |
|        KiCAD-cn         |    ✓     |
|     LibreOffice-cn      |    ✓     |
|         LyX-cn          |    ✓     |
|      Miniforge-cn       |    ✓     |
|        Mogan-cn         |    ✓     |
|        MSYS2-cn         |    ✓     |
| Navicat-Premium-Lite-cn |    ✓     |
|      OBS-Studio-cn      |    ✓     |
|        Octave-cn        |    ✓     |
|      Qt-Creator-cn      |    ✓     |
|      TeXStudio-cn       |    ✓     |
|         VLC-cn          |    ✓     |

## 备注

由于 Win 到权限管理复杂，对于一些常见的不提供 portable 安装包，且需要管理员应用的权限，建议使用 WinGet 进行安装

```powershell
scoop install winget
winget install Rakuten.Viber
```
