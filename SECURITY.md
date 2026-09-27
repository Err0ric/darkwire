# Security policy

## Reporting a vulnerability

Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** (private vulnerability reporting). Please do not open a public issue for a security problem.

Include what you found, where, and the steps to reproduce it. A proof of concept helps; keep it minimal and do not access or change data that is not yours.

## Scope

In scope:

- https://darkwire.tech (the web app)
- https://api.darkwire.tech (the API)
- The code in this repository

Out of scope:

- Rate-limit, load or denial-of-service testing
- The third-party feeds, status pages and enrichment APIs darkwire reads (news outlets, NVD, CISA, FIRST, vendor status pages); report those to their owners
- Hosting platform issues (Vercel, Railway) that are not caused by this project's configuration
- Reports from automated scanners with no demonstrated impact, and missing best-practice headers with no exploit

## Response

Best effort, usually within a week. You will get an acknowledgement, then an update when a fix ships. Credit in the fix commit if you want it.
