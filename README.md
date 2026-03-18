# audio-transcript

ステレオ録音されたPodcastの音声ファイルを、左右チャンネルで話者を分離しながら文字起こしするスクリプトです。  
[OpenAI Whisper](https://github.com/openai/whisper) を使用しており、日本語に最適化されています。

## 特徴

- **話者分離**: ステレオWAVの左右チャンネルをそれぞれ別の話者として文字起こし
- **タイムスタンプ付き出力**: 発話の開始・終了時刻を記録
- **複数の出力形式**: TXT / TSV / SRT / JSON に対応
- **`uv` 対応**: 依存ライブラリの事前インストール不要（`uv run` で直接実行可能）

## 必要環境

- Python 3.10 以上
- [uv](https://github.com/astral-sh/uv)（推奨）または pip

> **注意**: Whisper の `large-v3` モデルは初回実行時に自動ダウンロードされます（約3GB）。

## インストール

`uv` を使う場合、追加のインストールは不要です。

```bash
# uv がない場合
brew install uv
```

## 使い方

```bash
uv run transcribe_podcast.py input.wav
```

### 話者名を指定する

```bash
uv run transcribe_podcast.py input.wav --left-name ホスト --right-name ゲスト
```

### 出力形式を指定する

```bash
uv run transcribe_podcast.py input.wav --format tsv
```

## オプション一覧

| オプション     | デフォルト                             | 説明                                                          |
| -------------- | -------------------------------------- | ------------------------------------------------------------- |
| `--model`      | `large-v3`                             | Whisperモデル。精度重視なら `large-v3`、速度重視なら `medium` |
| `--left-name`  | `Speaker_L`                            | 左チャンネルの話者名                                          |
| `--right-name` | `Speaker_R`                            | 右チャンネルの話者名                                          |
| `--output`     | `{入力ファイル名}_transcript.{format}` | 出力ファイルパス                                              |
| `--format`     | `txt`                                  | 出力形式: `txt` / `tsv` / `srt` / `json`                      |

## 出力形式

### TXT（デフォルト）

```
[00:00] ホスト: こんにちは、今日のPodcastへようこそ。
[00:05] ゲスト: ありがとうございます。よろしくお願いします。
```

### TSV

スプレッドシートで開いて編集・カット判断に使えます。`keep` 列を `0` にした行をカット候補としてマークできます。

| start | end   | speaker | text          | keep | note |
| ----- | ----- | ------- | ------------- | ---- | ---- |
| 00:00 | 00:05 | ホスト  | こんにちは... | 1    |      |

### SRT

動画編集ソフトや字幕表示に使える標準字幕形式です。

### JSON

後続の自動処理やAIへの入力として使えます（`--format` が `txt`/`tsv`/`srt` のときも常に出力されます）。

## 次のステップ

出力された JSON または TXT ファイルを Claude などのAI にアップロードして、編集・ショーノートの作成・要約などに活用できます。

## 依存ライブラリ

- [openai-whisper](https://github.com/openai/whisper)
- [pydub](https://github.com/jiaaro/pydub)
