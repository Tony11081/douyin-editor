"""保留已有脚本测试，在独立进程执行，避免它们的 requests 替身互相覆盖。"""
import os
import subprocess
import sys
import tempfile

import pytest

_bootstrap = tempfile.TemporaryDirectory(prefix="editor-tests-")
os.environ["DATA_DIR"] = _bootstrap.name
os.environ["ACCESS_TOKEN"] = "test-token-0123456789"
os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
os.environ["HEYGEN_API_KEY"] = "hg-test"


def pytest_unconfigure(config):
    _bootstrap.cleanup()


LEGACY = {"test_render.py", "test_strict.py", "test_tts.py", "test_server_names.py",
          "test_videogen.py", "test_heygen.py"}


class ScriptModule(pytest.Module):
    def collect(self):
        def test_script(tmp_path):
            env = {**os.environ, "DATA_DIR": str(tmp_path), "HF_HUB_OFFLINE": "1"}
            if self.path.name == "test_render.py":
                video = tmp_path / "videos" / "testvideo01" / "source.mov"
                video.parent.mkdir(parents=True)
                music = tmp_path / "music" / "light.mp3"
                music.parent.mkdir()
                for args in (["-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=12", "-f", "lavfi",
                              "-i", "sine=f=220:d=12", "-c:v", "libx264", "-c:a", "aac", str(video)],
                             ["-f", "lavfi", "-i", "sine=f=440:d=12", str(music)]):
                    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=120)
            p = subprocess.run([sys.executable, "-X", "utf8", "-I", str(self.path)], env=env,
                               capture_output=True, encoding="utf-8", errors="replace", timeout=900)
            assert p.returncode == 0, p.stdout + p.stderr
        yield pytest.Function.from_parent(self, name="test_script", callobj=test_script)


def pytest_pycollect_makemodule(module_path, parent):
    if module_path.name in LEGACY:
        return ScriptModule.from_parent(parent, path=module_path)
