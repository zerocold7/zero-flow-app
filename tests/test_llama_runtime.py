"""The built-in AI's runtime: llama.cpp's llama-server, one build per kind of PC,
installed from pinned, checksum-verified archives. Nothing here downloads: the
archives are small fakes made in a temporary folder."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow.llm import llama_runtime as rt


def make_zip(folder, name, files):
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, "w") as z:
        for inner, data in files.items():
            z.writestr(inner, data)
    with open(path, "rb") as f:
        return path, hashlib.sha256(f.read()).hexdigest()


class RuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "downloads")
        os.makedirs(self.downloads)
        patcher = mock.patch.object(rt, "RUNTIME_DIR", os.path.join(self.tmp, "runtime"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_build(self, variant, files=None, wrong_hash=False):
        """Replace `variant`'s pinned archive with a fake one in self.downloads."""
        name = f"fake-{variant}.zip"
        _, digest = make_zip(self.downloads, name,
                             files or {"llama-server.exe": b"MZ fake", "ggml.dll": b"dll"})
        pinned = {variant: [(name, "0" * 64 if wrong_hash else digest)]}
        patcher = mock.patch.dict(rt.ARCHIVES, pinned)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestInstall(RuntimeTestCase):
    def test_an_archive_with_the_pinned_checksum_is_installed(self):
        self.fake_build("cpu")
        self.assertFalse(rt.installed("cpu"))
        rt.install("cpu", from_dir=self.downloads)
        self.assertTrue(rt.installed("cpu"))
        self.assertTrue(os.path.exists(rt.server_path("cpu")))

    def test_a_wrong_checksum_is_refused_and_nothing_installed(self):
        """A file that is not the one pinned is never unpacked."""
        self.fake_build("cpu", wrong_hash=True)
        with self.assertRaises(rt.RuntimeInstallError):
            rt.install("cpu", from_dir=self.downloads)
        self.assertFalse(rt.installed("cpu"))
        self.assertFalse(os.path.exists(rt.variant_dir("cpu")))

    def test_an_archive_that_writes_outside_its_folder_is_refused(self):
        self.fake_build("cpu", files={"llama-server.exe": b"MZ", "../escaped.txt": b"x"})
        with self.assertRaises(rt.RuntimeInstallError):
            rt.install("cpu", from_dir=self.downloads)
        self.assertFalse(os.path.exists(os.path.join(rt.RUNTIME_DIR, "escaped.txt")))
        self.assertFalse(rt.installed("cpu"))

    def test_an_archive_without_the_server_is_refused(self):
        self.fake_build("cpu", files={"readme.txt": b"no server here"})
        with self.assertRaises(rt.RuntimeInstallError):
            rt.install("cpu", from_dir=self.downloads)
        self.assertFalse(rt.installed("cpu"))


class TestVariants(unittest.TestCase):
    def test_every_variant_is_pinned_by_checksum(self):
        for variant in ("cuda", "vulkan", "cpu"):
            for name, digest in rt.ARCHIVES[variant]:
                self.assertIn(rt.BUILD, name) if name.startswith("llama-") else None
                self.assertRegex(digest, r"^[0-9a-f]{64}$", name)

    def test_the_build_follows_the_graphics_card(self):
        """Same classification as check_hardware.py: built-in graphics do not count."""
        cases = [
            (["NVIDIA GeForce RTX 4070"], "cuda"),
            (["Intel(R) UHD Graphics 620", "NVIDIA GeForce RTX 3050 Laptop GPU"], "cuda"),
            (["AMD Radeon RX 7600"], "vulkan"),
            (["Intel(R) Arc(TM) A750 Graphics"], "vulkan"),
            (["AMD Radeon(TM) Graphics"], "cpu"),          # built into a Ryzen
            (["Intel(R) UHD Graphics 620"], "cpu"),
            ([], "cpu"),
        ]
        for names, expected in cases:
            self.assertEqual(rt.pick_variant(names), expected, names)

    def test_a_setting_overrides_the_choice(self):
        with mock.patch.object(rt, "LLAMA_VARIANT", "cpu"):
            self.assertEqual(rt.chosen_variant(), "cpu")


if __name__ == "__main__":
    unittest.main()
