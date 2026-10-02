---
name: ai-video-production
description: Plan and validate generic AI-video production packages and their reusable reference, storyboard, prompt, and generation-handoff deliverables. Use for preproduction organization and prompt authoring, not for directly generating or submitting media.
---

# AI Video Production

Use this skill as the generic preproduction router for an AI film or music-video project. It covers the production package and the reusable deliverables that feed it; provider execution skills remain responsible for rendering or submitting media.

## Choose one mode

- **Production package** — create or review the shared `00_common/`, scene, and manifest tree. Read [production-package.html](references/deliverables/production-package.html).
- **Character sheet** — lock one recurring human or creature identity. Read [character-sheet.html](references/deliverables/character-sheet.html).
- **Environment sheet** — lock one empty location, its geometry, materials, and lighting states. Read [environment-sheet.html](references/deliverables/environment-sheet.html).
- **Object sheet** — lock one independent prop or practical object. Read [object-sheet.html](references/deliverables/object-sheet.html).
- **VFX sheet** — lock one reusable effect or effect family on a black background. Read [vfx-sheet.html](references/deliverables/vfx-sheet.html).
- **Image-only storyboard** — block composition, direction, scale, and one action per panel with no production text. Read [storyboard.html](references/deliverables/storyboard.html).
- **Text storyboard** — pair the image storyboard with timing, framing/lens, and one camera instruction per panel. Read [text-storyboard.html](references/deliverables/text-storyboard.html).
- **Cut prompt** — compile one approved cut into an image, image-to-video, or video prompt. Read [cut-prompt.html](references/deliverables/cut-prompt.html).
- **Scene prompt** — compile a scene-level continuity and progression prompt from approved cuts. Read [scene-prompt.html](references/deliverables/scene-prompt.html).
- **Generation handoff** — package the suite operator (`Suite:`), provider, model, inputs, duration, output, and validation information for a separate execution skill. Read [generation-handoff.html](references/deliverables/generation-handoff.html).

## Shared rules

1. Inspect the existing project before creating or changing paths. Preserve older drafts and unrelated changes.
2. Put recurring, independently reusable assets in `00_common/`; keep one-off assets inside their scene. Keep each prompt beside its output or declared output path.
3. Use stable IDs, absolute timeline seconds, and relative project-root references. Keep image-only storyboards separate from text storyboards.
4. Keep identity, geometry, physical orientation, and continuity references explicit. Screens, photographs, and mirrors face the acting subject unless the scene gives a reason otherwise.
5. Separate a reusable object's construction from its scene-specific visible state. Use dedicated state references when a screen, page, reflection, control, opening, damage state, or emitted effect changes between cuts.
6. Keep production labels, captions, watermarks, and storyboard marks out of generated footage. Meaningful in-world writing and ordinary UI are allowed when the story requires them; define their exact state outside the storyboard.
7. Distinguish story scene, editorial cut, motion beat, and provider generation job. Preserve the story scene even when provider limits require several jobs.
8. A prompt or handoff does not authorize a generation job. Use the selected provider skill only after the user separately requests generation or submission. Paid steps also need previz visual approval and a quoted estimate ([approval gates](references/core/production-order.html#approval-gates)).

## Progressive references and validation

- Read [references/index.html](references/index.html) or [data/knowledge-map.json](data/knowledge-map.json) to select the canonical HTML reference.
- Read [references/core/continuity.html](references/core/continuity.html) for shared identity, orientation, and motion rules.
- Read [references/core/production-order.html](references/core/production-order.html) for package placement and production order.
- Read [references/core/validation.html](references/core/validation.html) for stopping conditions.
- Read [references/profiles/generation-profiles.json](references/profiles/generation-profiles.json) when a provider or model duration limit matters. Limits belong to the selected profile; do not assume one universal duration.
- Use `<verified-cpython-3.14> scripts/validate_ai_video.py <mode> <path>` for the selected deliverable. The existing `init_production_package.py` and `validate_production_package.py` remain compatible entry points for package workflows.

## Cross-cutting handoffs (optional)

- When audio timing changes, read [audio timing](references/core/audio-timing.html).
- When selecting takes or handing a version to an editor, read [editorial handoff](references/core/editorial-handoff.html). The optional selection validator checks records, not viewing or approval.
- When choosing or adding an execution suite, read [suite operators](references/core/suite-operators.html); new operators start from [the template](assets/templates/suite-operator-template.md).
- When preparing 16:9 / 1:1 / 9:16 deliverables or final QA, read [delivery variants](references/deliverables/delivery-variants.html). Join segments without audio drift with `<verified-cpython-3.14> scripts/concat_sync.py list.txt out_vNN.mp4 [--audio-bitrate 256k]`.
- When preparing titles, loglines, thumbnails, or post copy, read [presentation handoff](references/deliverables/presentation-handoff.html). This is optional supporting material, not another mandatory production mode.
