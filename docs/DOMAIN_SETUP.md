# Connect filewink.me

The download website is published from `site/` in this repository. The same
deployment includes the signed feed under `apt/`. Installers remain in public
GitHub Releases; the application source repository stays private.

## Current setup, checked 28 October 2026

- `filewink.me` resolves to all four GitHub Pages IPv4 addresses below.
- `www.filewink.me` is currently a CNAME to `filewink.me`. Change it directly
  to `ayushxaw.github.io`; GitHub's domain check does not find it eligible for
  HTTPS in its current form.
- The custom domain is currently attached to **ayushxaw/ayushxaw.github.io**,
  not this repository. Its HTTPS enforcement is off.
- This project inherits that domain. GitHub reports its address as
  `http://filewink.me/filewink-downloads/`. The original github.io project URL
  redirects there.
- GitHub's health check reports an HTTPS certificate verification failure.
  A strict APT client refuses the HTTPS-to-HTTP redirect. Earlier successful
  APT installation checks predate this domain problem.

Do not add duplicate DNS records or reset working records just to follow a
generic setup tutorial. Check their current values first.

## Put the downloads site at the domain root

This is a coordinated GitHub Pages cutover, to perform while the owner is
available. It has deliberately not been performed as part of the website preview.

1. Verify ownership of `filewink.me` in the owning GitHub account's **Settings →
   Pages → Add a domain**. GitHub supplies a unique TXT host/value. In Namecheap,
   add that exact TXT record; retain it after verification. Do not guess the token.
2. In **ayushxaw/ayushxaw.github.io → Settings → Pages**, remove the `filewink.me`
   custom domain. This changes that account-level site; review it before removal.
3. Immediately set **filewink-downloads → Settings → Pages → Custom domain** to
   `filewink.me`. This project uses GitHub Actions: a repository `CNAME` file
   does not configure its custom domain.
4. Confirm the Namecheap records below. If Namecheap manages the domain's DNS,
   open **Domain List → Manage → Advanced DNS → Host Records**. If it uses other
   nameservers, edit records with that DNS provider instead.
5. Wait for GitHub's DNS check and HTTPS certificate to succeed, then enable
   **Enforce HTTPS**. Check both the main domain and `www` in a normal browser.

| Type | Host | Value | TTL |
| --- | --- | --- | --- |
| A | `@` | `185.199.108.153` | Automatic |
| A | `@` | `185.199.109.153` | Automatic |
| A | `@` | `185.199.110.153` | Automatic |
| A | `@` | `185.199.111.153` | Automatic |
| CNAME | `www` | `ayushxaw.github.io` | Automatic |

Remove conflicting parking/URL-redirect records for `@` or `www`, if present.
Keep email MX/TXT records and ownership verification records. Do not add wildcard
records. DNS propagation can take up to 24 hours; HTTPS issuance may lag behind it.

## Check compatibility before calling the cutover complete

- `https://filewink.me/` serves the actual download page with valid HTTPS.
- `https://www.filewink.me/` redirects to the same page.
- `https://filewink.me/apt/dists/ubuntu/InRelease` serves the unchanged signed feed.
- `https://ayushxaw.github.io/filewink-downloads/apt/dists/ubuntu/InRelease`
  follows HTTPS redirects to that same feed. Existing APT clients use this URL:
  do not change their installed source configurations just to match the website.
- A fresh Ubuntu test can install the APT setup package, run `apt update`, install
  Filewink, select an upgrade and remove it. Run the public workflow again after
  cutover to exercise the existing client configuration.
- Installer links work without GitHub sign-in. Private Windows preview links
  must never be used as public download buttons.

If a check fails, retain the recorded Pages settings, inspect DNS and certificate
status, and restore the previous custom-domain placement if needed. Avoid repeatedly
removing/re-adding the domain while a certificate is being issued. APT metadata,
public signing key and release assets must stay available throughout the move.

## References

- [GitHub: custom-domain inheritance](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages)
- [GitHub: configure a custom domain](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
- [GitHub: verify domain ownership](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages)
- [GitHub: HTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)
- [Namecheap: connect GitHub Pages](https://www.namecheap.com/support/knowledgebase/article.aspx/9645/2208/how-do-i-link-my-domain-to-github-pages/)
