# Filewink

Small file actions, with a full editor when you need it.

Convert photos, edit PDF pages, trim and join videos, and read text from images.
File processing stays on your computer. No account, uploads or ads.

**[Download the Ubuntu beta](https://github.com/ayushxaw/filewink-downloads/releases/download/v0.5.4-beta.1/filewink-0.5.4-beta1-ubuntu-amd64.deb)** · [Release notes and checksums](https://github.com/ayushxaw/filewink-downloads/releases/tag/v0.5.4-beta.1)

For **Ubuntu 24.04 on 64-bit Intel/AMD computers**. This is an early beta.
The current beta1 can crash during video playback on a minimal Ubuntu 26.04
installation; a replacement package is being checked. Use Ubuntu 24.04 for
this download. Other distributions, older Ubuntu releases and ARM are not
supported yet.

![Filewink action wheel](images/action-wheel.png)

## Install with APT

**APT updates are temporarily unavailable while the custom domain's HTTPS
setup is repaired.** Use the direct `.deb` installation below for now. Existing
packages and signed metadata are retained. Keep signature and HTTPS checks
enabled; an HTTP redirect is not a reason to disable them.

Download the [APT setup package](https://github.com/ayushxaw/filewink-downloads/releases/download/apt-setup-1/filewink-archive-keyring_2026.10.23.1_all.deb),
open a terminal in its folder, and run:

```bash
sudo apt install ./filewink-archive-keyring_2026.10.23.1_all.deb
sudo apt update
sudo apt install filewink
```

The small setup package adds a public signing key and a source scoped to
Filewink. Future published versions arrive through normal APT upgrades.
[Repository details](https://ayushxaw.github.io/filewink-downloads/apt/) ·
[Setup checksums](https://github.com/ayushxaw/filewink-downloads/releases/tag/apt-setup-1)

Installation, upgrade selection, thirteen packaged output checks and removal
passed on Ubuntu 24.04 in the [earlier public verification run](https://github.com/ayushxaw/filewink-downloads/actions/runs/39938333880).
That result predates the domain issue above and does not establish current feed
availability.

To disable this update source while keeping the app:

```bash
sudo apt purge filewink-archive-keyring
```

### Direct install

You can also download the app `.deb`, open a terminal in its folder, and run:

```bash
sudo apt install ./filewink-0.5.4-beta1-ubuntu-amd64.deb
```

Apt installs the required Ubuntu libraries and conversion tools. LibreOffice
components install with normal apt recommendations. Internet is needed for
missing packages. You do not need to install Python packages or clone a repo.

Open Filewink from Applications, or choose **Open With → Filewink** on a file.
The small wheel opens quick actions; **Open full app** opens the larger editors.

For **Shift+hold** and **Shift+Space** in GNOME Files, choose **Enable Files
gestures** in Filewink settings, then close and reopen Files. The right-click
provider also loads when Files restarts. Desktop icons and other file managers
can use Open With; the hold gesture is specific to GNOME Files.

## Everyday tools

- Photos: JPEG, PNG, WebP, AVIF and more; crop, resize, rotate and annotate.
- PDFs: merge, split, reorder, remove and rotate pages; compress, password
  protect, extract pictures, and export text, documents or page images.
- Videos: trim the beginning, end or middle; join kept clips; compress and export.
- Text: offline OCR with a review step before copying or saving the result.

PDF-to-document conversion can change layout. PDF-to-PowerPoint creates image
slides. OCR can make mistakes. Keep your original signed PDFs. HEIC, PDF text
editing and a multitrack video timeline are not included.

![Filewink photo editor](images/photo-editor.png)

## Remove

If you enabled user gestures, remove them before removing the app:

```bash
filewink-integrate --uninstall
sudo apt remove filewink
sudo apt purge filewink-archive-keyring  # if you enabled APT updates
```

Quit Filewink first. Your originals, generated files and settings are kept.

## Windows

Windows is in development. The native build, installer and Explorer gestures
are being tested; there is no finished Windows download in this release.

## About this repository

This is the public download and issue tracker. The Filewink application
repository stays private. The releases contain the app installer, checksums,
installation notes, and matching third-party dependency sources. Those sources
are for Qt/PySide/FFmpeg and do not contain Filewink's private application source.
The application and dependencies retain their individual licences, included in
the installed app under **About → Third-party licences**.

Found a bug? [Open an issue](https://github.com/ayushxaw/filewink-downloads/issues)
with your Ubuntu version, what you tried and what happened. Leave private files
and passwords out of public reports.

Made by Ayush Awasthi. Filewink is free to use. A voluntary support link will be
added when it is ready.
