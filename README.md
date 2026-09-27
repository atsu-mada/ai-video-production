# ai-video-production

AI 映画・MV の「生成前」の工程を組み立てて検証するエージェントスキルです。Claude Code と Codex で使えます。

作者: あつまだ（ATSUFUMI KASHIMA） / GitHub [@atsu-mada](https://github.com/atsu-mada)

## できること

- 制作パッケージ（`00_common/`、シーン、カット manifest）の作成とレビュー
- キャラクター／環境／小道具／VFX シート
- 絵コンテ（画像のみ・テキスト付き）
- カットプロンプト、シーンプロンプト
- 生成ハンドオフ（プロバイダー、モデル、入力、尺、出力、検証項目を別スキルへ渡す形にまとめる）
- 標準ライブラリだけで動く Python の検証スクリプト

## インストール

### Claude Code（プラグイン）

```
/plugin marketplace add atsu-mada/ai-video-production
/plugin install ai-video-production@atsu-mada-ai-video-production
```

`/ai-video-production:ai-video-production` で呼び出せます。

### Claude Code（手動）

```bash
git clone https://github.com/atsu-mada/ai-video-production.git ~/.claude/skills/ai-video-production
```

`/ai-video-production` で呼び出せます。

### Codex

```bash
git clone https://github.com/atsu-mada/ai-video-production.git ~/.codex/skills/ai-video-production
```

`$ai-video-production` で呼び出せます。

### 必要なもの

- Python 3（3.14 で確認）。標準ライブラリのみ。

## 検証スクリプトの例

```bash
python3 scripts/validate_ai_video.py references .
python3 scripts/init_production_package.py path/to/project
python3 scripts/validate_ai_video.py package path/to/project
```

## 関連スキル

- [previz-maker](https://github.com/atsu-mada/previz-maker) — カメラと動線のブロックプレビズと参照プロンプト
- [seedance-studio](https://github.com/atsu-mada/seedance-studio) — Seedance 2.5 のプロンプト作成（Emily2040/seedance-2.0 の改変フォーク）

## 制限

- 計画とプロンプト作成のためのスキルです。画像・動画・音声の生成、プロバイダーへの投入、アップロードは行いません。
- プロバイダーのモデル名、尺の上限、料金は変わります。`references/profiles/generation-profiles.json` は目安です。実行時に各プロバイダーの最新情報を確認してください。
- 検証スクリプトは構造と記載内容を確認するもので、映像の品質や承認を保証しません。

## ライセンス

[MIT](LICENSE) © 2026 atsu_mada (ATSUFUMI KASHIMA)

---

## English

An agent skill for Claude Code and Codex that plans and validates AI film / music-video production packages: character, environment, object and VFX sheets, image-only and text storyboards, cut and scene prompts, and generation handoffs. Includes stdlib-only Python validators.

- Claude Code plugin: `/plugin marketplace add atsu-mada/ai-video-production`, then `/plugin install ai-video-production@atsu-mada-ai-video-production`.
- Manual: `git clone https://github.com/atsu-mada/ai-video-production.git ~/.claude/skills/ai-video-production` (or `~/.codex/skills/ai-video-production` for Codex).

Planning and prompt authoring only; it never generates, submits, or uploads media. License: MIT.
