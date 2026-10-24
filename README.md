# py3-pymupdf · Alpine apk builder

用 **Alpine 发行版自带的 Python 与 MuPDF**（`apk add mupdf mupdf-dev python3-dev`）编译
[PyMuPDF](https://github.com/pymupdf/PyMuPDF)，打包成可直接安装的 Alpine `.apk`，推一个日期 tag
就把整套包一次性构建并发布。

Builds [PyMuPDF](https://github.com/pymupdf/PyMuPDF) against the Python and MuPDF that each
Alpine release ships (`apk add mupdf mupdf-dev python3-dev`), packages it as an installable
Alpine `.apk`, and a single date tag builds and publishes the whole set at once.

> **apk 是 Alpine Linux 软件包，不是 Android 安装包。**
> "apk" here means an Alpine Linux package, not an Android app.

## 最新发布 / Latest release

**r20261024** · 6 个包 · 2026-10-24 — <https://github.com/dainan13/pymupdf-fitz-alpine/releases/tag/r20261024>

Six packages, one release:

| apk | PyMuPDF | 构建于 Built on | 安装于 Installs on | 大小 Size | sha256 |
| --- | --- | --- | --- | --- | --- |
| `py3-pymupdf-1.13.20-r20261024.apk` | 1.13.20 | Alpine 3.8 / Python 3.6 | 3.8, 3.9 | 228 KiB | `5722e574f60c681109b0fd5d3e84a8d177034b003dc82f4599bc45f82c412a84` |
| `py3-pymupdf-1.16.18-r20261024.apk` | 1.16.18 | Alpine 3.11 / Python 3.8 | 3.11 | 310 KiB | `06dff0460897b8936be89457d3facbd71953dc0b3d4242a442e8ebb211f48df3` |
| `py3-pymupdf-1.18.0-r20261024.apk` | 1.18.0 | Alpine 3.13 / Python 3.8 | 3.13 | 384 KiB | `49036081d281ac2cd1b8b5b9e8e6abca66ad2a0a32f57254913e43e96c7ff25d` |
| `py3-pymupdf-1.18.1-r20261024.apk` | 1.18.1 | Alpine 3.14 / Python 3.9 | 3.14 | 385 KiB | `7c2bec459be5f0f0d2a0ddb8cbd2999360d066e6266ee093972c9d641167a6dd` |
| `py3-pymupdf-1.19.6-r20261024.apk` | 1.19.6 | Alpine 3.15 / Python 3.9 | 3.15 | 493 KiB | `85d0c1b7d937955449cdc1bb2c2b75a07f941b6cafbc2d15e5f7c8258849d305` |
| `py3-pymupdf-1.19.5-r20261024.apk` | 1.19.5 | Alpine 3.16 / Python 3.10 | 3.16 | 495 KiB | `a35651daf34bf6f3e19f872d8b065e931938fbbd1e60e4b1f47120cedff842c1` |

Release 里还有 `SHA256SUMS`、每个包对应的 `APKBUILD-<版本>-r20261024`、以及签名公钥。
The release also carries `SHA256SUMS`, the exact `APKBUILD-<version>-r20261024` used for each
package, and the signing keys.

⚠️ 这一版**没有配置固定签名密钥**，6 个包各自用一个一次性密钥签名，所以 Release 里有 6 个
`builder-*.rsa.pub`。要用签名校验安装，得装对应那个公钥；想统一成一把钥匙，配置
`ABUILD_PRIVKEY` / `ABUILD_PUBKEY` secrets 后重新发布即可（见下文"签名"）。

This release was built **without a configured signing key**, so each package is signed by its
own throw-away key and the release contains six `builder-*.rsa.pub` files. To verify signatures
you must install the matching key; configure `ABUILD_PRIVKEY` / `ABUILD_PUBKEY` secrets and
re-release if you want a single stable key.

## 安装 / Install

挑与你的 Alpine 版本对应（或落在"安装于"范围内）的那个包，下载后：

Pick the package that matches your Alpine release (or is listed under "Installs on"), then:

```sh
# 直接安装（未导入公钥）/ install directly (no trusted key imported)
apk add --allow-untrusted py3-pymupdf-1.16.18-r20261024.apk

# 校验校验和 / verify the checksum first
curl -LO https://github.com/dainan13/pymupdf-fitz-alpine/releases/download/r20261024/SHA256SUMS
sha256sum -c SHA256SUMS
```

```python
import fitz
print(fitz.VersionBind, fitz.VersionFitz)   # 1.16.18 1.16.1
```

依赖由 apk 自动解析为 `python3` + `mupdf`（后者带入 freetype / harfbuzz / openjpeg /
jbig2dec / libjpeg / zlib）。

Dependencies resolve automatically to `python3` + `mupdf` (which pulls freetype, harfbuzz,
openjpeg, jbig2dec, libjpeg and zlib).

## 发布模型 / Release model

发布 tag 是**日期戳**，不带版本号：`git tag r20261024 && git push origin r20261024`。它会构建
`matrix.json` 里的**全部**条目，跑完测试后放进**一个 Release**；`pkgrel` 直接取自 tag
（`r20261024` → `20261024`）。tag 不是 `r` + 8 位数字就什么都不做。

The release tag is a **date stamp**, not a version: `git tag r20261024 && git push origin
r20261024`. It builds **every** entry in `matrix.json`, tests each package, and publishes them
in **one** Release; `pkgrel` comes straight from the tag (`r20261024` → `20261024`). A tag that
is not `r` followed by eight digits triggers nothing.

```
tag rYYYYMMDD ──► contract   校验 tag → pkgrel，列出全部条目 / validate tag, list entries
                    │
                    ▼
                  build      matrix：每条目一个 job，在各自的 alpine:<X> 里 abuild
                    │        one job per entry, abuild inside its own alpine:<X>
                    ▼
                  test       每个包在 install[] 的 Alpine 里装 + smoke/feature 测试
                    │        each apk installed and tested on its install scope
                    ▼
                  publish    合并全部产物，一次 gh release / one Release with everything
```

- 全程只用该 Alpine 的 apk，**不编译 MuPDF 源码**；
  every dependency comes from that Alpine's apk; **MuPDF source is never compiled**.
- 老 Alpine 镜像不能作为 Actions 的 `container:`（runner 的 Node 需要更新的 musl），
  所以用 `docker run` 进入镜像；
  the old Alpine images cannot be used as a job `container:` (the runner's Node needs a newer
  musl), so the image is entered with `docker run`.
- 手动重跑：Actions → release → Run workflow，输入 tag；失败 run 上的 "Re-run jobs" 会重放
  旧 workflow，不要用；
  manual retry: Actions → release → Run workflow with the tag; don't use "Re-run jobs" on a
  failed run, it replays that commit's old workflow.

## 打包矩阵 / Packaging matrix

每个 Alpine 版本占一个独立的 PyMuPDF 版本号（同一条 MuPDF 线撞上 Python 升级时故意错开，
例如 3.13 用 1.18.0、3.14 用 1.18.1），所以一行对应一包，不会混淆。

Each Alpine release gets its own PyMuPDF version number (when two releases share a MuPDF line
but differ in Python, the versions are deliberately offset — 3.13 takes 1.18.0, 3.14 takes
1.18.1), so one row means exactly one package.

| Alpine | Python | MuPDF | PyMuPDF | 安装范围 Installs on |
| --- | --- | --- | --- | --- |
| 3.8 | 3.6 | 1.13.0 | 1.13.20 | 3.8, 3.9 |
| 3.11 | 3.8 | 1.16.1 | 1.16.18 | 3.11 |
| 3.13 | 3.8 | 1.18.0 | 1.18.0 | 3.13 |
| 3.14 | 3.9 | 1.18.0 | 1.18.1 | 3.14 |
| 3.15 | 3.9 | 1.19.0 | 1.19.6 | 3.15 |
| 3.16 | 3.10 | 1.19.1 | 1.19.5 | 3.16 |

**不支持的版本 / Not supported**：3.10（无 PyMuPDF 1.15 版本线）、3.12（1.17 在
`Page.firstAnnot` 上段错误）、3.17+（PyMuPDF ≥1.21 改为自带 MuPDF 源码构建，违反"依赖来自
apk"的约定）。原因与实测日志见 [docs/MANUAL.md](docs/MANUAL.md) §9。

3.10 (no PyMuPDF 1.15 line exists), 3.12 (1.17 segfaults on `Page.firstAnnot`) and 3.17+
(from 1.21 on, PyMuPDF builds its own MuPDF, which breaks the "dependencies come from apk"
rule) are out. Details and evidence logs are in [docs/MANUAL.md](docs/MANUAL.md) §9.

## 仓库结构 / Repository layout

```
matrix.json                 打包矩阵（唯一事实来源）/ the matrix, single source of truth
apkbuild/APKBUILD.in        APKBUILD 模板 / template rendered per entry
scripts/matrix.py           查矩阵、渲染 APKBUILD、生成文档与 CI 输出
scripts/build-apk.sh        在目标 Alpine 内构建 / build inside the target Alpine
scripts/run-tests.sh        装包并跑测试 / install and test
scripts/derive_matrix.py    推导新条目 / derive new entries in a chroot
tests/smoke.py              跨版本最小测试 / minimal cross-version test
tests/feature.py            跨版本功能测试 / adaptive feature test
docs/                       手册、矩阵、验证日志 / manual, matrix, evidence
.github/workflows/          release（r 日期 tag）、ci（push/PR）
```

## 文档 / Documentation

- [docs/MANUAL.md](docs/MANUAL.md) — 约定、流水线、签名、新增版本、故障排查（中文）
  conventions, pipeline, signing, adding a version, troubleshooting
- [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) — 兼容矩阵与证据 / matrix and evidence

构建差异（`mupdfthird` / `mupdf-third` / 已合并三种库名、`--no-as-needed` 额外链接库、
`-I/usr/include/freetype2`、MuPDF 未编 JS 时的 `jm_valid_chars` stub）全部由 `APKBUILD.in`
自动处理，**不需要手工打补丁**。

Build quirks (library naming across MuPDF versions, extra link libraries, the freetype include
path, the `jm_valid_chars` stub for MuPDF built without JavaScript) are handled by the
template — **no manual patches**.

## 签名 / Signing

配置 `secrets.ABUILD_PRIVKEY` + `secrets.ABUILD_PUBKEY`（base64）让所有包用同一把钥匙签名；
不配置则每个构建 job 生成一次性密钥（就像 r20261024 这样）。公钥随 Release 发布，放进
`/etc/apk/keys/` 后即可免 `--allow-untrusted`。

Configure `secrets.ABUILD_PRIVKEY` + `secrets.ABUILD_PUBKEY` (base64) to sign every package
with one stable key; without them each build job generates a throw-away key (as in r20261024).
The public key ships with the release — drop it into `/etc/apk/keys/` to install without
`--allow-untrusted`.

## 许可 / License

打包脚本与 CI 配置可自由使用。生成的包内含 PyMuPDF（**AGPL-3.0**）并动态链接 Alpine 的
MuPDF，分发时请遵守 AGPL-3.0。

The packaging scripts and CI config are free to use. The resulting packages contain PyMuPDF
(**AGPL-3.0**) and link Alpine's MuPDF dynamically — redistribute under AGPL-3.0.
