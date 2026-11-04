# /// script
# requires-python = ">=3.12"
# dependencies = ["openai", "langfuse>=5.1,<6", "e2b>=2.62.0", "python-dotenv"]
# ///
"""Key check: one traced OpenRouter call in Langfuse, one E2B sandbox running python --version.

Usage: uv run scripts/check_keys.py .env
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(sys.argv[1])
need = ["OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "E2B_API_KEY"]
missing = [k for k in need if not os.environ.get(k)]
if missing:
    sys.exit(f"missing: {', '.join(missing)}")

from langfuse import get_client
from langfuse.openai import OpenAI

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
resp = client.chat.completions.create(
    model="qwen/qwen3-coder",
    messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    max_tokens=5,
    name="key-check",
)
print("openrouter:", resp.choices[0].message.content.strip(), "| tokens:", resp.usage.total_tokens)
lf = get_client()
lf.flush()
print("langfuse auth:", lf.auth_check())

from e2b import Sandbox

sbx = Sandbox.create() if hasattr(Sandbox, "create") else Sandbox()
try:
    r = sbx.commands.run("python --version")
    print("e2b:", (r.stdout or r.stderr).strip())
finally:
    sbx.kill()
