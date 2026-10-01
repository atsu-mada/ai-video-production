# ai-video-production

English · [日本語](README.ja.md)

An agent skill that builds and validates the **pre-generation** stage of AI films and music videos. Works with Claude Code and Codex.

Author: atsu_mada (ATSUFUMI KASHIMA) / GitHub [@atsu-mada](https://github.com/atsu-mada)

## What it does

- Creates and reviews production packages (`00_common/`, scenes, cut manifests)
- Character, environment, prop, and VFX sheets
- Storyboards (image-only and with text)
- Cut prompts and scene prompts
- Generation handoffs (provider, model, inputs, duration, outputs, and checks, packaged for another skill to execute)
- A suite-operator contract (the nine headings, naming rules, and template shared by execution skills such as Magnific, TapNow, and Higgsfield)
- 16:9 / 1:1 / 9:16 delivery variants, delivery QA, and a concatenation script that avoids audio drift (`scripts/concat_sync.py`)
- Python validation scripts that use only the standard library

## Install

### Claude Code (plugin)

```
/plugin marketplace add atsu-mada/ai-video-production
/plugin install ai-video-production@atsu-mada-ai-video-production
```

Invoke with `/ai-video-production:ai-video-production`.

### Claude Code (manual)

```bash
git clone https://github.com/atsu-mada/ai-video-production.git ~/.claude/skills/ai-video-production
```

Invoke with `/ai-video-production`.

### Codex

```bash
git clone https://github.com/atsu-mada/ai-video-production.git ~/.codex/skills/ai-video-production
```

Invoke with `$ai-video-production`.

### Requirements

- Python 3 (tested on 3.14). Standard library only.

## Validation script examples

```bash
python3 scripts/validate_ai_video.py references .
python3 scripts/init_production_package.py path/to/project
python3 scripts/validate_ai_video.py package path/to/project
```

## Related skills

- [previz-maker](https://github.com/atsu-mada/previz-maker) — block previz for camera and blocking, plus a reference prompt
- [seedance-studio](https://github.com/atsu-mada/seedance-studio) — Seedance 2.5 prompt authoring (a modified fork of Emily2040/seedance-2.0)

## Limitations

- This skill is for planning and prompt authoring. It does not generate images, video, or audio, submit jobs to providers, or upload anything.
- Provider model names, duration limits, and pricing change. `references/profiles/generation-profiles.json` is a guide only; check each provider's current information at run time.
- The validation scripts check structure and required content. They do not guarantee visual quality or approval.

## License

[MIT](LICENSE) © 2026 atsu_mada (ATSUFUMI KASHIMA)
