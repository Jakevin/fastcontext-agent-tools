# FastContext MCP 使用說明（繁體中文）

這個專案把 Microsoft FastContext 包成 MCP stdio server，讓 LLM coding agent 可以用 read-only 的方式探索 repo，取得相關檔案與行號，再由主 agent 自己讀檔與修改。

## 前置需求

- Python 3.10+：執行本 MCP wrapper。
- Python 3.12+：執行上游 FastContext CLI。
- 已安裝 Microsoft FastContext CLI：<https://github.com/microsoft/fastcontext>
- 已啟動 OpenAI-compatible FastContext model endpoint。

上游 CLI 安裝範例：

```bash
git clone https://github.com/microsoft/fastcontext
cd fastcontext
uv tool install .
```

## 安裝本 MCP Server

```bash
git clone https://github.com/Jakevin/fastcontext-agent-tools
cd fastcontext-agent-tools
python -m pip install -e .
```

如果 `fastcontext-mcp` 不在 `PATH`，請用 `python -m fastcontext_mcp` 啟動。

## 環境變數

```bash
export BASE_URL="http://127.0.0.1:30000/v1"
export MODEL="microsoft/FastContext-1.0-4B-SFT"
export API_KEY="your-api-key"
export FASTCONTEXT_ALLOWED_ROOTS="/path/to/repos"
```

`FASTCONTEXT_ALLOWED_ROOTS` 是安全白名單。MCP server 只會允許探索這些目錄底下的 repo。多個路徑請用系統的 `os.pathsep` 分隔：macOS/Linux 是 `:`，Windows 是 `;`。

## MCP 設定範例

```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "python",
      "args": ["-m", "fastcontext_mcp"],
      "env": {
        "BASE_URL": "http://127.0.0.1:30000/v1",
        "MODEL": "microsoft/FastContext-1.0-4B-SFT",
        "API_KEY": "your-api-key",
        "FASTCONTEXT_ALLOWED_ROOTS": "/path/to/repos"
      }
    }
  }
}
```

## 工具

- `fastcontext_health`：檢查 CLI、endpoint 變數與 repo allowlist。
- `fastcontext_explore`：送出自然語言探索 query，回傳 citations 與 raw output。
- `fastcontext_explore_with_trace`：同上，但另外寫出 FastContext trajectory JSONL。

## 建議使用方式

適合用在：

- 不熟悉的中大型 codebase。
- 需要先找出功能入口、錯誤路徑、測試位置。
- 主 agent 不應該把大量 grep/read 歷史塞進自己的 context。

不適合用在：

- 已經知道要改哪個檔案。
- 很小的單檔問題。
- 需要直接修改檔案的任務。FastContext 只負責找 context。

給 LLM agent 的一句話：

> 請安裝 `https://github.com/Jakevin/fastcontext-agent-tools`，執行 `python -m pip install -e .`，把 `python -m fastcontext_mcp` 設成 stdio MCP server，設定 `BASE_URL`、`MODEL`、`API_KEY`、`FASTCONTEXT_ALLOWED_ROOTS`，並啟用 `skills/fastcontext-explorer`。

