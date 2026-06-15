# FastContext MCP ガイド（日本語）

このプロジェクトは Microsoft FastContext を MCP stdio server として利用できるようにするものです。LLM coding agent は read-only の repository exploration を委譲し、関連するファイルと行番号の citation を受け取り、その後に main agent が自分で該当コードを確認します。

## 必要条件

- Python 3.10+：この MCP wrapper 用。
- Python 3.12+：上流 FastContext CLI 用。
- Microsoft FastContext CLI：<https://github.com/microsoft/fastcontext>
- FastContext model を提供する OpenAI-compatible endpoint。

上流 CLI のインストール例：

```bash
git clone https://github.com/microsoft/fastcontext
cd fastcontext
uv tool install .
```

## この MCP Server のインストール

```bash
git clone https://github.com/Jakevin/fastcontext-agent-tools
cd fastcontext-agent-tools
python -m pip install -e .
```

`fastcontext-mcp` が `PATH` にない場合は、`python -m fastcontext_mcp` を使ってください。

## 環境変数

```bash
export BASE_URL="http://127.0.0.1:30000/v1"
export MODEL="microsoft/FastContext-1.0-4B-SFT"
export API_KEY="your-api-key"
export FASTCONTEXT_ALLOWED_ROOTS="/path/to/repos"
```

`FASTCONTEXT_ALLOWED_ROOTS` は安全のための allowlist です。MCP server はこの配下の repository だけを探索します。複数のパスは OS の `os.pathsep` で区切ります。macOS/Linux は `:`、Windows は `;` です。

## MCP 設定例

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

## MCP Tools

- `fastcontext_health`：CLI、endpoint 設定、allowlist を確認します。
- `fastcontext_explore`：自然言語 query を FastContext に送り、citations と raw output を返します。
- `fastcontext_explore_with_trace`：探索結果に加えて trajectory JSONL を保存します。

## 推奨ワークフロー

使うべき場面：

- 未知または中規模以上の codebase。
- 機能の入口、エラー処理、テスト位置を探したい場合。
- main agent の context に大量の grep/read 履歴を残したくない場合。

避けるべき場面：

- 編集対象ファイルがすでに明確な場合。
- 小さな単一ファイルの作業。
- ファイル編集そのものを FastContext に任せたい場合。FastContext は探索専用です。

LLM agent に渡す一文：

> `https://github.com/Jakevin/fastcontext-agent-tools` をインストールし、`python -m pip install -e .` を実行して、`python -m fastcontext_mcp` を stdio MCP server として設定し、`BASE_URL`、`MODEL`、`API_KEY`、`FASTCONTEXT_ALLOWED_ROOTS` を指定したうえで `skills/fastcontext-explorer` を有効化してください。

