# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/shivangsaxena1011/breathewise-ai/security/advisories/new)
rather than a public issue. You should get a reply within a few days.

## How BreatheWise protects users

| Area | Measure |
| --- | --- |
| Input | Every request body is a Pydantic model with strict bounds (lengths, ranges, enums, list sizes). Coordinates, text and history are capped. |
| Abuse | Per-IP sliding-window rate limits, with a tighter budget for AI endpoints. Client IPs come from platform headers that callers cannot forge. |
| Prompt injection | User text is JSON-quoted inside `USER_DATA` tags and kept out of the trusted `CONTEXT` block. The system prompt tells the model to treat it as data. |
| Uploads | Photos are capped at 4 MB, their type is checked from magic bytes (not the client's `Content-Type`), they are analysed in memory and never stored. |
| Privacy | No accounts and no personal data. Report coordinates are rounded to about 100 m. One-person-one-vote uses an HMAC of the IP with a secret key, so IPs are never stored. Household profiles stay in the browser's `localStorage`. |
| Community text | Links and markup are rejected, whitespace is normalised, and reports expire after 30 days. |
| Headers | Strict CSP (`script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`), HSTS, `X-Content-Type-Options`, `X-Frame-Options`, COOP/CORP, `Referrer-Policy` and a minimal `Permissions-Policy`, set both by the API and by `vercel.json`. |
| Errors | Upstream and storage failures return generic messages, never stack traces or keys. Gemini errors are logged without request content or credentials. |
| Secrets | Keys are read from environment variables only and hidden from `repr()`. `.env*` files are git-ignored. |
| Static files | The SPA fallback resolves paths and refuses anything outside the build directory. |
| Supply chain | Dependencies are pinned. CI runs `pip-audit`, `npm audit`, ruff's bandit (`S`) rules and CodeQL. Dependabot opens weekly update PRs. |
| Container | The Docker image runs as a non-root user. |
