# 日记完整复刻器（Diary Replica）

Windows 图形化日记导出工具。程序按界面中填写的参数请求日记接口，保存原始数据和图片，并生成包含正文、图片与评论的 PDF。

## 一键部署（Windows）

下载本仓库的 ZIP 并解压，右键在项目目录中打开 PowerShell，然后运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本会自动完成以下操作：

1. 检查 Python 3.10 或更高版本；未安装时尝试通过 `winget` 安装 Python 3.12。
2. 在项目目录创建 `.venv` 隔离环境。
3. 安装全部依赖。
4. 启动日记复刻器。

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
- `query.json`：本次查询参数。
- `diaries\`：逐篇日记 JSON。
- `images\`：下载的日记图片。
- `日记完整复刻_YYYYMMDD_HHMMSS.pdf`：最终 PDF。

日记、Cookie 和 Authorization 等内容可能涉及隐私。导出目录已被 `.gitignore` 排除，请勿将个人数据提交到公共仓库。

## 主要文件

- `diary_query_gui.py`：主程序。
- `setup.ps1`：一键部署、启动和构建脚本。
- `build_exe.ps1`：仅构建 EXE 的简化脚本。
- `DiaryReplica.spec`：PyInstaller 配置。
- `DiaryReplica.iss`：Inno Setup 安装包配置。
