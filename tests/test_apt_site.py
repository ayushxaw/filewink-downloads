"""Exercise the public feed trust boundary using a disposable signing key."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "tools/assemble_apt.py"
SPEC = importlib.util.spec_from_file_location("assemble_apt", MODULE)
assembler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assembler)


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "GnuPG is required")
class AptSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing_directory = tempfile.TemporaryDirectory(
            prefix="filewink-test-signing-"
        )
        cls.home = Path(cls.signing_directory.name)
        cls.home.chmod(0o700)
        cls.gpg(
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-generate-key",
            "Disposable Filewink test key",
            "rsa2048",
            "sign",
            "1d",
        )
        listing = cls.gpg("--with-colons", "--list-keys").stdout.decode()
        cls.fingerprint = next(
            line.split(":")[9]
            for line in listing.splitlines()
            if line.startswith("fpr:")
        )
        cls.public_key = cls.gpg("--armor", "--export", cls.fingerprint).stdout

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["gpgconf", "--homedir", str(cls.home), "--kill", "gpg-agent"],
            capture_output=True,
            check=False,
        )
        cls.signing_directory.cleanup()

    @classmethod
    def gpg(cls, *arguments):
        return subprocess.run(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.home),
                "--batch",
                "--yes",
                *arguments,
            ],
            capture_output=True,
            check=True,
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="filewink-test-apt-site-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "apt"
        self.index = self.source / "dists/ubuntu/main/binary-amd64"
        self.index.mkdir(parents=True)
        self.output = self.root / "site"
        self.payload = b"An installer downloaded from a public release.\n"
        digest = hashlib.sha256(self.payload).hexdigest()
        self.package = {
            "name": "filewink",
            "version": "0.5.4~beta1",
            "filename": "pool/main/f/filewink/filewink-0.5.4-beta1-ubuntu-amd64.deb",
            "sha256": digest,
            "size": len(self.payload),
            "source_url": "https://github.com/ayushxaw/filewink-downloads/releases/download/"
            "v0.5.4-beta.1/filewink-0.5.4-beta1-ubuntu-amd64.deb",
        }
        self.manifest = {
            "schema": 1,
            "fingerprint": self.fingerprint,
            "suite": "ubuntu",
            "component": "main",
            "architecture": "amd64",
            "packages": [self.package],
        }
        self.write_manifest()
        (self.source / "filewink.asc").write_bytes(self.public_key)
        (self.source / "filewink.sources").write_text(
            "Types: deb\nURIs: https://ayushxaw.github.io/filewink-downloads/apt\n"
            "Suites: ubuntu\nComponents: main\nArchitectures: amd64\n"
            "Signed-By: /usr/share/keyrings/filewink-archive-keyring.asc\n"
        )
        (self.source / "index.html").write_text("<p>Install Filewink with apt.</p>\n")
        self.write_index()
        self.sign_release()

    def write_manifest(self):
        (self.source / "manifest.json").write_text(json.dumps(self.manifest))

    def write_index(self):
        package = self.package
        text = (
            "Package: filewink\nVersion: 0.5.4~beta1\nArchitecture: amd64\n"
            f"Filename: {package['filename']}\nSize: {package['size']}\n"
            f"SHA256: {package['sha256']}\nDescription: Local file tools\n\n"
        )
        data = text.encode()
        (self.index / "Packages").write_bytes(data)
        (self.index / "Packages.gz").write_bytes(gzip.compress(data, mtime=0))

    def sign_release(self):
        lines = [
            "Origin: Filewink",
            "Label: Filewink",
            "Suite: ubuntu",
            "Codename: ubuntu",
            "Architectures: amd64",
            "Components: main",
        ]
        for field, algorithm in (("SHA256", "sha256"), ("SHA512", "sha512")):
            lines.append(field + ":")
            for name in ("Packages", "Packages.gz"):
                data = (self.index / name).read_bytes()
                digest = hashlib.new(algorithm, data).hexdigest()
                lines.append(f" {digest} {len(data)} main/binary-amd64/{name}")
        release = self.source / "dists/ubuntu/Release"
        release.write_text("\n".join(lines) + "\n")
        self.gpg(
            "--digest-algo",
            "SHA256",
            "--output",
            str(release.parent / "InRelease"),
            "--clearsign",
            str(release),
        )
        self.gpg(
            "--digest-algo",
            "SHA256",
            "--output",
            str(release.parent / "Release.gpg"),
            "--detach-sign",
            str(release),
        )

    def download(self, package, destination):
        destination.write_bytes(self.payload)

    def assemble(self, *, downloader=None, **options):
        with patch.object(
            assembler, "download_asset", side_effect=downloader or self.download
        ) as download:
            result = assembler.assemble(self.source, self.output, **options)
        return result, download

    def refused_before_download(self):
        with patch.object(assembler, "download_asset") as download:
            with self.assertRaises((ValueError, RuntimeError)):
                assembler.assemble(self.source, self.output)
            download.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_signed_feed_and_checked_installer_produce_a_site(self):
        result, download = self.assemble(fingerprint=self.fingerprint)
        self.assertEqual(result, self.output)
        self.assertEqual(
            (result / "apt" / self.package["filename"]).read_bytes(), self.payload
        )
        self.assertEqual((result / "apt/filewink.asc").read_bytes(), self.public_key)
        self.assertTrue((result / "apt/index.html").is_file())
        self.assertTrue((result / ".nojekyll").is_file())
        self.assertEqual(download.call_count, 1)
        self.assertFalse(list(result.rglob("*.key")))

    def test_installer_hash_failure_leaves_no_deployment(self):
        def corrupt(package, destination):
            destination.write_bytes(b"!" * len(self.payload))

        with self.assertRaisesRegex(ValueError, "checksum"):
            self.assemble(downloader=corrupt)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".filewink-apt-site-*")), [])

    def test_homepage_does_not_change_signed_feed(self):
        website = self.root / "homepage"
        (website / "assets").mkdir(parents=True)
        (website / "index.html").write_text('<a href="apt/">APT</a>')
        (website / "assets/logo.svg").write_text("<svg></svg>")
        result, _ = self.assemble(website=website)
        self.assertEqual((result / "index.html").read_bytes(), (website / "index.html").read_bytes())
        self.assertTrue((result / "assets/logo.svg").is_file())
        for relative in ("dists/ubuntu/InRelease", "dists/ubuntu/Release", "dists/ubuntu/Release.gpg", "dists/ubuntu/main/binary-amd64/Packages", "dists/ubuntu/main/binary-amd64/Packages.gz", "filewink.asc", "filewink.sources", "manifest.json", "index.html"):
            self.assertEqual((result / "apt" / relative).read_bytes(), (self.source / relative).read_bytes())
        self.assertEqual((result / "apt" / self.package["filename"]).read_bytes(), self.payload)

    def test_homepage_cannot_override_apt_before_download(self):
        website = self.root / "homepage"
        (website / "apt").mkdir(parents=True)
        (website / "index.html").write_text("Home")
        (website / "apt/InRelease").write_text("Replaced metadata")
        with self.assertRaisesRegex(ValueError, "must not replace"):
            self.assemble(website=website)
        self.assertFalse(self.output.exists())

    def test_homepage_rejects_linked_private_files(self):
        website = self.root / "homepage"
        website.mkdir()
        (website / "index.html").write_text("Home")
        (website / "notes.txt").symlink_to(self.source / "manifest.json")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.assemble(website=website)
        self.assertFalse(self.output.exists())

    def test_homepage_reserved_paths_are_rejected_even_when_empty(self):
        website = self.root / "homepage"
        website.mkdir()
        (website / "index.html").write_text("Home")
        for name in ("apt", "CNAME"):
            with self.subTest(name=name):
                reserved = website / name
                reserved.mkdir()
                with patch.object(assembler, "download_asset") as download:
                    with self.assertRaisesRegex(ValueError, "must not replace"):
                        assembler.assemble(self.source, self.output, website=website)
                download.assert_not_called()
                reserved.rmdir()
        self.assertFalse(self.output.exists())

    def test_homepage_cannot_set_the_custom_domain(self):
        website = self.root / "homepage"
        website.mkdir()
        (website / "index.html").write_text("Home")
        (website / "CNAME").write_text("unexpected.example")
        with patch.object(assembler, "download_asset") as download:
            with self.assertRaisesRegex(ValueError, "domain settings"):
                assembler.assemble(self.source, self.output, website=website)
        download.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_homepage_needs_a_homepage(self):
        website = self.root / "homepage"
        website.mkdir()
        (website / "style.css").write_text("body {}")
        with self.assertRaisesRegex(ValueError, "index.html"):
            self.assemble(website=website)
        self.assertFalse(self.output.exists())

    def test_installer_size_failure_leaves_no_deployment(self):
        def truncated(package, destination):
            destination.write_bytes(self.payload[:-1])

        with self.assertRaisesRegex(ValueError, "size"):
            self.assemble(downloader=truncated)
        self.assertFalse(self.output.exists())

    def test_path_traversal_is_rejected_before_network(self):
        self.package["filename"] = "pool/../../outside.deb"
        self.write_manifest()
        self.refused_before_download()

    def test_absolute_package_urls_are_rejected_before_network(self):
        self.package["filename"] = self.package["source_url"]
        self.write_manifest()
        self.refused_before_download()

    def test_private_or_unrelated_release_urls_are_rejected(self):
        self.package["source_url"] = self.package["source_url"].replace(
            "/filewink-downloads/", "/filewink/"
        )
        self.write_manifest()
        self.refused_before_download()

    def test_unsigned_changed_package_index_is_rejected(self):
        (self.index / "Packages").write_bytes(b"Package: other\n")
        self.refused_before_download()

    def test_signed_index_and_manifest_disagreement_is_rejected(self):
        self.package["sha256"] = "0" * 64
        self.write_manifest()
        self.refused_before_download()

    def test_unlisted_signed_package_is_rejected(self):
        path = self.index / "Packages"
        data = (
            path.read_bytes()
            + b"Package: unexpected\nVersion: 1\nArchitecture: amd64\n\n"
        )
        path.write_bytes(data)
        (self.index / "Packages.gz").write_bytes(gzip.compress(data, mtime=0))
        self.sign_release()
        self.refused_before_download()

    def test_broken_clear_signature_is_rejected(self):
        path = self.source / "dists/ubuntu/InRelease"
        path.write_bytes(
            path.read_bytes().replace(b"Origin: Filewink", b"Origin: Tampered")
        )
        self.refused_before_download()

    def test_broken_detached_signature_is_rejected(self):
        (self.source / "dists/ubuntu/Release.gpg").write_bytes(b"not a signature")
        self.refused_before_download()

    def test_fingerprint_change_is_rejected(self):
        self.manifest["fingerprint"] = "0" * 40
        self.write_manifest()
        self.refused_before_download()

    def test_independently_pinned_fingerprint_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "separately pinned"):
            self.assemble(fingerprint="0" * 40)
        self.assertFalse(self.output.exists())

    def test_symlink_metadata_is_rejected(self):
        path = self.source / "filewink.sources"
        original = self.root / "external.sources"
        path.rename(original)
        path.symlink_to(original)
        self.refused_before_download()

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        marker = self.output / "owned-file"
        marker.write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.assemble()
        self.assertEqual(marker.read_text(), "keep")

    def test_symlink_output_is_rejected_without_touching_target(self):
        target = self.root / "other"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.assemble()
        self.assertEqual(list(target.iterdir()), [])

    def test_duplicate_json_fields_are_rejected(self):
        path = self.source / "manifest.json"
        path.write_text(
            path.read_text().replace('"schema": 1', '"schema": 1, "schema": 1')
        )
        self.refused_before_download()

    def test_source_configuration_cannot_disable_signature_checks(self):
        path = self.source / "filewink.sources"
        path.write_text(path.read_text() + "Trusted: yes\n")
        self.refused_before_download()

    def test_source_configuration_must_use_the_installed_keyring(self):
        path = self.source / "filewink.sources"
        path.write_text(
            path.read_text().replace("filewink-archive-keyring.asc", "other.asc")
        )
        self.refused_before_download()


if __name__ == "__main__":
    unittest.main()
