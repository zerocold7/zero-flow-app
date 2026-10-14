"""AI-model benchmark: graphics memory, load time and Polish speed per Ollama setting.

    venv\\Scripts\\python.exe tools\\bench\\bench_llm.py                 (default + 4096 + 8192)
    venv\\Scripts\\python.exe tools\\bench\\bench_llm.py --ctx 8192 16384

For each setting the model is unloaded, loaded fresh with that context size, and asked
to Polish the same English and Arabic sentences with the engine's own prompts. Prints
memory (total and on the graphics card), load time, and per-request time, plus the
first answer per language so a quality change is visible. Needs Ollama running.
"""
import argparse
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("ZEROFLOW_LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "results", "logs"))
os.makedirs(os.environ["ZEROFLOW_LOG_DIR"], exist_ok=True)

import flow_core  # noqa: E402
import personas  # noqa: E402

BASE = flow_core.OLLAMA_HOST_URL.rsplit("/api/", 1)[0]
SAMPLES = [
    ("en", personas.STANDARD_SYSTEM_PROMPT,
     "so um I wanted to say that the the meeting tomorrow is at ten and everyone should "
     "like bring the the budget numbers"),
    ("en", personas.STANDARD_SYSTEM_PROMPT,
     "please send the updated report to the team before friday afternoon and tell them "
     "the docker container is fixed"),
    ("ar", personas.ARABIC_POLISH_PROMPT,
     "يعني انا كنت ابغى اقول انو الاجتماع بكره الساعه عشره و لازم الكل يجي عشان نناقش الميزانيه"),
    ("ar", personas.ARABIC_POLISH_PROMPT,
     "طيب اممم ارسل التقرير للفريق قبل يوم الجمعه و قلهم ان المشكله انحلت"),
]


def prompt(instruction, text):
    return f"{instruction}\n\nInput Raw String: {text}\nOutput String:"


def unload(model):
    requests.post(f"{BASE}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    deadline = time.time() + 30
    while time.time() < deadline and any(m["name"] == model for m in loaded()):
        time.sleep(0.3)


def loaded():
    return requests.get(f"{BASE}/api/ps", timeout=5).json().get("models", [])


def measure(model, ctx, repeat):
    options = {"temperature": 0.2}
    if ctx:
        options["num_ctx"] = ctx
    unload(model)
    started = time.perf_counter()
    requests.post(f"{BASE}/api/generate", json={"model": model, "keep_alive": "5m",
                                                "options": options}, timeout=300)
    load_s = time.perf_counter() - started
    info = next(m for m in loaded() if m["name"] == model)
    times, answers = [], {}
    for _ in range(repeat):
        for lang, instruction, text in SAMPLES:
            started = time.perf_counter()
            reply = requests.post(f"{BASE}/api/generate", json={
                "model": model, "prompt": prompt(instruction, text), "stream": False,
                "options": options, "think": False, "keep_alive": "5m"}, timeout=300).json()
            times.append(time.perf_counter() - started)
            answers.setdefault(lang, reply.get("response", "").strip())
    after = next(m for m in loaded() if m["name"] == model)
    return {"ctx": ctx or "model default", "size": info["size"], "vram": info["size_vram"],
            "context": after.get("context_length"), "load": load_s,
            "reloaded": after.get("expires_at") is None, "times": times, "answers": answers}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ctx", type=int, nargs="*", default=[4096, 8192])
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    model = flow_core.get_ollama_model()
    print(f"model: {model}   Ollama: {requests.get(BASE + '/api/version').json()['version']}")
    for ctx in [None] + args.ctx:
        r = measure(model, ctx, args.repeat)
        t = sorted(r["times"])
        print(f"\nnum_ctx {r['ctx']}:  memory {r['size'] / 2**30:.2f} GB "
              f"({r['vram'] / 2**30:.2f} GB on the graphics card), context {r['context']}, "
              f"load {r['load']:.1f} s")
        print(f"  Polish: median {t[len(t) // 2]:.2f} s, slowest {t[-1]:.2f} s over {len(t)} requests")
        for lang, answer in r["answers"].items():
            print(f"  {lang}: {answer[:110]}")
    unload(model)
    print("\n(model unloaded; the engine loads it again at its next start)")


if __name__ == "__main__":
    main()
