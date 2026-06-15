# FastContext Setup Reference

Use this reference only when the user asks to install, configure, or debug the FastContext MCP integration.

## Upstream FastContext CLI

Install Microsoft's FastContext CLI from the upstream repository:

```bash
git clone https://github.com/microsoft/fastcontext
cd fastcontext
uv tool install .
```

The MCP wrapper calls the `fastcontext` executable. It does not download model weights or start an inference server.

## Endpoint Environment

FastContext expects an OpenAI-compatible endpoint:

```bash
export BASE_URL="https://your-endpoint.example/v1"
export MODEL="microsoft/FastContext-1.0-4B-SFT"
export API_KEY="your-api-key"
```

`API_KEY` can be omitted only when the endpoint does not require authentication.

## Repository Allowlist

Set `FASTCONTEXT_ALLOWED_ROOTS` to restrict what the MCP server may explore:

```bash
export FASTCONTEXT_ALLOWED_ROOTS="/Users/me/projects:/Users/me/work"
```

If unset, the MCP server allows only repositories under the directory where the server process starts.

