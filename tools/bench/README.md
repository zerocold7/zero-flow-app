# tools/bench — measuring before keeping

Every speed or accuracy change to the engine is measured here first, on the same clips
before and after. Results go to `results/` and clips to `clips/` and `mine/` — all
git-ignored.

| Script | What it does |
|---|---|
| `make_clips.py` | Makes 132 synthetic test cases: 12 English sentences (Kokoro) and 12 Arabic (espeak-ng), each **clean**, followed by **4 s of room noise**, a **breath** or **typing**, and spoken **quietly** — plus clips with **no speech** (silence, hum, clicks, quiet and loud noise). Same output every run. |
| `bench_stt.py` | Runs the engine's own transcription (`zeroflow.stt.transcribe_audio`) over a clip folder and scores character errors, end punctuation, **invented words**, and time. `--compare A B` puts two runs side by side; `--model` tries another Whisper model; `--no-filter` turns the invented-ending filter off. |
| `bench_llm.py` | For each AI context size: graphics memory, load time, Polish speed, and the answers. Needs Ollama. |
| `record_mine.py` | Records **your own voice** reading the benchmark's sentences, plus two clips with no words — into `mine/`, on this PC only. |

```powershell
.\venv\Scripts\python.exe tools\bench\make_clips.py
.\venv\Scripts\python.exe tools\bench\bench_stt.py --label before --runs 2
#   ... change the engine ...
.\venv\Scripts\python.exe tools\bench\bench_stt.py --label after --runs 2
.\venv\Scripts\python.exe tools\bench\bench_stt.py --compare before after
```

**What synthetic clips can and cannot show.** They prove a change does no harm, and
they compare models and speeds fairly. They do **not** reproduce invented endings
("Thank you." after the last word): those depend on a real room, microphone and
breath. For that, record yourself and compare the filter off and on:

```powershell
.\venv\Scripts\python.exe tools\bench\record_mine.py
.\venv\Scripts\python.exe tools\bench\bench_stt.py --clips mine --label mine-off --no-filter --runs 3
.\venv\Scripts\python.exe tools\bench\bench_stt.py --clips mine --label mine-on --runs 3
.\venv\Scripts\python.exe tools\bench\bench_stt.py --compare mine-off mine-on
```

The Arabic synthetic voice is robotic, so Arabic error rates here are far above what a
person gets; compare them only with each other.
