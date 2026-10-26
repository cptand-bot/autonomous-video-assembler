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


def render_video(root: Path, output: Path, audio: Path | None = None, captions: bool = False, require_approval: bool = True) -> dict:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    scenes = payload.get("scenes", [])
    if not scenes:
        raise RenderError("no scenes")
    # Рендер идёт ТОЛЬКО по утверждению человека. Раньше approval.json не читал
    # никто: кнопка «Утвердить ролик» была украшением, а джоб render рендерил
    # артефакт того же прогона — до того, как человек что-то увидел.
    if require_approval:
        approval_path = root / "approval.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path.exists() else {}
        if not approval.get("approved"):
            raise RenderError(
                "ролик не утверждён человеком: нет approved в approval.json. "
                "Откройте review.html, нажмите «✅ Утвердить ролик», затем «💾 Скачать правки» "
                "и примените файл: python -m assembler.apply_changes --root <root> --changes review_changes.json"
            )
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    missing = [str(s["id"]) for s in scenes if (str(s["id"]) not in manifest or manifest.get(str(s["id"]), {}).get("status") in {"FAILED", "placeholder"}) and not str(s.get("source", "")).startswith("card:")]
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
            if is_card:
                command += ["-t", str(scene["duration_sec"]), "-vf", card_filter(scene)]
            else:
                command += ["-t", str(scene["duration_sec"]),
                            "-filter_complex", scene_filter(root, scene, ov, is_video=is_video, has_photo=has_photo),
                            "-map", "[vout]"]
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


FRAME_W, FRAME_H, FPS = 1920, 1080, 25
# Доля ширины кадра, которую занимает фото-всплывашка. Считается ОТ КАДРА, а не
# от размера исходного фото: иначе крупное фото накрывает пол-экрана, а мелкое
# становится микроскопическим, и размер оказывается случайным.
OVERLAY_WIDTH_SHARE = 0.34
ZOOM_AMPLITUDE = 0.045  # 1 -> 1,045 за сцену: приближение заметно, но не дёргает


def _esc(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def _window(overlay: dict, duration: float, minimum: float = 3.0) -> tuple[float, float]:
    """Окно показа всплывашки. Она ДЕРЖИТ сцену, а не мелькает три секунды."""
    at = float(overlay.get("at", 0.35) or 0)
    start = at * duration if at <= 1 else at
    start = max(0.0, min(start, max(0.0, duration - minimum)))
    end = max(start + minimum, duration - 0.3)
    return round(start, 2), round(min(end, duration), 2)


def base_graph(scene: dict, is_video: bool = False) -> str:
    """Кадр без чёрных полей и с медленным зумом в одну сторону.

    Было: scale+pad заливал края чёрным — 23 кадра из 55 давали полосы, у
    вертикальных экран был чёрным на две трети. И не было никакого движения:
    фото висело неподвижным все 11 секунд сцены.
    """
    duration = max(0.1, float(scene.get("duration_sec", 5) or 5))
    frames = max(1, int(round(duration * FPS)))
    graph = (
        "[0:v]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=increase,"
        f"crop={FRAME_W}:{FRAME_H},gblur=sigma=30,eq=brightness=-0.16[bg];"
        f"[fgsrc]scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[flat]"
    )
    if is_video:
        return graph + ";[flat]null[base]"
    zoom = (
        f"zoompan=z='1+{ZOOM_AMPLITUDE}*on/{frames}'"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={FRAME_W}x{FRAME_H}:fps={FPS}"
    )
    return graph + f";[flat]{zoom}[base]"


def overlay_position(pos: str) -> tuple[str, str]:
    """Углы, никогда не центр: центр кадра занят лицом или предметом."""
    margin = 70
    corners = {
        "tl": (str(margin), str(margin)),
        "tr": (f"W-w-{margin}", str(margin)),
        "bl": (str(margin), f"H-h-{margin}"),
        "br": (f"W-w-{margin}", f"H-h-{margin}"),
    }
    return corners.get(str(pos), corners["tr"])


def scene_filter(root: Path, scene: dict, overlay: dict, is_video: bool = False, has_photo: bool | None = None) -> str:
    duration = max(0.1, float(scene.get("duration_sec", 5) or 5))
    graph = [base_graph(scene, is_video)]
    label = "base"
    photo = root / str(overlay.get("photo", "")) if overlay.get("photo") else None
    if has_photo is None:
        has_photo = bool(photo and photo.exists())
    if has_photo and overlay.get("photo"):
        scale = min(1.6, max(0.6, float(overlay.get("scale", 1) or 1)))
        width = int(FRAME_W * OVERLAY_WIDTH_SHARE * scale)
        start, end = _window(overlay, duration)
        x, y = overlay_position(overlay.get("corner") or overlay.get("pos") or "tr")
        # Рамка-пластина вокруг всплывашки: она читается как вставка, а не как
        # случайный прямоугольник поверх кадра.
        graph.append(
            f"[1:v]format=rgba,scale={width}:-1,"
            "pad=iw+10:ih+10:5:5:color=0xf2f4f8@0.92,"
            "pad=iw+6:ih+6:3:3:color=0x11131a@0.85[ov]"
        )
        graph.append(f"[{label}][ov]overlay={x}:{y}:enable='between(t,{start},{end})'[withov]")
        label = "withov"
    text = overlay.get("text", {}) or {}
    tail: list[str] = []
    if text.get("words"):
        start, end = _window(text if text.get("at") is not None else overlay, duration)
        words = _esc(str(text["words"]).upper())
        x, y = text_position(text.get("pos", "tl"))
        # Тёмная пластина + белый капс. Жёлтый с обводкой запрещён.
        tail.append(
            f"drawtext=text='{words}':x={x}:y={y}:fontsize=46:fontcolor={text.get('color', 'white')}"
            ":box=1:boxcolor=0x14161a@0.82:boxborderw=22"
            f":enable='between(t,{start},{end})'"
        )
    ticker = overlay.get("ticker", {}) or {}
    if ticker.get("words"):
        start, end = _window(ticker if ticker.get("at") is not None else overlay, duration, minimum=4.0)
        words = _esc(str(ticker["words"]).upper())
        tail.append(
            f"drawtext=text='{words}':x=(w-text_w)/2:y=h-130:fontsize=38:fontcolor=white"
            ":box=1:boxcolor=0x14161a@0.82:boxborderw=18"
            f":enable='between(t,{start},{end})'"
        )
    graph.append(f"[{label}]{','.join(tail)}[vout]" if tail else f"[{label}]null[vout]")
    return ";".join(graph)


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
    parser.add_argument("--skip-approval", action="store_true", help="рендер без утверждения человеком: только для тестов")
    args = parser.parse_args(); audio = args.audio if args.audio and args.audio.is_file() else None; print(json.dumps(render_video(args.root, args.output, audio, args.captions, require_approval=not args.skip_approval), ensure_ascii=False))


if __name__ == "__main__":
    main()
