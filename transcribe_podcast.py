#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "openai-whisper",
#     "pydub",
# ]
# ///
"""
Podcast文字起こしスクリプト（ステレオ左右話者分離対応）

使い方:
  uv run transcribe_podcast.py input.wav
  uv run transcribe_podcast.py input.wav --left-name ホスト --right-name ゲスト --format tsv

オプション:
  --model large-v3       Whisperモデル（default: large-v3, 精度重視）
  --model medium         速度重視の場合
  --left-name ホスト     左チャンネルの話者名（default: Speaker_L）
  --right-name ゲスト    右チャンネルの話者名（default: Speaker_R）
  --output output.txt    出力ファイル名（default: {入力ファイル名}_transcript.{format}）
  --format txt           出力形式: txt, tsv, srt, json（default: txt）
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import whisper
from pydub import AudioSegment


def split_stereo(input_path: str, tmpdir: str) -> tuple[str, str]:
    """ステレオWAVを左右モノラルに分割"""
    print("🔀 ステレオを左右チャンネルに分割中...")
    audio = AudioSegment.from_wav(input_path)

    if audio.channels != 2:
        print(
            f"⚠️  チャンネル数が {audio.channels} です。ステレオ(2ch)を想定しています。"
        )
        if audio.channels == 1:
            print("   モノラルファイルです。両チャンネル同一として処理します。")
            left_path = os.path.join(tmpdir, "left.wav")
            audio.export(left_path, format="wav")
            return left_path, left_path

    channels = audio.split_to_mono()
    left_path = os.path.join(tmpdir, "left.wav")
    right_path = os.path.join(tmpdir, "right.wav")
    channels[0].export(left_path, format="wav")
    channels[1].export(right_path, format="wav")

    duration_sec = len(audio) / 1000
    print(f"   ✅ 分割完了（{duration_sec:.1f}秒 = {duration_sec / 60:.1f}分）")
    return left_path, right_path


def transcribe_channel(model, audio_path: str, label: str) -> list[dict]:
    """1チャンネルをWhisperで文字起こし"""
    print(f"🎙️  {label} を文字起こし中...（しばらくかかります）")

    result = model.transcribe(
        audio_path,
        language="ja",
        verbose=False,
        word_timestamps=False,
        no_speech_threshold=0.4,
        logprob_threshold=-0.8,
        condition_on_previous_text=False,
        fp16=False,
    )

    segments = []
    for seg in result["segments"]:
        segments.append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "speaker": label,
            }
        )

    print(f"   ✅ {label} 完了: {len(segments)} セグメント")
    return segments


def merge_segments(left_segs: list[dict], right_segs: list[dict]) -> list[dict]:
    """左右のセグメントをタイムスタンプ順にマージ"""
    all_segs = left_segs + right_segs
    all_segs.sort(key=lambda s: s["start"])
    return [s for s in all_segs if s["text"] and s["text"] != "..."]


def dedup_crosstalk(
    segments: list[dict], time_window: float = 2.0, sim_threshold: float = 0.45
) -> list[dict]:
    """左右チャンネル間の音漏れ重複を除去する。

    同じ時間帯（±time_window秒）に異なる話者で類似テキスト（sim_threshold以上）が
    ある場合、テキストが長い方（＝本来の話者側でより正確に拾えている方）を残す。
    """
    from difflib import SequenceMatcher

    remove = set()
    for i in range(len(segments)):
        if i in remove:
            continue
        for j in range(i + 1, len(segments)):
            if j in remove:
                continue
            # 時間が離れすぎたら打ち切り（ソート済み前提）
            if segments[j]["start"] - segments[i]["start"] > time_window + 2:
                break
            # 同じ話者はスキップ
            if segments[i]["speaker"] == segments[j]["speaker"]:
                continue
            # 時間の重なりチェック
            overlap_start = max(segments[i]["start"], segments[j]["start"])
            overlap_end = min(segments[i]["end"], segments[j]["end"])
            if overlap_end - overlap_start < -time_window:
                continue
            # テキスト類似度
            sim = SequenceMatcher(
                None, segments[i]["text"], segments[j]["text"]
            ).ratio()
            if sim >= sim_threshold:
                # 長い方を残す
                if len(segments[i]["text"]) >= len(segments[j]["text"]):
                    remove.add(j)
                else:
                    remove.add(i)

    kept = [s for idx, s in enumerate(segments) if idx not in remove]
    print(
        f"🔇 クロストーク重複除去: {len(remove)} セグメント除去 → {len(kept)} セグメント残存"
    )
    return kept


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def format_srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def output_txt(segments: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for seg in segments:
            ts = format_timestamp(seg["start"])
            f.write(f"[{ts}] {seg['speaker']}: {seg['text']}\n")
    print(f"📄 テキスト出力: {path}")


def output_tsv(segments: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("start\tend\tspeaker\ttext\tkeep\tnote\n")
        for seg in segments:
            start = format_timestamp(seg["start"])
            end = format_timestamp(seg["end"])
            f.write(f"{start}\t{end}\t{seg['speaker']}\t{seg['text']}\t1\t\n")
    print(f"📊 TSV出力: {path}")
    print("   → スプレッドシートで開いて keep=0 にした行をカット対象にできます")


def output_srt(segments: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = format_srt_timestamp(seg["start"])
            end = format_srt_timestamp(seg["end"])
            f.write(f"{i}\n{start} --> {end}\n{seg['speaker']}: {seg['text']}\n\n")
    print(f"🎬 SRT出力: {path}")


def output_json(segments: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    print(f"🔧 JSON出力: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Podcast文字起こし（ステレオ左右話者分離）"
    )
    parser.add_argument("input", help="入力WAVファイル")
    parser.add_argument(
        "--model", default="large-v3", help="Whisperモデル (default: large-v3)"
    )
    parser.add_argument(
        "--left-name",
        default="Speaker_L",
        help="左チャンネルの話者名 (default: Speaker_L)",
    )
    parser.add_argument(
        "--right-name",
        default="Speaker_R",
        help="右チャンネルの話者名 (default: Speaker_R)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="出力ファイルパス (default: {input}_transcript.{format})",
    )
    parser.add_argument(
        "--format",
        default="txt",
        choices=["txt", "tsv", "srt", "json"],
        help="出力形式 (default: txt)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ ファイルが見つかりません: {args.input}")
        sys.exit(1)

    if args.output is None:
        stem = Path(args.input).stem
        args.output = f"{stem}_transcript.{args.format}"

    print(f"🤖 Whisperモデル ({args.model}) を読み込み中...")
    model = whisper.load_model(args.model)
    print("   ✅ モデル読み込み完了")

    with tempfile.TemporaryDirectory() as tmpdir:
        left_path, right_path = split_stereo(args.input, tmpdir)
        left_segs = transcribe_channel(model, left_path, args.left_name)
        right_segs = transcribe_channel(model, right_path, args.right_name)

    merged = merge_segments(left_segs, right_segs)
    merged = dedup_crosstalk(merged)
    print(f"\n📋 合計: {len(merged)} セグメント")

    formatters = {
        "txt": output_txt,
        "tsv": output_tsv,
        "srt": output_srt,
        "json": output_json,
    }
    formatters[args.format](merged, args.output)

    # JSON も常に出力（後続処理用）
    if args.format != "json":
        json_path = str(Path(args.output).with_suffix(".json"))
        output_json(merged, json_path)

    print("\n✨ 完了！")
    print(
        "   次のステップ: 出力ファイルをClaudeにアップロードして編集・ショーノート作成"
    )


if __name__ == "__main__":
    main()
