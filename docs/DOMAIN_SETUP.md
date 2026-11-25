# Connect filewink.me

The download website is published from `site/` in this repository. The same
deployment includes the signed feed under `apt/`. Installers remain in public
GitHub Releases; the application source repository stays private.

## Current setup, checked 26 November 2026

`filewink.me` already serves the downloads site over HTTPS. The custom domain
and **Enforce HTTPS** are set in this repository’s Pages settings. The four
GitHub Pages A records are in place. The existing github.io APT URL redirects
over HTTPS to the signed feed on the main domain.

## Fix the www address in Namecheap

1. Open **Domain List → filewink.me → Manage → Advanced DNS → Host Records**.
2. Edit the existing **CNAME Record** with host `www`. Set **Value** to
   `ayushxaw.github.io` and **TTL** to **Automatic**, then save.
3. Once DNS and the certificate update, open `https://www.filewink.me/` in a
   browser. It should redirect to `https://filewink.me/` without a warning.

The current CNAME points to `filewink.me`, and the certificate does not cover
`www.filewink.me`. GitHub Pages expects the CNAME to point directly to the
account hostname and provides the redirect once DNS and the certificate are
ready. [GitHub Pages instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site#configuring-an-apex-domain-and-the-www-subdomain-variant)

## Verify the site and APT

- `https://filewink.me/` opens the download page with valid HTTPS.
- `https://www.filewink.me/` redirects to the same page with valid HTTPS.
- `https://filewink.me/apt/dists/ubuntu/InRelease` serves the signed feed.
- `https://ayushxaw.github.io/filewink-downloads/apt/dists/ubuntu/InRelease`
  reaches the same feed using only HTTPS.
- The downloads work in a browser signed out of GitHub. The publishing
  workflow also checks the live APT setup, install, upgrade and removal.

## References

- [GitHub: custom-domain inheritance](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages)
- [GitHub: configure a custom domain](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
- [GitHub: verify domain ownership](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages)
- [GitHub: HTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)
- [Namecheap: connect GitHub Pages](https://www.namecheap.com/support/knowledgebase/article.aspx/9645/2208/how-do-i-link-my-domain-to-github-pages/)
