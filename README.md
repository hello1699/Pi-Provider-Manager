# Pi Provider Manager

一个使用 **Python + tkinter/ttk** 编写的轻量桌面工具，用于可视化管理 Pi Coding Agent 的 `~/.pi/agent/models.json`。无需手动编辑 JSON，即可维护 Provider、模型、备份和配置方案。

## 功能

- Provider 新增、编辑、删除：`baseUrl`、`api`、API Key、`headers`、`compat`
- API Key 默认掩码，并可在详情/编辑框中显示或隐藏
- 每个 Provider 下的模型新增、编辑、删除：ID、上下文窗口、最大 Token、Reasoning、text/image 输入和可选 Cost
- 从当前 Provider 获取远程模型列表，支持多选；逐个填写 Pi 模型参数后添加
- 每次配置变更自动写入 `~/.pi/agent/models.json`，并在 SQLite 中备份此前文件内容
- 保存、切换和删除配置方案（Profile）
- JSON 配置导入与导出
- Provider 健康检查：后台请求 `{baseUrl}/v1/models`，超时 10 秒，不阻塞界面
- 可视化列出并恢复历史备份

## 目录与数据

| 内容 | 路径 |
| --- | --- |
| Pi 配置 | `~/.pi/agent/models.json` |
| 应用数据库 | `~/.pi-provider-manager/ppm.db` |
| Python 虚拟环境 | 项目目录下 `.venv/` |

首次运行时，如 `~/.pi/agent/models.json` 不存在，程序会自动建立包含 `{"providers": {}}` 的空配置。

## 安装与运行

要求：Python 3.8+，以及系统 Python 已包含 tkinter（多数 Windows 官方 Python 安装包默认提供）。

### Git Bash（当前项目环境）

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### CMD

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

> 若 PowerShell 阻止激活脚本，可仅对当前终端执行：`Set-ExecutionPolicy -Scope Process Bypass`，然后再激活。

## Pi 配置格式

新增 Provider 的 `api` 默认值为 `openai-completions`，可在界面中修改。程序保留已有配置中未由表单管理的字段。示例：

```json
{
  "providers": {
    "my-provider": {
      "baseUrl": "https://example.com/v1",
      "api": "openai-completions",
      "apiKey": "sk-******",
      "headers": {
        "User-Agent": "claude-cli/2.1.217"
      },
      "compat": {
        "sendSessionAffinityHeaders": true
      },
      "models": [
        {
          "id": "my-model",
          "reasoning": true,
          "input": ["text", "image"],
          "contextWindow": 128000,
          "maxTokens": 8192,
          "thinkingLevelMap": {
            "minimal": null,
            "low": null,
            "medium": null,
            "high": "high",
            "max": "max"
          }
        }
      ]
    }
  }
}
```

对于 Cost：四个字段 `input`、`output`、`cacheRead`、`cacheWrite` 要么全部留空（不写入配置），要么全部填写非负数字（支持小数）。

`thinkingLevelMap` 用于将 Pi 的 `minimal`、`low`、`medium`、`high`、`max` 五种思考强度映射为 Provider 支持的字符串。在模型窗口中五项均可选：未填写时会保存为 `null`，填写时会保存为对应字符串。

## 获取模型列表

在模型操作栏选择 **获取模型列表**，程序会在后台以当前 Provider 的鉴权信息请求 `GET {baseUrl}/v1/models`（Base URL 已以 `/v1` 结尾时不会重复追加），超时为 10 秒。接口需返回 OpenAI 兼容结构：

```json
{
  "data": [{"id": "model-a"}, {"id": "model-b"}]
}
```

列表支持多选，已在本地配置的模型会标记为“已存在”，不能重复添加。大多数接口只返回模型 ID，不包含 Pi 所需的 Context Window、Max Tokens、Reasoning 与 Input 能力，因此确认选择后会为每个模型依次打开参数表单；取消任意一个表单会停止余下模型的添加，已经保存的模型不会回滚。

## 测试

激活虚拟环境后运行：

```bash
python -m unittest discover -s tests -v
```

测试使用临时目录与临时 SQLite 文件，不会读写真实的 Pi 配置。

## 可选：PyInstaller 打包

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name PiProviderManager main.py
```

输出的可执行文件位于 `dist/`。程序所有路径均使用 `os.path.expanduser`，在打包运行时仍会使用当前用户目录下的 Pi 配置和数据库。
