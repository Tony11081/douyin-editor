"""四项台账功能的离线验收：lavfi 视频、伪 ASR、真实 ffmpeg 和文件回读。"""
import asyncio
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image
import pytest
from starlette.requests import Request

os.environ.setdefault("ACCESS_TOKEN", "test-token-0123456789")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import editor
import server
import covers
import specs
import subtitles


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "DATA_DIR", tmp_path)
    for name, folder in (("VIDEOS", "videos"), ("OUTPUTS", "outputs"), ("MUSIC", "music")):
        path = tmp_path / folder
        path.mkdir()
        monkeypatch.setattr(editor, name, path)
    def no_network(*a, **k):
        raise AssertionError("离线测试不允许网络请求")
    monkeypatch.setattr(editor.requests.sessions.Session, "request", no_network)


def video(ident="toolkitvid01", duration=3, hdr=False):
    path = editor.VIDEOS / ident
    path.mkdir()
    flags = (["-vf", "format=yuv420p10le", "-c:v", "libx265", "-pix_fmt", "yuv420p10le",
              "-x265-params", "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc",
              "-color_trc", "arib-std-b67", "-color_primaries", "bt2020", "-colorspace", "bt2020nc"]
             if hdr else ["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc2=s=240x426:r=20:d={duration}", "-f", "lavfi", "-i",
                    f"sine=f=440:d={duration}", *flags, "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(path / "source.mp4")], check=True, timeout=90)
    meta = {"video_id": ident, "source": "source.mp4", **editor.probe(path / "source.mp4")}
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    tr = {"language": "zh", "words": [{"i": 0, "s": 0, "e": 1, "w": "IC"},
                                        {"i": 1, "s": 1, "e": 2, "w": "报品"}],
          "segments": [{"s": 0, "e": 1, "text": "IC", "w0": 0, "w1": 0},
                       {"s": 1, "e": 2, "text": "报品", "w0": 1, "w1": 1}]}
    (path / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    return ident


def render_spec(vid):
    return {"video_id": vid, "clips": [{"start": 0, "end": 2, "text": "IC报品", "sub": "Etsy product"}],
            "width": 240, "height": 426, "fps": 20, "preset": "ultrafast",
            "effects": {"drift": 0, "sfx": False, "flash_first": False, "progress_bar": False},
            "audio": {"denoise": False, "loudnorm": False}}


def wait(jid):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        job = server._jobs[jid]
        if job["state"] in ("done", "error"):
            assert job["state"] == "done", job.get("error")
            return server._job_view(job)["result"]
        time.sleep(0.05)
    pytest.fail("后台任务超时")


def test_transcript_range_and_default():
    vid = video()
    assert server.get_transcript(vid) == "S0 [0.00-1.00] IC\n   0.00~1.00IC\nS1 [1.00-2.00] 报品\n   1.00~2.00报品"
    assert server.get_transcript(vid, 1, 2, False) == "S1 [1.00-2.00] 报品"
    assert server.get_transcript(vid, 1.5, 1.8) == "S1 [1.00-2.00] 报品\n   1.00~2.00报品"
    for args in ((-1, None, True), (2, 1, True), (float("nan"), None, True), (None, None, "no")):
        with pytest.raises(editor.EditorError):
            server.get_transcript(vid, *args)


def test_batch_rejects_all_and_named_outputs(monkeypatch):
    spec = render_spec(video())
    calls = []
    with monkeypatch.context() as m:
        m.setattr(server, "_submit", lambda *a, **k: calls.append(a))
        with pytest.raises(editor.EditorError, match="第 2 条"):
            server.render_batch([spec, {**spec, "width": 241}])
        assert calls == []
        with pytest.raises(editor.EditorError, match="names"):
            server.render_batch([spec], [])
    before = copy.deepcopy(spec)
    ids = server.render_batch([spec, spec], ["直播一", "直播二"])["job_ids"]
    outputs = [wait(jid) for jid in ids]
    assert spec == before
    for name, result in zip(["直播一", "直播二"], outputs):
        saved = editor.load_output(result["output_id"])
        assert saved["name"] == name
        assert any(r.get("name") == name for r in server.list_outputs())
    old = editor.render(copy.deepcopy(spec))
    assert "name" not in old
    row = next(r for r in server.list_outputs() if r["output_id"] == old["output_id"])
    assert set(row) == {"output_id", "video_id", "duration", "download_url"}


def test_chunked_asr_offsets_prompt_and_bounded_decode(monkeypatch):
    vid = video(duration=1)
    path = editor.video_dir(vid) / "meta.json"
    meta = editor.load_meta(vid)
    meta["duration"] = 3601
    path.write_text(json.dumps(meta))
    decoded, prompts = [], []
    real_run = editor.subprocess.run
    def decode(cmd, **kwargs):
        if "f32le" not in cmd:
            return real_run(cmd, **kwargs)
        decoded.append((float(cmd[cmd.index("-ss") + 1]), float(cmd[cmd.index("-t") + 1])))
        # 每段只需要少量假 PCM；时间偏移由伪 Whisper 明确给出。
        return subprocess.CompletedProcess(cmd, 0, np.zeros(16000, dtype=np.float32).tobytes(), b"")
    class FakeWhisper:
        def transcribe(self, audio, **kwargs):
            assert len(audio) == 16000
            prompts.append(kwargs["initial_prompt"])
            word = types.SimpleNamespace(start=.1, end=.8, word="IC")
            return iter([types.SimpleNamespace(start=0, end=.9, text="IC", words=[word])]), None
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisper))
    monkeypatch.setattr(editor, "_model", FakeWhisper())
    monkeypatch.setattr(editor.subprocess, "run", decode)
    progress = []
    result = editor.transcribe(vid, progress=progress.append)
    assert decoded == [(i * 600, 600 if i < 6 else 1) for i in range(7)]
    assert [w["s"] for w in result["words"]] == [i * 600 + .1 for i in range(7)]
    assert [s["w0"] for s in result["segments"]] == list(range(7))
    assert all("以下是普通话口播" in p and "Etsy" in p for p in prompts)
    assert progress[-1] == "已转写 60.0/60.0 分钟"
    assert editor.load_transcript(vid) == result


def test_glossary_atomic_merge_overrides_and_all_sources(monkeypatch):
    assert server.glossary_list() == editor.GLOSSARY_DEFAULTS
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: server.glossary_set({f"错{i}": f"正{i}"}), range(12)))
    assert len(server.glossary_list()) == 20
    assert "错0" not in server.glossary_remove(["错0"])
    for bad in ({"": "a"}, {"a": ""}, {"a": 1}, []):
        with pytest.raises(editor.EditorError):
            server.glossary_set(bad)
    spec = render_spec(video())
    for text in (True, False):
        s = copy.deepcopy(spec)
        if not text:
            s["clips"][0].pop("text")
        s["corrections"] = {"IC": "Custom"}
        plan = editor.plan_view(editor.plan_render(s))
        assert "Custom爆品" == "".join(c["text"] for c in plan["captions"])
        assert plan["applied"]["corrections"] == {"IC": "Custom", "报品": "爆品"}
    placed = [{"start": 0, "end": 2, "text": "IC报品"}]
    monkeypatch.setattr(server.tts_mod, "plan_voice", lambda *a: placed)
    spec.update(captions="voiceover", voiceover={"tts_id": "testtts00001"})
    result = editor.plan_view(editor.plan_render(spec))
    assert "Etsy爆品" == "".join(c["text"] for c in result["captions"])
    tokens = editor._tokens_from_words([{"s": 0, "e": 2, "w": "前IC后"}], 0, 2, {"IC": "Etsy"})
    assert "".join(t["w"] for t in tokens) == "前Etsy后"
    assert tokens[0]["s"] == 0 and tokens[-1]["e"] == 2
    # 替换结果不再被词表二次替换，三个字幕来源遵守同一规则。
    assert editor._correct_text("意见代发", {"意见代发": "IC", "IC": "Etsy"}, {}) == "IC"


def test_cover_hlg_render_first_frame_and_unchanged_timing(tmp_path):
    vid = video(hdr=True)
    jid = server.make_cover(video_id=vid, time=.5, title="直播爆品\nEtsy 一件代发",
                            subtitle="封面测试", style={"highlight": ["Etsy"]})["job_id"]
    result = wait(jid)
    image = Image.open(covers.cover_path(result["cover_id"]))
    assert image.size == (1080, 1920)
    assert "/covers/" in result["download_url"]
    # 直接回读 PNG：标题黄字、白字存在，底部与相同 HDR 映射的参考帧一致。
    pixels = np.array(image)
    assert ((pixels[:, :, 0] > 230) & (pixels[:, :, 1] > 180) & (pixels[:, :, 2] < 70)).sum() > 500
    meta = editor.load_meta(vid)
    assert meta["color_transfer"] == "arib-std-b67"
    assert "tonemap" in editor._color_filter(meta, {})
    cmd = ["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(editor.video_dir(vid) / meta["source"]),
           "-frames:v", "1", "-vf", editor._color_filter(meta, {}) +
           "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
           "-f", "image2pipe", "-c:v", "png", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    assert np.array_equal(pixels[1200:], np.array(Image.open(io.BytesIO(raw)).convert("RGB"))[1200:])
    font = covers._font(100)
    assert bytes(font.getmask("直")) != bytes(font.getmask("\U0010ffff"))
    spec = render_spec(vid)
    plain = editor.render(copy.deepcopy(spec))
    spec["cover"] = {"cover_id": result["cover_id"]}
    covered = editor.render(spec)
    assert covered["captions"] == plain["captions"] and covered["subs"] == plain["subs"]
    assert abs(editor.probe(editor.OUTPUTS / covered["file"])["duration"] - plain["duration"]) < .06
    frames = [Image.open(io.BytesIO(f)).convert("RGB") for f in editor.frames("output", covered["output_id"], [0, .8], 240)]
    expected = np.array(image.resize(frames[0].size), dtype=float)
    first, later = (np.array(f, dtype=float) for f in frames)
    assert np.abs(first - expected).mean() < 12
    assert np.abs(later - expected).mean() > 15
    def pcm(output):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(editor.OUTPUTS / output["file"]),
                               "-vn", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    assert pcm(plain) == pcm(covered)
    assert server.make_cover(output_id=covered["output_id"], title="成片封面")
    # 等待任务结束，避免测试退出后后台线程继续访问临时目录。
    last = [j for j in server._jobs.values() if j["kind"] == "cover"][-1]
    wait(last["job_id"])


@pytest.mark.parametrize("change", [{"style": {"colour": "red"}}, {"time": float("nan")},
                                     {"time": 99}, {"title": ""}, {"style": {"y": -1}},
                                     {"style": {"highlight": ["不存在"]}}])
def test_cover_invalid(change):
    with pytest.raises(editor.EditorError):
        server.make_cover(**{"video_id": video(), "title": "正常标题", **change})


def test_subtitles_bilingual_player_and_mux_speed(tmp_path):
    spec = render_spec(video())
    rendered = editor.render(spec)
    for fmt in ("srt", "vtt"):
        out = server.export_subtitles(rendered["output_id"], fmt, True)
        path = editor.DATA_DIR / "subtitles" / out["file"]
        body = path.read_text(encoding="utf-8")
        assert "Etsy爆品\nEtsy product" in body
        assert body.startswith("WEBVTT\n\n") == (fmt == "vtt")
        # libavformat 解码字幕，并由 libass 实际烧录，检查播放器可用的两行内容。
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "ass", "-"],
                           capture_output=True, check=True)
        assert "Etsy爆品\\NEtsy product" in p.stdout.decode("utf-8")
    for speed in (.5, 1, 2):
        out = editor.mux({"output_id": rendered["output_id"], "speed": speed, "original_volume": 1})
        reread = editor.load_output(out["output_id"])
        assert reread["captions"][0]["end"] == rendered["captions"][0]["end"] / speed
        assert reread["subs"][0]["end"] == rendered["subs"][0]["end"] / speed
        assert abs(editor.probe(editor.OUTPUTS / out["file"])["duration"] - 2 / speed) < .12
        assert server.export_subtitles(out["output_id"], bilingual=True)["count"] > 0
        assert any(r.get("source_output_id") == rendered["output_id"] for r in server.list_outputs())
    external = editor.mux({"video_id": spec["video_id"], "speed": 2, "original_volume": 1})
    with pytest.raises(editor.EditorError, match="output_id"):
        server.export_subtitles(external["output_id"])


def test_subtitle_alignment_and_invalid_inputs():
    cues = [{"start": 0, "end": 2, "text": "原文"}]
    subs = [{"start": 0, "end": 1, "text": "one"}, {"start": 1, "end": 2, "text": "two"}]
    aligned = subtitles._bilingual(cues, subs)
    assert [c["text"] for c in aligned] == ["原文\none", "原文\ntwo"]
    for bad in ([], subs[:1], subs + subs[:1]):
        with pytest.raises(editor.EditorError, match="译文"):
            subtitles._bilingual(cues, bad)
    for fmt, bilingual in (("ass", False), ("srt", "yes")):
        with pytest.raises(editor.EditorError):
            subtitles.export("invalid", fmt, bilingual)
    for obj in ({"output_id": "a" * 12, "video_id": "toolkitvid01"}, {}, {"output_id": "a" * 12, "speed": float("inf")}):
        with pytest.raises(editor.EditorError):
            specs.validate(obj, "mux")


def test_file_routes_and_cover_spec_validation():
    cover_id = "abcdef012345"
    path = editor.DATA_DIR / "covers" / f"{cover_id}.png"
    path.parent.mkdir()
    Image.new("RGB", (1080, 1920), "white").save(path)
    sub = editor.DATA_DIR / "subtitles" / f"{cover_id}_bilingual.srt"
    sub.parent.mkdir()
    sub.write_text("1\n00:00:00,000 --> 00:00:01,000\n原文\ntranslation\n", encoding="utf-8")
    for fn, filename in ((server.cover_files, path.name), (server.subtitle_files, sub.name)):
        for token, name, status in ((server.TOKEN, filename, 200), ("wrong", filename, 404),
                                     (server.TOKEN, "../" + filename, 404), (server.TOKEN, "a" * 12 + ".png", 404)):
            response = asyncio.run(fn(Request({"type": "http", "path_params": {"token": token, "name": name}})))
            assert response.status_code == status
    spec = render_spec(video())
    for cover in ({"cover_id": cover_id, "duration": 3}, {"cover_id": "../x"},
                  {"cover_id": cover_id, "duration": 0}, {"cover_id": cover_id, "typo": 1}):
        with pytest.raises(editor.EditorError):
            editor.plan_render({**spec, "cover": cover})
