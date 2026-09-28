---
name: <service>[-chrome]-<action>-<role>
description: Operate <Service> through <MCP | API | CLI | Chrome UI> to execute reviewed AI-video generation handoffs whose Suite field names this skill. Quote cost and wait for explicit user approval before any paid step.
---

# <Service> Operator

Suite operator for <Service>. It follows the suite-operator contract defined by the `ai-video-production` skill (`references/core/suite-operators.html`). Preproduction skills stay suite-neutral; this skill owns every <Service>-specific tool name, model identifier, price, and UI step.

Naming: `<service>[-chrome]-<action>-<role>`. Use `-chrome` only for browser-UI operation, omit `<action>` for a whole-suite operator, and pick `<role>` from operator, publisher, generator, or maker.

## Shared client contract

- Accept one reviewed generation handoff whose `Suite:` equals this skill's name. If it names another suite, stop and route.
- A handoff never authorizes a run. Quote cost, wait for the user's explicit OK, then submit.
- Report provider state, technical QC, and perceptual review as separate evidence states.
- Never regenerate a queued or running job. Search existing results before re-running or re-upscaling.
- Save every output to a new versioned path; never overwrite an accepted version.
- Keep internal identifiers, credentials, balances, share URLs, and account handles out of user-facing text and out of this skill.
- Record every limit and price as "observed YYYY-MM"; verify live at execution time.

## 1. Access path

- Access: <MCP server | REST API | CLI | Chrome UI>.
- Authentication owner: <user signs in | token stored by the user's tooling>. The agent never enters credentials.
- The agent may: <list of calls or clicks>.
- The agent must not: <e.g. purchase credits, change account settings, publish, delete>.

## 2. Models & modes

| Model | Modes (T2V / I2V / R2V / first-last frame / extend) | Audio | Notes |
|---|---|---|---|
| <model> | <modes> | <yes/no> | <exclusive combinations> |

## 3. References

- Accepted types: <image | video | audio | character>.
- Count limits: <n images, n videos, n audio>.
- Tagging syntax: <e.g. @Image N>.
- Minimum lengths or sizes: <e.g. audio at least N s>.
- Exclusive combinations: <e.g. boundary frames cannot be combined with general references>.

## 4. Limits

- Durations: <min-max per job> (observed YYYY-MM).
- Resolutions and aspect ratios: <list>.
- Concurrency: <jobs in parallel; separate post-processing limits>.
- Upload limits: <file size, formats>.

## 5. Cost estimation

- Estimate with: <tool or pricing page>.
- Known gaps: <e.g. actual charge above estimate when a video reference is attached>.
- Gate: present the quote, wait for the user's OK, then run.

## 6. Moderation & failure

- What a block looks like: <status and message>.
- Charged when blocked: <yes/no, observed YYYY-MM>.
- Procedure: one plain retry, then a reworded prompt that replaces contact or destruction verbs with gentle metaphors; stop after <n> failures and report.

## 7. Post-processing

| Mode | Suits | Avoid for | Observed cost |
|---|---|---|---|
| <mode> | <content> | <content> | <relative cost, YYYY-MM> |

## 8. Retrieval

- Wait: <polling or long-poll procedure; never regenerate while waiting>.
- Register or download: <required steps before saving>.
- Naming: `<cut-or-job-id>_v<NN>.<ext>`; bump the version for every new output and verify with ffprobe.

## 9. Approval gates

- Previz must be visually approved by the user before any paid generation.
- Every paid step (generation, upscale, extend, retake) needs a quoted estimate and the user's explicit OK.
- Approval for one job does not extend to later jobs.
