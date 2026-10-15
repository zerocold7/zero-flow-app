r"""Install the built-in AI's runtime (llama.cpp's llama-server) for this PC.

    venv\Scripts\python.exe tools\get_llama.py              the build this PC needs
    venv\Scripts\python.exe tools\get_llama.py --variant cpu
    venv\Scripts\python.exe tools\get_llama.py --from D:\downloads   reuse archives already downloaded

Downloads the pinned llama.cpp release from GitHub (github.com/ggml-org/llama.cpp),
checks every archive against its published SHA-256, and unpacks it into
runtime/llama/<build>/. Sizes: cuda 625 MB, vulkan 31 MB, cpu 19 MB. The AI model
itself (Gemma 4 E4B, 5.15 GB) downloads the first time the engine starts.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow.llm import llama_runtime as rt  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--variant", choices=["auto", *rt.ARCHIVES], default="auto")
    parser.add_argument("--from", dest="from_dir", help="folder holding archives already downloaded")
    args = parser.parse_args()
    variant = rt.chosen_variant() if args.variant == "auto" else args.variant
    print(f"llama.cpp {rt.BUILD}, {variant} build")
    if rt.installed(variant):
        print(f"already installed: {rt.variant_dir(variant)}")
        return 0
    try:
        folder = rt.install(variant, args.from_dir)
    except (rt.RuntimeInstallError, OSError) as e:
        print(f"not installed: {e}")
        return 1
    print(f"installed: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
