# musicgen-if-eval

A single-file **instruction-following evaluation workbench** for text-to-music models.

**[▶ Open the live workbench](https://hycccc.github.io/musicgen-if-eval/)** — no install, demo clips embedded.

Text-to-music prompts bundle many constraints at once — key, tempo, harmony, structure, instrumentation. A model can nail the vibe and still ignore half the instructions. Judging that properly means **decomposing the prompt into per-dimension requirements and judging each one separately**, with a musical explanation attached to every failure. This workbench implements that workflow end to end.

> Provenance: this is a public, from-scratch remake of a tool pattern I built and run in production for music-model evaluation. **No production data is included** — every demo clip here is synthesized by construction (see below).

## The methodology

1. **Requirement decomposition.** Each prompt becomes a checklist of dimensions (tempo / key / harmony in the demo; vocals, structure, instrumentation, language in the full pattern), each tagged with a difficulty tier — models fail "match the BPM" and "follow the chord progression" at very different rates, and scoring should know the difference.
2. **Per-dimension verdicts with musical basis.** Raters judge each requirement pass / partial / fail, and every non-pass demands a *musical* explanation ("progression lands on V in bar 4, spec asked for I — cadence broken"), not just a score. That's what makes reports actionable for model iteration.
3. **Heuristics as guardrails, not gold.** The workbench runs onset-autocorrelation tempo estimation (±2 BPM on the demo set) and Krumhansl-profile key estimation to anchor the rater. The key estimator is deliberately labeled experimental: chord loops share their pitch-class set with the relative key, an ambiguity the profile alone can't resolve — a small live demonstration of why automated music metrics stay guardrails while humans stay the gold standard.
4. **Pipeline-ready output.** One click exports all verdicts as JSONL, one row per item with requirements, per-dimension verdicts, musical basis, and overall result.

## Demo items are ground-truthed by construction

`tools/make_demo_audio.py` synthesizes every clip from a musical spec (key, mode, roman-numeral progression, BPM), so each clip's ground truth is known exactly. Three clips honor their prompt; three contain **controlled violations**:

| Item | Prompt asks for | Audio actually is | Expected verdict |
|---|---|---|---|
| if-001 | C major, I–V–vi–IV, 120 BPM | exactly that | pass |
| if-002 | C major, I–V–vi–IV, 120 BPM | rendered at **92 BPM** | tempo fail |
| if-003 | A minor, i–VI–III–VII, 100 BPM | exactly that | pass |
| if-004 | G major, I–IV–V–I, 112 BPM | rendered **a semitone up (A♭)** | key fail |
| if-005 | D major, I–IV–V–I, 110 BPM | rendered **I–V–vi–IV** | harmony fail |
| if-006 | E minor, i–VII–VI–VII, 140 BPM | exactly that | pass |

Regenerate with:

```bash
python3 tools/make_demo_audio.py --embed   # requires numpy + ffmpeg
```

## Run it

Open `index.html` in any browser (or use the live link above). Everything is self-contained: audio embedded as data URIs, verdicts persisted to localStorage, no server, no dependencies.

## License

MIT
