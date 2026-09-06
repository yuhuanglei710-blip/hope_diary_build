# 日记完整复刻器（Diary Replica）

Windows 图形化日记导出工具。程序按界面中填写的参数请求日记接口，自动获取全部分页，保存原始数据和图片，并生成包含正文、图片与评论的 PDF。

## 一键部署（Windows）

下载本仓库的 ZIP 并解压，右键在项目目录中打开 PowerShell，然后运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本会自动完成以下操作：

1. 检查带完整 Tkinter 的官方 Python 3.12；未安装时尝试通过 `winget` 自动安装。
2. 在项目目录创建 `.venv` 隔离环境。
3. 安装全部依赖。
4. 启动日记复刻器。

## 双击生成 EXE

直接双击项目目录中的：

```text
build-exe.cmd
```

它会自动检查或安装 Python、创建隔离环境、安装依赖并调用 PyInstaller。完成后窗口不会立即关闭，生成结果位于：

```text
dist\DiaryReplica.exe
```

第一次构建需要下载 Python 依赖，因此耗时会比后续构建长。

构建固定使用官方 Python 3.12，并检查 Tkinter/Tcl/Tk 运行库，防止生成缺少图形界面的无效 EXE。旧版脚本生成的 `.venv` 如果不是 Python 3.12，会被自动替换。如果检查失败，请重新安装官方 Python，并确保安装器中的 `tcl/tk and IDLE` 功能已启用。

如果不希望部署完成后自动启动：

```powershell
.\setup.ps1 -NoLaunch
```

如果还要生成独立的 Windows EXE：

```powershell
.\setup.ps1 -BuildExe -NoLaunch
```

生成文件位于 `dist\DiaryReplica.exe`。

## 使用 Git 下载

```powershell
git clone https://github.com/yuhuanglei710-blip/hope_diary_build.git
Set-Location hope_diary_build
PowerShell -ExecutionPolicy Bypass -File .\setup.ps1
```

## 手动运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\diary_query_gui.py
```

## 导出内容

每次任务会在所选目录中创建独立文件夹，包含：

- `response.json`：接口的完整原始响应。
- `responses\`：接口每一页未经合并的原始响应，方便核对和排查。
- `query.json`：本次查询参数。
- `diaries\`：逐篇日记 JSON。
- `images\`：下载的日记图片。
- `日记完整复刻_YYYYMMDD_HHMMSS.pdf`：最终 PDF。

日记、Cookie 和 Authorization 等内容可能涉及隐私。导出目录已被 `.gitignore` 排除，请勿将个人数据提交到公共仓库。

如果程序提示“请求成功，但没有日记”，说明网络和接口均已正常工作，但填写的用户 ID、日期范围或日记类型没有匹配数据。请确认填写的是**用户 ID**，而不是某一篇日记的 ID。默认从第 1 页开始，并会自动继续获取后续全部页。

## 主要文件

- `diary_query_gui.py`：主程序。
- `setup.ps1`：一键部署、启动和构建脚本。
- `build-exe.cmd`：可直接双击的一键 EXE 构建入口。
- `build_exe.ps1`：仅构建 EXE 的简化脚本。
- `DiaryReplica.spec`：PyInstaller 配置。
- `DiaryReplica.iss`：Inno Setup 安装包配置。
