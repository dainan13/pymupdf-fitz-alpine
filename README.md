# py3-pymupdf · Alpine apk builder

用 **Alpine 发行版自带的 Python 与 MuPDF**（`apk add mupdf mupdf-dev python3-dev`）编译
[PyMuPDF](https://github.com/pymupdf/PyMuPDF)，打包成可直接安装的 Alpine `.apk`，并通过
GitHub Actions **打 tag 即发布**。

- 不编译 MuPDF 源码，只链接 `libmupdf.so` / `libmupdfthird.so`；
- 每个 tag 绑定一个明确的编译环境，产物版本号 = `PyMuPDF 版本 - r<UTC 日期>`；
- 不在约定表里的 tag **不会**触发发布（硬 gate）。

> "apk" 指 Alpine Linux 软件包，不是 Android 安装包。

## 当前约定

| tag | PyMuPDF | 编译环境 | 可安装 Alpine |
| --- | --- | --- | --- |
| `v1.13.20` | 1.13.20 | Alpine 3.8 / Python 3.6 / MuPDF 1.13.0 | 3.8, 3.9 |
| `v1.16.18` | 1.16.18 | Alpine 3.11 / Python 3.8 / MuPDF 1.16.1 | 3.11 |
| `v1.18.0` | 1.18.0 | Alpine 3.13 / Python 3.8 / MuPDF 1.18.0 | 3.13 |
| `v1.18.1` | 1.18.1 | Alpine 3.14 / Python 3.9 / MuPDF 1.18.0 | 3.14 |
| `v1.19.6` | 1.19.6 | Alpine 3.15 / Python 3.9 / MuPDF 1.19.0 | 3.15 |
| `v1.19.5` | 1.19.5 | Alpine 3.16 / Python 3.10 / MuPDF 1.19.1 | 3.16 |

版本号**故意错开**：每个 Alpine 只占一个 tag，同一条 MuPDF 线撞上 Python 升级时就用下一个
维护版（例如 3.13 用 `v1.18.0`、3.14 用 `v1.18.1`），这样 tag、Release、产物和表格一一对应。

覆盖到此为止是**结构性边界**：PyMuPDF 1.21 起 setup.py 改为自带 MuPDF 源码构建
（`PYMUPDF_SETUP_MUPDF_BUILD`），无法满足"依赖全部来自 apk"这条核心约定；而 Alpine 从未
发布过 MuPDF 1.20，也没有 PyMuPDF 1.20.x 能对应的发行版。所以 3.17+ 不在本项目范围内。

推导状态：3.8/3.9、3.11、3.13、3.14、3.15、3.16 均已通过编译 + 测试；**3.10 与 3.12 暂不支持**——3.10 没有对应的 PyMuPDF 版本线（1.16 用 MuPDF 1.15
头文件编译失败）；3.12 的 1.17.7 编译失败、1.17.0 在 `Page.firstAnnot` 上段错误（上游 bug）。
3.13 需给 `jm_valid_chars` 补 no-op stub（Alpine 的 MuPDF 未编 JS），模板已自动处理。
细节见 [docs/MANUAL.md](docs/MANUAL.md#9-推导记录alpine-310-起)。

完整矩阵（含各 Alpine 的 muPDF/Python 事实表、推导状态）见
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)；约定细则与运维手册见
[docs/MANUAL.md](docs/MANUAL.md)。

已有产物：

- `py3-pymupdf-1.13.20-r20261022.apk`（Alpine 3.8 构建，3.8/3.9 可装）
  sha256 `5fe27de9c29faf74863291e9aece8cac04dfad1a4b9fb626e8871799fd1d8f5a`
- `py3-pymupdf-1.19.6-r0.apk`（Alpine 3.15 构建，3.15 可装）
  sha256 `5ed98cfce56c22d36f51597dbd64dc67b1f4a9bb785023c9658c91aebbc6c5e6`
- `py3-pymupdf-1.19.5-r0.apk`（Alpine 3.16 构建，3.16 可装）
  sha256 `54777f8edc8ff3f94b1960dde4911f1fb78de047664593e386662ba244b7a551`

## 安装

```sh
# 直接装（未导入公钥时）
apk add --allow-untrusted py3-pymupdf-1.13.20-r20261022.apk

# 或者先信任签名公钥，再从本地仓库装
cp builder-6ad9934e.rsa.pub /etc/apk/keys/
mkdir -p /opt/repo/testing/x86_64
cp py3-pymupdf-1.13.20-r20261022.apk APKINDEX.tar.gz /opt/repo/testing/x86_64/
apk add --repository /opt/repo/testing py3-pymupdf
```

```python
import fitz
print(fitz.VersionBind, fitz.VersionFitz)   # 1.13.20 1.13.0
```

依赖自动解析为 `python3` + `mupdf`（由 `mupdf` 带入 freetype/harfbuzz/openjpeg/
jbig2dec/libjpeg/zlib）。

## 发布约定（摘要）

```
git tag v1.13.20 && git push origin v1.13.20
   └─► contract job  查 matrix.json，命中才继续
       └─► build     在 alpine:3.8 容器内 abuild
           └─► test  在 3.8、3.9 容器内安装并跑测试
               └─► publish  1.13.20-r20261022 + SHA256SUMS + 公钥
```

- `pkgrel` = 构建当天 UTC 日期（`YYYYMMDD`），所以同一天重复发布是同一版本号；
- 未约定的 tag → `contract` job 失败，**不构建、不发布**；
- 可安装范围逐项实测，不看 `so:` 依赖（Alpine 3.8–3.17 的 muPDF 都叫 `libmupdf.so.0`，
  ABI 却早已不同）。

详见 [docs/MANUAL.md](docs/MANUAL.md)。

## 目录

```
matrix.json                 发布约定（唯一事实来源）
apkbuild/APKBUILD.in        APKBUILD 模板
scripts/matrix.py           查约定 / 渲染 APKBUILD / 生成文档与 CI 输出
scripts/build-apk.sh        在目标 Alpine 内构建（CI 与本地共用）
scripts/run-tests.sh        在目标 Alpine 内安装并测试
scripts/derive_matrix.py    推导新版本（chroot：编译 @N，验证 @N+1）
tests/smoke.py              跨版本最小测试
tests/feature.py            跨版本功能测试（API 缺失则 SKIP）
docs/                       手册、兼容矩阵、验证日志
.github/workflows/          release（tag 触发）、ci（PR 校验）
```

## 本地构建

```sh
docker run --rm -it -v "$PWD:/w" -w /w alpine:3.8 sh -c '
  apk add --no-cache git && TAG=v1.13.20 sh scripts/build-apk.sh'
# 产物：artifacts/py3-pymupdf-1.13.20-r<日期>.apk
```

只验证不发布：加 `PKGREL=0`，产物版本变成 `-r0`。

## 签名

仓库用 `secrets.ABUILD_PRIVKEY` / `secrets.ABUILD_PUBKEY`（base64）做固定密钥签名；
未配置时每次构建生成一次性密钥。公钥随 Release 发布，放进 `/etc/apk/keys/` 即可免
`--allow-untrusted`。

## 许可

打包脚本与 CI 配置可自由使用。生成的包内含 PyMuPDF（**AGPL-3.0**），并动态链接
Alpine 的 MuPDF；发布与再分发请自行遵守 AGPL-3.0。
