"""Phase 7 measurements that need nothing installed: what each installed package weighs
(the upper bound of a PyInstaller one-folder build, per edition) and what first run
downloads on each hardware tier.

    venv\\Scripts\\python tools\\measure_packaging.py
"""
import os
import sys
from importlib import metadata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# Only the GPU edition carries these: the CUDA libraries and the CUDA build of torch.
GPU_ONLY = {"nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12"}
# Development-only: never in a build.
DEV = {"pip", "ruff", "pytest", "pytest-qt", "pluggy", "iniconfig", "anthropic", "setuptools"}

MB = 1024 * 1024


def dist_size(dist) -> int:
    total = 0
    for f in dist.files or ():
        p = dist.locate_file(f)
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total


def torch_cuda_part(dist) -> int:
    """Bytes of torch's CUDA libraries (lib/*cu*.dll, cudnn, nccl ...)."""
    total = 0
    for f in dist.files or ():
        name = str(f).lower()
        if name.startswith("torch/lib/") and name.endswith(".dll") and any(
                k in name for k in ("cu", "nv", "cudnn", "nccl", "caffe2_nvrtc")):
            try:
                total += os.path.getsize(dist.locate_file(f))
            except OSError:
                pass
    return total


def main():
    rows = []
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        rows.append((dist_size(dist), name, dist.version, dist))
    rows.sort(reverse=True)
    gpu = cpu = 0
    torch_cuda = 0
    for size, name, _version, dist in rows:
        key = name.lower().replace("_", "-")
        if key in DEV:
            continue
        gpu += size
        if key not in GPU_ONLY:
            cpu += size
        if key == "torch":
            torch_cuda = torch_cuda_part(dist)
    cpu -= torch_cuda
    print("Largest installed packages (MB):")
    for size, name, version, _ in rows[:15]:
        print(f"  {size / MB:8.0f}  {name} {version}")
    print(f"\nPackages counted: {len(rows)}")
    print(f"torch CUDA DLLs inside torch: {torch_cuda / MB:.0f} MB")
    print(f"GPU edition, upper bound (all runtime packages): {gpu / MB:.0f} MB")
    print(f"CPU-light, upper bound (no nvidia-*, no torch CUDA DLLs): {cpu / MB:.0f} MB")

    from zeroflow import first_run
    import check_hardware
    print("\nFirst-run download per tier (default preset, built-in AI, Reader on):")
    for tier in check_hardware.TIERS:
        _, preset, _ = check_hardware.recommend({"gpus": [], "ram_gb": 16}, tier=tier)
        runtime = {"nvidia-desktop": "cuda", "nvidia-laptop": "cuda",
                   "amd-intel-gpu": "vulkan"}.get(tier, "cpu")
        items = first_run.downloads_for(preset, runtime, runtime_installed=False)
        total = sum(i.size for i in items)
        parts = ", ".join(f"{i.label} {i.size / MB:.0f}" for i in items)
        print(f"  {tier:15s} {total / MB / 1024:5.2f} GB  ({parts})")


if __name__ == "__main__":
    main()
