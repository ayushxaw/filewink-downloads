#!/usr/bin/env python3
"""Exercise an assembled Filewink site with real APT in disposable local state.

Nothing is installed. Only loopback HTTP is used, and the host's APT sources,
trusted keys, package database, lists and caches are never read or changed.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def run(command, *, environment=None, cwd=None, timeout=120):
    return subprocess.run(
        command,
        env=environment,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def require_success(result, description):
    if result.returncode:
        raise RuntimeError(
            description
            + " failed:\n"
            + result.stdout.strip()
            + "\n"
            + result.stderr.strip()
        )


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_arguments):
        pass


@contextmanager
def serve(site):
    handler = functools.partial(QuietHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.1}
    )
    worker.daemon = True
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/apt/"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        if worker.is_alive():
            raise RuntimeError("The temporary APT HTTP server did not stop.")


def quote_config(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def apt_environment(directory, site, uri):
    directory.mkdir()
    for path in (
        "etc/sources.list.d",
        "etc/apt.conf.d",
        "etc/trusted.gpg.d",
        "state/lists/partial",
        "cache/archives/partial",
        "log",
        "downloads",
    ):
        (directory / path).mkdir(parents=True, exist_ok=True)
    (directory / "state/status").write_text("")
    (directory / "etc/apt.conf").write_text("")
    (directory / "etc/sources.list").write_text("")
    public_key = directory / "filewink.asc"
    shutil.copyfile(site / "apt/filewink.asc", public_key)
    if any(character.isspace() for character in str(public_key)):
        raise ValueError(
            "Use a temporary-directory location without whitespace for Signed-By."
        )
    (directory / "etc/sources.list.d/filewink.sources").write_text(
        "Types: deb\n"
        f"URIs: {uri}\n"
        "Suites: ubuntu\n"
        "Components: main\n"
        "Architectures: amd64\n"
        f"Signed-By: {public_key}\n"
    )
    # APT_CONFIG is loaded before the normal configuration directories. Point
    # those directories at this sandbox so no host hooks, proxies or sources run.
    config = directory / "apt.conf"
    config.write_text(
        f"Dir {quote_config(directory)};\n"
        'Dir::Etc "etc";\n'
        'Dir::Etc::main "apt.conf";\n'
        'Dir::Etc::parts "apt.conf.d";\n'
        'Dir::Etc::sourcelist "sources.list";\n'
        'Dir::Etc::sourceparts "sources.list.d";\n'
        'Dir::Etc::trusted "trusted.gpg";\n'
        'Dir::Etc::trustedparts "trusted.gpg.d";\n'
        'Dir::State "state";\n'
        'Dir::State::status "status";\n'
        'Dir::State::lists "lists";\n'
        'Dir::Cache "cache";\n'
        'Dir::Cache::archives "archives";\n'
        'Dir::Log "log";\n'
        'APT::Architecture "amd64";\n'
        'APT::Architectures { "amd64"; };\n'
        'APT::Get::List-Cleanup "false";\n'
        'APT::Get::AllowUnauthenticated "false";\n'
        'Acquire::AllowInsecureRepositories "false";\n'
        'Acquire::AllowDowngradeToInsecureRepositories "false";\n'
        'Acquire::Languages "none";\n'
        'Acquire::Retries "0";\n'
        'Acquire::http::Timeout "30";\n'
        'Acquire::http::Proxy "DIRECT";\n'
        'Acquire::https::Proxy "DIRECT";\n'
    )
    environment = dict(os.environ, APT_CONFIG=str(config), LC_ALL="C")
    for variable in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        environment.pop(variable, None)
    return environment


def expected_app(site):
    manifest = json.loads((site / "apt/manifest.json").read_text())
    candidates = [item for item in manifest["packages"] if item["name"] == "filewink"]
    if not candidates:
        raise ValueError("The assembled manifest contains no Filewink package.")
    latest = candidates[0]
    for candidate in candidates[1:]:
        comparison = run(
            [
                "dpkg",
                "--compare-versions",
                candidate["version"],
                "gt",
                latest["version"],
            ],
            timeout=10,
        )
        if comparison.returncode not in {0, 1}:
            raise ValueError("The manifest contains an invalid Debian version.")
        if comparison.returncode == 0:
            latest = candidate
    if not re.fullmatch(r"[0-9a-f]{64}", latest["sha256"]):
        raise ValueError("The package manifest needs a lowercase SHA-256 checksum.")
    return latest


def signed_client_check(site, directory, expected):
    with serve(site) as uri:
        environment = apt_environment(directory, site, uri)
        update = run(["apt-get", "update", "--error-on=any"], environment=environment)
        require_success(update, "Signed APT update")
        policy = run(["apt-cache", "policy", "filewink"], environment=environment)
        require_success(policy, "APT candidate lookup")
        match = re.search(r"^\s*Candidate:\s*(\S+)\s*$", policy.stdout, re.MULTILINE)
        if match is None or match[1] != expected["version"]:
            raise RuntimeError(
                "APT selected an unexpected Filewink candidate:\n" + policy.stdout
            )
        downloads = directory / "downloads"
        download = run(
            ["apt-get", "download", "filewink=" + expected["version"]],
            environment=environment,
            cwd=downloads,
            timeout=180,
        )
        require_success(download, "Authenticated package download")
        packages = list(downloads.glob("*.deb"))
        if len(packages) != 1:
            raise RuntimeError("APT did not download exactly one package.")
        package = packages[0]
        checksum = hashlib.sha256()
        with package.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(block)
        if (
            package.stat().st_size != expected["size"]
            or checksum.hexdigest() != expected["sha256"]
        ):
            raise RuntimeError(
                "APT's downloaded package disagrees with the release manifest."
            )
        return {"candidate": match[1], "sha256": checksum.hexdigest()}


def copy_site(source, destination):
    # Link large installers when possible. Tampering replaces individual metadata
    # files atomically, so the original assembled site is never modified.
    def link_or_copy(original, target):
        if Path(original).is_symlink():
            raise ValueError("The assembled site must not contain symlinks.")
        try:
            os.link(original, target)
        except OSError:
            shutil.copy2(original, target)

    shutil.copytree(source, destination, copy_function=link_or_copy)


def replace_bytes(path, content):
    temporary = path.with_name(path.name + ".client-test-tmp")
    with temporary.open("xb") as handle:
        handle.write(content)
    temporary.replace(path)


def rejected_update(site, directory, *, signature):
    with serve(site) as uri:
        environment = apt_environment(directory, site, uri)
        result = run(["apt-get", "update", "--error-on=any"], environment=environment)
    combined = result.stdout + "\n" + result.stderr
    if result.returncode == 0:
        raise RuntimeError("APT accepted tampered repository metadata:\n" + combined)
    if signature:
        recognized = re.search(
            r"BADSIG|invalid signature|signatures? (?:were |are )?invalid|"
            r"signature verification failed|OpenPGP signature.*failed|"
            r"signature could not be verified|not signed",
            combined,
            re.IGNORECASE,
        )
    else:
        recognized = re.search(r"Hash Sum mismatch", combined, re.IGNORECASE)
    if recognized is None:
        raise RuntimeError(
            "APT failed for an unexpected reason during tamper checking:\n" + combined
        )


def check(site):
    if os.geteuid() == 0:
        raise RuntimeError("Run this integration check as an unprivileged user.")
    for executable in ("apt-get", "apt-cache", "dpkg"):
        if shutil.which(executable) is None:
            raise RuntimeError("Install the required command: " + executable)
    site = Path(site).resolve()
    expected = expected_app(site)
    if not (site / "apt/filewink.asc").is_file():
        raise ValueError("The assembled site is missing its public signing key.")
    with tempfile.TemporaryDirectory(prefix="filewink-apt-client-") as name:
        temporary = Path(name)
        verified = signed_client_check(site, temporary / "good-client", expected)

        bad_signature = temporary / "bad-signature-site"
        copy_site(site, bad_signature)
        inrelease = bad_signature / "apt/dists/ubuntu/InRelease"
        original = inrelease.read_bytes()
        modified = original.replace(
            b"Origin: Filewink\n", b"Origin: Tampered Filewink\n", 1
        )
        if original == modified:
            raise ValueError("The signed Release is missing its expected Origin field.")
        replace_bytes(inrelease, modified)
        rejected_update(bad_signature, temporary / "signature-client", signature=True)

        bad_index = temporary / "bad-index-site"
        copy_site(site, bad_index)
        packages = bad_index / "apt/dists/ubuntu/main/binary-amd64/Packages"
        original = packages.read_bytes()
        modified = original.replace(b"Package: filewink", b"Package: Filewink", 1)
        if modified == original:
            raise ValueError("The package index does not contain the Filewink package.")
        replace_bytes(packages, modified)
        compressed = packages.with_name("Packages.gz")
        modified_compressed = bytearray(compressed.read_bytes())
        if len(modified_compressed) < 18:
            raise ValueError("The compressed package index is unexpectedly short.")
        # Keep the signed file size unchanged, so APT must check its hash rather
        # than rejecting only a length mismatch. Both served index variants are
        # corrupted; there is no untouched compressed fallback to accept.
        modified_compressed[-8] ^= 1
        replace_bytes(compressed, modified_compressed)
        rejected_update(bad_index, temporary / "index-client", signature=False)
    return {
        "signed_update": "passed",
        "download": verified,
        "tampered_signature": "rejected",
        "tampered_packages": "rejected",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", type=Path, required=True, help="Assembled site containing apt/"
    )
    args = parser.parse_args()
    try:
        report = check(args.site)
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(1, "APT client check failed: " + str(error) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
