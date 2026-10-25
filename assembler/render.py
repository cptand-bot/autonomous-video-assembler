from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from .captions import write_ass


class RenderError(RuntimeError):
    pass


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RenderError(f"ffmpeg failed ({result.returncode}): {detail}")


def render_video(root: Path, output: Path, audio: Path | None = None, captions: bool = False) -> dict:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    scenes = payload.get("scenes", [])
    if not scenes:
        raise RenderError("no scenes")
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    missing = [str(s["id"]) for s in scenes if str(s["id"]) not in manifest and not str(s.get("source", "")).startswith("card:")]
    if missing:
        raise RenderError("missing scene images: " + ", ".join(missing))
    captions_path = root / "captions.ass"
    if captions and not captions_path.exists():
        write_ass(scenes, captions_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    overlays = json.loads((root / "overlays.json").read_text(encoding="utf-8")) if (root / "overlays.json").exists() else {}
    with tempfile.TemporaryDirectory() as temp:
        clips: list[Path] = []
        for scene in scenes:
            sid = str(scene["id"]); clip = Path(temp) / f"{int(sid):04d}.mp4"
            is_card = sid not in manifest
            image = root / manifest[sid]["path"] if not is_card else None
            is_video = bool(image and image.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"})
            command = ["ffmpeg", "-y"] + (["-f", "lavfi", "-i", f"color=c=0x171522:s=1920x1080:r=25"] if is_card else (["-stream_loop", "-1"] if is_video else ["-loop", "1"]) + ["-i", str(image)])
            ov = overlays.get(sid, {})
            has_photo = bool(ov.get("photo") and (root / ov["photo"]).exists())
            if has_photo:
                command += ["-loop", "1", "-i", str(root / ov["photo"])]
                command += ["-t", str(scene["duration_sec"]), "-filter_complex", scene_filter(root, scene, ov), "-map", "[vout]"]
            elif is_card:
                command += ["-t", str(scene["duration_sec"]), "-vf", card_filter(scene)]
            else:
                command += ["-t", str(scene["duration_sec"]), "-vf", scene_filter(root, scene, ov)]
            command += ["-r", "25", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(clip)]
            run_ffmpeg(command)
            clips.append(clip)
        concat = Path(temp) / "concat.txt"
        concat.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
        if audio:
            command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
        if captions_path.exists():
            ass_filter_path = captions_path.as_posix().replace(":", r"\:")
            command += ["-vf", f"subtitles=filename='{ass_filter_path}'", "-c:v", "libx264"]
        else: command += ["-c:v", "copy"]
        command.append(str(output)); run_ffmpeg(command)
    result = {"status": "rendered", "output": str(output), "scene_count": len(scenes), "duration_sec": round(sum(s["duration_sec"] for s in scenes), 3)}
    (root / "render_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def scene_filter(root: Path, scene: dict, overlay: dict) -> str:
    filters = ["scale=1920:1080:force_original_aspect_ratio=decrease", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"]
    post_filters = []
    photo_graph = None
    if overlay.get("photo"):
        photo = root / overlay["photo"]
        if photo.exists():
            chain = ",".join(filters)
            x = overlay.get("pos", {}).get("x", 80); y = overlay.get("pos", {}).get("y", 90)
            at = overlay.get("at", 0.35)
            scale = float(overlay.get("scale", 1) or 1)
            scale = min(2.4, max(0.4, scale))
            photo_graph = f"[0:v]{chain}[base];[1:v]format=rgba,scale=iw*{scale}:ih*{scale}[ov];[base][ov]overlay={x}:{y}:enable='between(t,{at},{at + 3})'[base2]"
    text = overlay.get("text", {})
    if text.get("words"):
        words = str(text["words"]).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        x, y = text_position(text.get("pos", "tl"))
        post_filters.append(f"drawtext=text='{words}':x={x}:y={y}:fontsize=48:fontcolor={text.get('color', 'white')}:enable='between(t,{text.get('at', 0.35)},{text.get('at', 0.35)+3})'")
    ticker = overlay.get("ticker", {})
    if ticker.get("words"):
        words = str(ticker["words"]).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        post_filters.append(f"drawtext=text='{words}':x=(w-text_w)/2:y=h-120:fontsize=38:fontcolor=white:enable='between(t,{ticker.get('at', 0)},{ticker.get('at', 0)+4})'")
    if photo_graph:
        tail = ",".join(post_filters)
        return photo_graph + (f";[base2]{tail}[vout]" if tail else ";[base2]null[vout]")
    return ",".join(filters + post_filters)


def text_position(pos: str) -> tuple[str, str]:
    positions = {
        "tl": ("80", "80"), "tc": ("(w-text_w)/2", "80"), "tr": ("w-text_w-80", "80"),
        "ml": ("80", "(h-text_h)/2"), "mc": ("(w-text_w)/2", "(h-text_h)/2"), "mr": ("w-text_w-80", "(h-text_h)/2"),
        "bl": ("80", "h-text_h-140"), "bc": ("(w-text_w)/2", "h-text_h-140"), "br": ("w-text_w-80", "h-text_h-140"),
    }
    return positions.get(str(pos), positions["tl"])


def card_filter(scene: dict) -> str:
    text = str(scene.get("text", "")).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    return f"drawtext=text='{text}':x=120:y=(h-text_h)/2:fontsize=56:fontcolor=white:line_spacing=18"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render storyboard to MP4")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--output", type=Path, default=Path("build/output.mp4"))
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--captions", action="store_true")
    args = parser.parse_args(); audio = args.audio if args.audio and args.audio.is_file() else None; print(json.dumps(render_video(args.root, args.output, audio, args.captions), ensure_ascii=False))


if __name__ == "__main__":
    main()
