"""One model download for the first-run wizard, as a child process it can stop at once
(zeroflow.first_run.real_fetch). The request is one JSON argument: repo, revision,
patterns, cache_dir. huggingface_hub reads HF_HOME from the environment the wizard sets.

    python -m zeroflow.fetch '{"repo": "...", "revision": "...", "patterns": [...], "cache_dir": "..."}'
"""
import json
import sys


def main() -> int:
    request = json.loads(sys.argv[1])
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import logging as hf_logging
    hf_logging.set_verbosity_error()
    snapshot_download(request["repo"], revision=request["revision"],
                      allow_patterns=request["patterns"], cache_dir=request["cache_dir"])
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:                         # the last line is what the wizard shows
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        code = 1
    raise SystemExit(code)
