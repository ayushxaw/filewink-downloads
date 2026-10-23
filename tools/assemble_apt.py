#!/usr/bin/env python3
"""Assemble a verified public APT site without putting installers in Git.

Requires Python 3.12+, curl, gpg and gpgv. Only the public download repository's
release assets may be fetched. Signing happens separately; this tool never
imports or needs a private key.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

PACKAGE_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]*\Z")
SAFE_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
VERSION = re.compile(r"[0-9][A-Za-z0-9.+:~\-]*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FINGERPRINT = re.compile(r"[0-9A-Fa-f]{40}\Z")
PUBLIC_REPO = "/ayushxaw/filewink-downloads/releases/download/"
INDEX_PATH = "main/binary-amd64/Packages"


def fail(message):
    raise ValueError(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("Duplicate JSON field: " + key)
        result[key] = value
    return result


def safe_relative(value):
    if not isinstance(value, str):
        fail("A repository filename must be text.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or not path.parts
        or any(
            part in {".", ".."} or not SAFE_PART.fullmatch(part) for part in path.parts
        )
    ):
        fail("Unsafe repository filename: " + repr(value))
    return path


def require_regular(path):
    if path.is_symlink() or not path.is_file():
        fail("Expected a regular file: " + str(path))
    for parent in path.parents:
        if parent.is_symlink():
            fail("Repository paths must not contain symlinks: " + str(parent))
    return path


def read_file(root, relative):
    path = root.joinpath(*safe_relative(relative).parts)
    return require_regular(path).read_bytes()


def load_manifest(source):
    manifest = json.loads(
        read_file(source, "manifest.json"), object_pairs_hook=no_duplicate_keys
    )
    if not isinstance(manifest, dict) or type(manifest.get("schema")) is not int:
        fail("The repository manifest needs schema 1.")
    if manifest["schema"] != 1:
        fail("Unsupported repository manifest schema.")
    fingerprint = manifest.get("fingerprint", "")
    if not isinstance(fingerprint, str) or not FINGERPRINT.fullmatch(fingerprint):
        fail("The manifest needs a full 40-digit signing-key fingerprint.")
    for field, expected in (
        ("suite", "ubuntu"),
        ("component", "main"),
        ("architecture", "amd64"),
    ):
        if manifest.get(field) != expected:
            fail("Unexpected repository " + field + ".")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        fail("The manifest must list its packages.")
    seen = set()
    paths = set()
    for package in packages:
        if not isinstance(package, dict):
            fail("Invalid package manifest entry.")
        for field, pattern in (
            ("name", PACKAGE_NAME),
            ("version", VERSION),
            ("sha256", SHA256),
        ):
            value = package.get(field)
            if not isinstance(value, str) or not pattern.fullmatch(value):
                fail("Invalid package " + field + ".")
        if package["name"] not in {"filewink", "filewink-archive-keyring"}:
            fail("The public feed may only contain Filewink packages.")
        size = package.get("size")
        if type(size) is not int or size <= 0:
            fail("Package sizes must be positive byte counts.")
        filename = safe_relative(package.get("filename"))
        if filename.parts[0] != "pool" or filename.suffix != ".deb":
            fail("Installers must use relative pool/*.deb filenames.")
        identity = package["name"], package["version"]
        if identity in seen or str(filename) in paths:
            fail("Duplicate package or installer filename in the manifest.")
        seen.add(identity)
        paths.add(str(filename))
        url = package.get("source_url")
        if not isinstance(url, str):
            fail("A package needs its public release URL.")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith(PUBLIC_REPO)
        ):
            fail("Only HTTPS assets from the public Filewink releases are allowed.")
        tail = parsed.path[len(PUBLIC_REPO) :].split("/")
        if (
            len(tail) != 2
            or any(not SAFE_PART.fullmatch(part) for part in tail)
            or tail[1] != filename.name
        ):
            fail("The release URL must point to the named installer asset.")
    manifest["fingerprint"] = fingerprint.upper()
    return manifest


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + " failed: " + result.stderr.strip())
    return result.stdout


def verify_signatures(source, fingerprint):
    for name in ("gpg", "gpgv"):
        if not shutil.which(name):
            raise RuntimeError("Install " + name + " before assembling the repository.")
    public_key = read_file(source, "filewink.asc")
    if not public_key.startswith(b"-----BEGIN PGP PUBLIC KEY BLOCK-----"):
        fail("The repository must contain an armored public key.")
    if b"PRIVATE KEY" in public_key or b"SECRET KEY" in public_key:
        fail("Private signing keys must never enter the public repository.")
    for relative in (
        "dists/ubuntu/InRelease",
        "dists/ubuntu/Release",
        "dists/ubuntu/Release.gpg",
    ):
        require_regular(source / relative)
    with tempfile.TemporaryDirectory(prefix="filewink-apt-verify-") as name:
        home = Path(name)
        home.chmod(0o700)
        listing = run(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(home),
                "--batch",
                "--with-colons",
                "--fingerprint",
                "--show-keys",
                str(source / "filewink.asc"),
            ]
        )
        primary = []
        waiting = False
        for line in listing.splitlines():
            fields = line.split(":")
            if fields[0] in {"sec", "ssb"}:
                fail("A private key was supplied instead of a public key.")
            if fields[0] == "pub":
                waiting = True
            elif fields[0] == "fpr" and waiting:
                primary.append(fields[9].upper())
                waiting = False
        if primary != [fingerprint]:
            fail("The public signing-key fingerprint does not match the manifest.")
        keyring = home / "repository.gpg"
        run(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(home),
                "--batch",
                "--yes",
                "--output",
                str(keyring),
                "--dearmor",
                str(source / "filewink.asc"),
            ]
        )
        cleartext = home / "verified-release"
        options = ["gpgv", "--homedir", str(home), "--keyring", str(keyring)]
        run(
            options
            + ["--output", str(cleartext), str(source / "dists/ubuntu/InRelease")]
        )
        release = read_file(source, "dists/ubuntu/Release")
        if cleartext.read_bytes() != release:
            fail(
                "InRelease and the detached Release do not contain identical metadata."
            )
        run(
            options
            + [
                str(source / "dists/ubuntu/Release.gpg"),
                str(source / "dists/ubuntu/Release"),
            ]
        )
    return release


def parse_stanzas(data):
    result = []
    stanza = {}
    previous = None
    for line in data.decode("utf-8").splitlines() + [""]:
        if not line:
            if stanza:
                result.append(stanza)
            stanza, previous = {}, None
        elif line[0].isspace():
            if previous is None:
                fail("Unexpected continuation in repository metadata.")
            stanza[previous] += "\n" + line[1:]
        else:
            key, separator, value = line.partition(":")
            if (
                not separator
                or not re.fullmatch(r"[A-Za-z0-9-]+", key)
                or key in stanza
            ):
                fail("Malformed or duplicate repository metadata field.")
            stanza[key] = value.lstrip()
            previous = key
    return result


def verify_metadata(source, manifest, release):
    stanzas = parse_stanzas(release)
    if len(stanzas) != 1:
        fail("Release must contain one metadata stanza.")
    fields = stanzas[0]
    if fields.get("Suite", fields.get("Codename")) != manifest["suite"]:
        fail("Release uses a different suite from the manifest.")
    if fields.get("Components", "").split() != ["main"]:
        fail("Release uses unexpected components.")
    architectures = fields.get("Architectures", "").split()
    if set(architectures) not in ({"amd64"}, {"amd64", "all"}) or len(
        architectures
    ) != len(set(architectures)):
        fail("Release uses unexpected architectures.")
    expected = {INDEX_PATH, INDEX_PATH + ".gz"}
    for field, algorithm in (
        ("SHA256", "sha256"),
        ("SHA512", "sha512"),
        ("SHA1", "sha1"),
        ("MD5Sum", "md5"),
    ):
        if field not in fields:
            if field == "SHA256":
                fail("Release must authenticate its indexes with SHA256.")
            continue
        found = set()
        for line in fields[field].splitlines():
            if not line.strip():
                continue
            pieces = line.split()
            if len(pieces) != 3:
                fail("Malformed Release checksum entry.")
            digest, size, filename = pieces
            safe_relative(filename)
            if filename not in expected or filename in found:
                fail("Release contains an unexpected or repeated index.")
            data = read_file(source, "dists/ubuntu/" + filename)
            if not size.isdecimal() or int(size) != len(data):
                fail("Release index size does not match: " + filename)
            if hashlib.new(algorithm, data).hexdigest() != digest:
                fail("Release index checksum does not match: " + filename)
            found.add(filename)
        if found != expected:
            fail("Release does not authenticate every required index.")
    packages = read_file(source, "dists/ubuntu/" + INDEX_PATH)
    if (
        gzip.decompress(read_file(source, "dists/ubuntu/" + INDEX_PATH + ".gz"))
        != packages
    ):
        fail("Compressed and plain package indexes do not match.")
    entries = parse_stanzas(packages)
    expected_packages = {
        (item["name"], item["version"]): item for item in manifest["packages"]
    }
    observed = set()
    for entry in entries:
        identity = entry.get("Package"), entry.get("Version")
        if identity not in expected_packages or identity in observed:
            fail("Packages and the manifest list different package versions.")
        item = expected_packages[identity]
        for field, expected_value in (
            ("Filename", item["filename"]),
            ("SHA256", item["sha256"]),
            ("Size", str(item["size"])),
        ):
            if entry.get(field) != expected_value:
                fail("Packages disagrees with the manifest about " + field + ".")
        if entry.get("Architecture") not in {"amd64", "all"}:
            fail("Packages contains an unsupported architecture.")
        observed.add(identity)
    if observed != set(expected_packages):
        fail("The package index is missing a manifest entry.")


def verify_source_config(source):
    stanzas = parse_stanzas(read_file(source, "filewink.sources"))
    if len(stanzas) != 1:
        fail("The public source configuration must contain one repository.")
    expected = {
        "Types": "deb",
        "URIs": "https://ayushxaw.github.io/filewink-downloads/apt",
        "Suites": "ubuntu",
        "Components": "main",
        "Architectures": "amd64",
        "Signed-By": "/usr/share/keyrings/filewink-archive-keyring.asc",
    }
    fields = stanzas[0]
    fields["URIs"] = fields.get("URIs", "").rstrip("/")
    if any(fields.get(field) != value for field, value in expected.items()):
        fail(
            "The source configuration must use the public feed and its scoped signing key."
        )
    if set(fields) - set(expected):
        fail("The public source configuration contains unexpected options.")


def download_asset(package, destination):
    if not shutil.which("curl"):
        raise RuntimeError("Install curl before assembling the repository.")
    run(
        [
            "curl",
            "--disable",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--proto",
            "=https",
            "--proto-redir",
            "=https",
            "--connect-timeout",
            "30",
            "--max-time",
            "600",
            "--max-filesize",
            str(package["size"]),
            "--output",
            str(destination),
            "--",
            package["source_url"],
        ]
    )


def assemble(source, output, *, fingerprint=None):
    source = Path(os.path.abspath(source))
    output = Path(os.path.abspath(output))
    if output.exists() or output.is_symlink():
        fail("The output path already exists; choose a new deployment directory.")
    if output == source or source in output.parents:
        fail("The deployment directory must be outside the source metadata.")
    for parent in (output.parent, *output.parents):
        if parent.is_symlink():
            fail("The deployment destination must not contain symlinks.")
    if not output.parent.is_dir():
        fail("The deployment destination's parent directory must already exist.")
    manifest = load_manifest(source)
    if fingerprint is not None and fingerprint.upper() != manifest["fingerprint"]:
        fail("The manifest does not match the separately pinned fingerprint.")
    release = verify_signatures(source, manifest["fingerprint"])
    verify_metadata(source, manifest, release)
    verify_source_config(source)
    metadata = [
        "manifest.json",
        "filewink.asc",
        "filewink.sources",
        "dists/ubuntu/Release",
        "dists/ubuntu/InRelease",
        "dists/ubuntu/Release.gpg",
        "dists/ubuntu/" + INDEX_PATH,
        "dists/ubuntu/" + INDEX_PATH + ".gz",
    ]
    if (source / "index.html").exists():
        metadata.append("index.html")
    # Validate every committed input before any network request.
    contents = {relative: read_file(source, relative) for relative in metadata}
    with tempfile.TemporaryDirectory(
        prefix=".filewink-apt-site-", dir=output.parent
    ) as name:
        stage = Path(name) / "site"
        apt = stage / "apt"
        for relative, data in contents.items():
            path = apt / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for package in manifest["packages"]:
            path = apt / package["filename"]
            path.parent.mkdir(parents=True, exist_ok=True)
            download_asset(package, path)
            require_regular(path)
            if path.stat().st_size != package["size"]:
                fail("Downloaded installer size does not match: " + package["filename"])
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != package["sha256"]:
                fail(
                    "Downloaded installer checksum does not match: "
                    + package["filename"]
                )
        (stage / ".nojekyll").write_text("", encoding="utf-8")
        # rename avoids publishing a partial directory; an existing output is never replaced.
        if output.exists() or output.is_symlink():
            fail("The output path appeared while assembling the deployment.")
        stage.rename(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1] / "apt"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fingerprint", help="Optional independent pin for the repository key"
    )
    args = parser.parse_args()
    try:
        destination = assemble(args.source, args.output, fingerprint=args.fingerprint)
    except (ValueError, RuntimeError, OSError, EOFError) as error:
        parser.exit(1, "APT deployment refused: " + str(error) + "\n")
    print("Verified APT site assembled at " + str(destination))


if __name__ == "__main__":
    main()
