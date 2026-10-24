# 手册

本仓库把"用某个 Alpine 版本自带的 Python 与 MuPDF，把指定版本的 PyMuPDF 编译成
apk"这件事固定成一套可审计的约定，并用 GitHub Actions 实现"打 tag 即发布"。

- 机器可读的约定：[`matrix.json`](../matrix.json)
- 人读的矩阵：[COMPATIBILITY.md](COMPATIBILITY.md)（由 `scripts/matrix.py markdown` 生成，CI 会校验）

---

## 1. 约定

### 1.1 一个 tag 对应一个编译环境

**git tag 是唯一入口**。tag 里只写 PyMuPDF 版本（`v1.13.20`），它编译在哪个 Alpine
上由 `matrix.json` 决定，不由 tag 本身推断：

```json
{ "tag": "v1.13.20", "pymupdf": "1.13.20",
  "build": { "alpine": "3.8", "python": "3.6", "mupdf": "1.13.0-r0" },
  "install": ["3.8", "3.9"] }
```

因此：

| 你做 | 结果 |
| --- | --- |
| `git tag v1.13.20 && git push origin v1.13.20` | 在 `alpine:3.8` 容器里编译，跑测试，发布 `1.13.20-r<UTC 日期>` |
| 打 `v1.16.0` 但 `matrix.json` 里没有 | `contract` job 直接失败，**不构建、不发布**，summary 里给出提示 |
| 打 `v1.13.20.1` 之类的衍生 tag | 同上（未约定 = 不发布） |

"不发布"是硬 gate：`contract` job 失败后 `build` / `test` / `publish` 都不会运行。

### 1.2 产物命名

```
py3-pymupdf-<pkgver>-r<pkgrel>.apk      pkgrel = 构建当天 UTC 日期 YYYYMMDD
例：py3-pymupdf-1.13.20-r20261022.apk
```

- `pkgver` 永远等于 PyMuPDF 版本号；
- `pkgrel` 用日期而不是递增序号：同一天重跑会得到相同的 apk 版本号，Release 资产
  以 `--clobber` 覆盖（内容里 `builddate` 会变，但功能一致）；
- 该 apk 的 `depends` 由 abuild 自动推导为 `python3` + `mupdf` + 具体 so 依赖。

### 1.3 可安装范围（install scope）

`install` 字段回答"这个 apk 能装到哪些 Alpine 上"。判定依据只有两条硬约束：

1. **CPython ABI 一致**：扩展文件名里的 ABI 标签（如 `cpython-36m`）与
   `/usr/lib/python3.X/site-packages` 路径都要对得上；
2. **MuPDF C ABI 一致**：PyMuPDF 必须与 `libmupdf` 的上游版本线匹配
   （1.13 ↔ 1.13、1.16 ↔ 1.16……）。

⚠️ 不能用 `apk` 的 `so:libmupdf.so.0` 依赖判断兼容性：Alpine 3.8–3.17 的 muPDF
都声明同一个 soname，而 ABI 早就变了。真正会拦住错误安装的往往只是
`so:libpython3.6m.so.1.0` 这类 Python 侧依赖。

`install` 里的每一项都必须有实测证据（见第 5 节），不接受"应该能行"。

### 1.4 一个 Alpine 版本一个独立 tag（版本号错开）

Alpine 会在同一个 muPDF 版本线上换 Python（3.13 和 3.14 都是 muPDF 1.18，但
Python 3.8 → 3.9），同一个 PyMuPDF 版本因此必须编两次。约定**不用环境后缀**，
而是把版本号故意错开：每个受支持的 Alpine 拥有一个**互不重复**的 PyMuPDF 版本号，
于是 tag、Release、产物文件名、手册表格天然一一对应。

```
Alpine 3.13 (muPDF 1.18, Python 3.8) -> v1.18.0
Alpine 3.14 (muPDF 1.18, Python 3.9) -> v1.18.1
```

- 同一条版本线里相邻维护版差异极小，选哪个只看"号还没被占走"，**优先用存在的版本**；
- 万一某条线没有空闲维护版（极少见），可以退到上一版本线的末尾，或用字母后缀
  （`v1.18.0a`）——规则只有一条：**一个 tag 只能对应一个编译环境**，
  `matrix.json` 的 tag 唯一性天然保证这点；
- 这样做的好处：README / 表格里一眼就能看出"这个 Alpine 对应这个版本"，不用查后缀。

---

## 2. `matrix.json` 字段

| 字段 | 含义 |
| --- | --- |
| `releases[].tag` | 允许发布、且已约定的 git tag |
| `releases[].pymupdf` | PyMuPDF 版本（= `pkgver`） |
| `releases[].mupdf_line` | 对应的 MuPDF 版本线，写进 `pkgdesc` |
| `build.alpine` | 编译所用的 Alpine 版本（CI 直接用它做 container 镜像 tag） |
| `build.python` / `build.mupdf` | 该 Alpine 上的 Python / muPDF 版本，用于审计 |
| `build.abi_tag` / `build.site_packages` | Python 侧结论，写进文档和 Release notes |
| `install[]` | 允许安装的 Alpine 版本列表（逐项实测） |
| `verified{}` | 已验证的内容与证据文件路径 |
| `pending[]` | 还没进入约定的候选（推导中），CI 不读它 |

新增/修改约定必须单独提 PR，改完跑：

```sh
python3 scripts/matrix.py markdown        # 更新 docs/COMPATIBILITY.md 里的表格
```

CI 的 `lint` 任务会检查文档与 `matrix.json` 是否一致。

---

## 3. 发布流水线（`.github/workflows/release.yml`）

```
push tag v*  ──►  contract   解析 tag；不在 matrix.json 就失败退出
                   │
                   ▼
                 build      在 alpine:<build.alpine> 容器里跑 scripts/build-apk.sh
                   │        （装 apk 依赖 → 渲染 APKBUILD → abuild → 产物 + SHA256）
                   ▼
                 test       对 install[] 里每个 Alpine 起容器，装 apk 跑测试
                   │
                   ▼
                 publish    sha256、Release notes、gh release upload
```

- 构建全程只用该 Alpine 的 apk：`python3-dev`、`mupdf-dev` 等；**不编译 MuPDF 源码**。
- 源码只下载 PyMuPDF sdist（`files.pythonhosted.org`，可用 `PYMUPDF_MIRROR` 覆盖）。
- 每个 job 的关键输出都写进 GitHub Step Summary。

### 签名

| Secret / Var | 用途 |
| --- | --- |
| `secrets.ABUILD_PRIVKEY` | base64 的 RSA 私钥（`base64 -w0 builder.rsa`） |
| `secrets.ABUILD_PUBKEY` | base64 的对应公钥（`.rsa.pub`） |
| `vars.ABUILD_PACKAGER` | 写进包元数据的 `PACKAGER` 字符串 |

- 配了就用固定密钥签名，公钥随 Release 一起发布，用户把它放进 `/etc/apk/keys/`
  即可免 `--allow-untrusted`；
- 没配则每次构建生成一次性密钥（apk 仍带签名，只是公钥每次都不同）。

生成密钥：

```sh
docker run --rm -it -v "$PWD:/w" alpine:3.8 sh -c '
  apk add --no-cache abuild openssh-keygen >/dev/null
  adduser -D builder && addgroup builder abuild
  su builder -c "abuild-keygen -a -n"
  cp /home/builder/.abuild/*.pub /w/'
base64 -w0 /home/builder/.abuild/builder-*.rsa      # -> ABUILD_PRIVKEY
base64 -w0 /home/builder/.abuild/builder-*.rsa.pub  # -> ABUILD_PUBKEY
```

---

## 4. 目录结构

```
matrix.json                 发布约定（唯一事实来源）
apkbuild/APKBUILD.in        APKBUILD 模板（占位符由 scripts/matrix.py 渲染）
scripts/
  matrix.py                 解析约定、渲染 APKBUILD、生成文档表格 / GHA 输出
  build-apk.sh              在目标 Alpine 内构建 apk（CI 与本地共用）
  run-tests.sh              在目标 Alpine 内安装 apk 并跑测试
  derive_matrix.py          推导新条目（chroot 里"编译 @N，验证 @N+1"）
tests/
  smoke.py                  跨版本最小测试（1.13 … 1.19 通用）
  feature.py                跨版本功能测试（API 缺失则 SKIP）
docs/
  MANUAL.md                 本手册
  COMPATIBILITY.md          兼容矩阵（生成）
  evidence/                 验证日志
.github/workflows/
  release.yml               tag 触发的编译 + 测试 + 发布
  ci.yml                    PR 校验：lint、构建、多版本安装测试
artifacts/                  构建输出（.gitignore）
```

---

## 5. 新增一个版本（推导流程）

目标：为更高的 Alpine 版本找到"能编译、能跑"的 PyMuPDF 版本线，并把结论写进约定。

### 5.1 步骤

1. 查依赖事实（哪个 Alpine 用哪个 muPDF / Python）：

   ```sh
   python3 scripts/matrix.py markdown      # 见 COMPATIBILITY.md 的对照表
   ```

2. 选候选 PyMuPDF：MuPDF 版本线 N.x 对应 PyMuPDF N.x 的最新维护版。
   注意 MuPDF 1.15（Alpine 3.10）**没有**对应的 PyMuPDF 1.15 版本线，只能拿
   1.16.x 去试。

3. 用推导工具跑"编译 @N → 验证 @N"以及"验证 @N+1"：

   ```sh
   sudo python3 scripts/derive_matrix.py 3.10:1.16.0 --check 3.10 3.11
   ```

   它会：
   - 拉 `alpine-minirootfs-3.10.x` 建 chroot（`.cache/rootfs/3.10`）；
   - 在 chroot 里跑 `build-apk.sh`（推导模式，`pkgrel=0`，不进约定）；
   - 把产物装进 3.10 / 3.11 的 chroot 跑 `tests/smoke.py` + `tests/feature.py`；
   - 在 `.cache/derive/` 留下 JSON 记录。

4. 判定（就是约定的推导规则）：

   | 结果 | 结论 |
   | --- | --- |
   | @N 编译失败 | 换候选版本（上一个/下一个 PyMuPDF 维护版） |
   | @N 编译成功、@N 测试通过、@N+1 测试也通过 | @N+1 并入同一 `install` 列表 |
   | @N 通过、@N+1 失败 | @N+1 需要自己的编译环境 → 从 @N+1 开始找下一个 PyMuPDF 版本 |

5. 把结论写进 `matrix.json`（`releases` 或 `pending`），更新文档，提 PR。

### 5.2 验收标准

一个条目只有同时满足下面条件才能进 `releases`：

- `build-apk.sh` 在该 Alpine 上无错误；
- `check()` 通过（PyMuPDF 自报的 `VersionFitz` 与期望 MuPDF 线一致）；
- `install[]` 里每个 Alpine 上 `tests/smoke.py` 和 `tests/feature.py` 都返回 0；
- 证据日志放进 `docs/evidence/` 并在 `verified.evidence` 里引用。

---

## 6. 本地构建

### 6.1 在任意 Alpine 机器/容器里（推荐）

```sh
# docker
docker run --rm -it -v "$PWD:/w" -w /w alpine:3.8 sh -c '
  apk add --no-cache git && TAG=v1.13.20 sh scripts/build-apk.sh'
# 产物在 ./artifacts/
```

### 6.2 在 alpine3.8builder 这类常备构建机上

```sh
git clone <repo> && cd <repo>
TAG=v1.13.20 sh scripts/build-apk.sh
```

脚本会自己装依赖、建 `builder` 用户、下载源码、跑 `abuild`。想看细节加
`sh -x`，或看 `/home/builder/aports/testing/py3-pymupdf/`。

### 6.3 只验证、不发布

```sh
TAG=v1.13.20 PKGREL=0 sh scripts/build-apk.sh
APK=artifacts/py3-pymupdf-1.13.20-r0.apk sh scripts/run-tests.sh   # 在目标 Alpine 内
```

`PKGREL=0` 让产物版本与正式发布区分开，避免误传。

---

## 7. 故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| `tag ... is not in matrix.json` | 预期行为。先把条目写进 `matrix.json`，再打 tag |
| `must be built on Alpine 3.8, this is 3.10` | 用错镜像；CI 由 `build.alpine` 决定，本地请换容器 |
| `Do not run abuild as root` | abuild 必须用非 root 用户跑；脚本已建 `builder` 用户，别再手工 `abuild -F` |
| `fakeroot: nested operation not yet supported` | 不要把 abuild 套在 `fakeroot` 外层 |
| `sha512sum: ... Permission denied` | distfile 权限不对（`chmod 644`，属主 builder 可读） |
| `error: command 'swig' failed` | PyMuPDF 1.21 起 sdist 不再带预生成 wrapper，需要 `swig`（模板 makedepends 已含） |
| `fitz_wrap.c: fatal error: ft2build.h: No such file or directory` | PyMuPDF 1.18.x 直接 `#include <ft2build.h>`，需要 `-I/usr/include/freetype2`；模板里已设 `CPPFLAGS` |
| `ImportError: Error relocating /usr/lib/libmupdf.so.0: hb_buffer_add_utf8 / FT_Select_Charmap ...` | Alpine 的 `libmupdf.so` 把 freetype/harfbuzz/jpeg/openjpeg/jbig2dec/zlib 的符号留给加载方。从 MuPDF 1.16 起必须在链接扩展时显式带上这些库：`matrix.json` 的 `build.extra_link_libs` 会渲染成 `-Wl,--no-as-needed -l...`（1.13.20/3.8 不需要，保持为空） |
| `-lmupdf-third: not found` | PyMuPDF ≥1.16 的库名带连字符，Alpine 是 `libmupdfthird.so`；模板里的 `build()` 已自动改写 |
| `so:libpython3.6m.so.1.0 (no such package)` | 装到 Python 版本不匹配的 Alpine 上了；查 `install` 范围 |
| `apk update` 极慢 | 该机器到 `dl-cdn` 慢。CI 无需处理；本机可切 `mirrors.aliyun.com` |
| `docs/COMPATIBILITY.md is stale` | 跑了 `matrix.py markdown` 但没更新文档 |
| `add_subparsers() got an unexpected keyword argument 'required'` | Python 3.6 不支持；本仓库脚本已避免 3.7+ 语法，改动时注意 |

---

## 8. 已知限制

- **只支持 x86_64**：`arch="x86_64"`。要 `aarch64`/`armv7` 需要新的矩阵维度
  （届时建议 tag 里带架构，例如 `v1.13.20-aarch64`）。
- **不打包 MuPDF**，完全依赖 `apk add mupdf`；MuPDF 的安全更新由 Alpine 负责，
  但也意味着 Alpine 一旦升级 muPDF 主版本，对应条目就必须重编。
- **PyMuPDF 1.13 的 API 与新版差异较大**（`getImageList`/`getToC`/`write()`、
  shape 字体名要写 `Helvetica` 不能写 `helv`、`firstAnnot` 可能 parent 未绑定）。
  `tests/feature.py` 已做适配，业务代码迁移时注意。
- **同一天重复发布同一个 tag** 会覆盖 Release 资产（apk 版本号相同，`builddate` 不同）。

---

## 9. 推导记录（Alpine 3.10 起）

已实测的事实，供后续补条目时参考：

| Alpine | muPDF | Python | 结论 |
| --- | --- | --- | --- |
| 3.10 | 1.15.0 | 3.7 | **不可支持**：PyMuPDF 1.16.0 用 MuPDF 1.15 头文件编译失败（`pdf_write_options` 字段、`fz_convert_pixmap`、`fz_stext_char` 等都变了），而 PyMuPDF 没有 1.15 版本线 |
| 3.11 | 1.16.1 | 3.8 | PyMuPDF 1.16.18 可编译、可 `import`（需 `extra_link_libs`） |
| 3.12 | 1.17.0 | 3.8 | **暂不支持**：1.17.7 用的是 MuPDF 1.18 的 redact API（`black_boxes`/`PDF_REDACT_IMAGE_REMOVE`）→ 编译失败；1.17.0 能编译、smoke 通过，但 `Page.firstAnnot` 直接段错误（上游 1.17 bug） |
| 3.13 | 1.18.0 | 3.8 | 1.18.0 可编译；**需要给 `jm_valid_chars` 补 no-op stub**（Alpine 的 MuPDF 未编 JavaScript）后 smoke + feature 全过 → 已纳入约定 |
| 3.14 | 1.18.0 | 3.9 | 同一个 MuPDF、Python 升到 3.9 → `v1.18.1`；smoke + feature 全过（需 `-I/usr/include/freetype2`） |
| 3.15 | 1.19.0 | 3.9 | `v1.19.6`：smoke + feature 全过（需 setuptools + g++；MuPDF 1.19 已无 third-party 库，模板会自动从 setup.py 里删掉） |
| 3.16 | 1.19.1 | 3.10 | `v1.19.5`：同上，Python 3.10 单独编 |
| 3.17 | 1.21.0 | 3.10 | **超出范围**：PyMuPDF 1.21 的 setup.py 改为内置构建 MuPDF（`PYMUPDF_SETUP_MUPDF_BUILD`/`_TGZ`），用不了 apk 的 mupdf；且 Alpine 没有 MuPDF 1.20，PyMuPDF 1.20.x 也配不上 |

**项目的天然上界是 Alpine 3.16（PyMuPDF 1.19.x）**：1.21 起上游改成自带 MuPDF 源码构建，
与本项目"依赖全部来自 apk"的约定冲突。

由此得到的选版规则：**MuPDF 的次版本号就是 PyMuPDF 的次版本号**，且取该线里
"最早能用"的那个维护版（远端维护版可能已经悄悄跟到了下一个 MuPDF）。

由于每个 Alpine 只能占一个 tag，同一 muPDF 线撞上 Python 升级时按 §1.4 把版本号错开
（3.13 → `v1.18.0`，3.14 → `v1.18.1`）。

---

## 10. 首次发布 checklist

仓库本身不需要初始化：`matrix.json` + `.github/workflows/` 就是全部。提交后按顺序做：

1. **推代码**

   ```sh
   git init && git add -A && git commit -m "py3-pymupdf: Alpine 3.8-3.16 apk builder"
   git remote add origin git@github.com:<you>/<repo>.git
   git push -u origin main
   ```

   `artifacts/` 和 `.cache/` 已在 `.gitignore` 里，不会被提交；仓库只有源码、模板、脚本、文档和验证日志。

2. **（推荐）配置签名密钥**，这样每个 Release 的公钥都一致：

   ```sh
   base64 -w0 builder.rsa      # -> secrets.ABUILD_PRIVKEY
   base64 -w0 builder.rsa.pub  # -> secrets.ABUILD_PUBKEY
   ```

   不配也能发：`build-apk.sh` 会生成一次性密钥，公钥随 Release 一起上传。

3. **打 tag 触发发布**

   ```sh
   git tag v1.16.18
   git push origin v1.16.18
   ```

   四个 job 依次是 `contract`（查 `matrix.json`）→ `build`（`alpine:3.11` 容器内 abuild）
   → `test`（在 `install[]` 的每个 Alpine 里装包并跑测试）→ `publish`（`gh release`）。

4. **验收**：Release 页面应有 `py3-pymupdf-1.16.18-r<日期>.apk`、`SHA256SUMS`、
   `.rsa.pub`、`APKBUILD-1.16.18-r<日期>`。

### 关于"要不要打补丁"

**不需要手工 patch。** 版本差异全部由 `APKBUILD.in` 在构建时自动处理：

- 库名 `mupdfthird` / `mupdf-third` / 已合并（1.19+）三种情况自动选择；
- MuPDF ≥ 1.16 需要的 `-Wl,--no-as-needed -l...` 由 `build.extra_link_libs` 渲染；
- 1.18.x 的 `-I/usr/include/freetype2`、1.19+ 的 setuptools/g++、1.18+ 缺 JS 的
  `jm_valid_chars` stub 都在模板里。

所以一个 tag 就是一次完整发布，通常每个版本只发一次；只有改了 `APKBUILD.in`/脚本、
或换 PyMuPDF 版本才需要新 tag。注意 `pkgrel` 是日期，**同一天重发同一个 tag 会覆盖
Release 资产**（内容里的 builddate 会变）。
