"""防回归：server.py 里的工具函数不能和导入的模块同名。
以前 `import tts` 之后又定义了工具函数 `def tts(...)`，模块被覆盖，
tts / tts_voices / get_tts 和试听链接全部报 AttributeError。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_server_names.py"""
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")
os.environ.setdefault("ACCESS_TOKEN", "test-token-0123456789")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import server  # noqa: E402

for name in ("editor", "tts_mod", "videogen", "heygen"):
    mod = getattr(server, name)
    assert isinstance(mod, types.ModuleType), f"server.{name} 被同名函数覆盖了：{mod!r}"
for fn in ("synthesize", "list_voices", "load", "preview"):
    assert callable(getattr(server.tts_mod, fn)), f"tts 模块缺少 {fn}"
assert callable(server.tts), "tts 工具函数不见了"
print("ok: server 模块名没有被工具函数覆盖")
