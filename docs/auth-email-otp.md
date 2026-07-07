# Email OTP Authentication with Email Allowlist

## Overview

HAS uses passwordless **Email OTP authentication**: staff sign in by entering a
one-time 6-digit verification code sent to their email. Access is restricted by
an **admin-managed allowlist** — only pre-approved email addresses can ever
receive a code. Successful verification establishes a **server-side session**
referenced by an HttpOnly cookie.

> This replaced the earlier magic-link design: instead of clicking an emailed
> link, the user returns to the login page and types the code. The allowlist,
> session, rate-limiting and audit infrastructure are shared.

## Login flow (two steps)

```
User                     Frontend                Backend                    Email
 |  enter email            |                        |                         |
 |------------------------>| POST /auth/request-otp |                         |
 |                         |----------------------->| 1 allowlist check       |
 |                         |                        | 2 rate-limit check      |
 |                         |                        | 3 generate 6-digit OTP  |
 |                         |                        |   (store SHA-256 hash,  |
 |                         |                        |    salted with email)   |
 |                         |                        |------------------------>| code
 |  generic message        |<-- 200 (always same) --|                         |
 |                         |                        |                         |
 |  read code in inbox     |                        |                         |
 |  type code on step 2    |                        |                         |
 |------------------------>| POST /auth/verify-otp  |                         |
 |                         |  {email, code}         |                         |
 |                         |----------------------->| 4 latest unused code    |
 |                         |                        | 5 check expiry +        |
 |                         |                        |   attempt counter       |
 |                         |                        | 6 hash-compare code     |
 |                         |                        | 7 mark code USED        |
 |                         |                        | 8 create session row    |
 |                         |<- Set-Cookie (HttpOnly)|                         |
 |  redirected by role     |                        |                         |
```

1. **Allowlist check** — the email must exist in `allowed_email` and be
   `enabled`. Otherwise nothing is sent; the API still returns the same generic
   message, so an attacker cannot probe which emails are registered.
2. **Rate limiting** — max 3 code requests per email and 10 per IP within a
   15-minute window. Excess requests are silently dropped (and audited).
3. **OTP generation** — `secrets.randbelow(10**6)` formatted to 6 digits.
   Only its **SHA-256 hash, salted with the email** is stored
   (`login_token.token_hash`), with a **10-minute expiry**.
4. **Latest-code rule** — only the most recent unused code for an email is
   accepted; requesting a new code implicitly invalidates older ones.
5. **Attempt limiting** — each wrong entry increments `login_token.attempts`;
   after 5 failures the code is locked (HTTP 429) even if the correct code is
   subsequently entered. The user must request a fresh code.
6. **Hash comparison** — the submitted code is salted+hashed and compared.
7. **Single use** — `used_at` is set in the same transaction; the code cannot
   be redeemed twice. First successful login stamps
   `allowed_email.verified_at` (email ownership proven).
8. **Session** — a long random value goes into the `has_session` cookie
   (**HttpOnly, SameSite=Lax, Secure in production**); the database stores only
   its hash in `user_session` with a 7-day expiry. Sessions are server-side, so
   disabling or removing an email **revokes its sessions immediately**.

The frontend proxies `/api/*` through the Next.js server to the FastAPI
backend, so the cookie is first-party (no cross-origin cookie issues).

## Data model

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `allowed_email` | admin-managed allowlist | email (unique), role, enabled, added_by, added_at, verified_at |
| `login_token` | one-time OTP codes | token_hash (unique), email, expires_at, used_at, **attempts**, request_ip |
| `user_session` | server-side sessions | token_hash (unique), email, role, expires_at, revoked_at |
| `auth_log` | audit trail | event, email, ip, detail, created_at |

Roles: `admin`, `interviewer`, `lecturer`, `supervisor`, `user`.
`admin` unlocks management endpoints; other roles are "staff" who manage only
their own interview slots (identity derived from the session).

## API routes

| Route | Access | Purpose |
|-------|--------|---------|
| `POST /api/auth/request-otp` | public | request a code (generic response) |
| `POST /api/auth/verify-otp` | public | {email, code} → session cookie |
| `GET /api/auth/me` | session | current session info |
| `POST /api/auth/logout` | session | revoke session, clear cookie |
| `GET/POST /api/auth/allowlist` | admin | list / add allowed emails |
| `PATCH/DELETE /api/auth/allowlist/{id}` | admin | enable/disable/re-role / remove (revokes sessions) |

## Security measures checklist

- [x] No code sent to emails outside the allowlist
- [x] Uniform generic response — no user enumeration
- [x] OTP stored **hashed** (SHA-256, email-salted), never plain text
- [x] 10-minute expiry (configurable via `OTP_TTL_MINUTES`, within 5–10 spec)
- [x] Single-use — code invalidated in the same transaction as login
- [x] Verification attempts limited (5 per code, then HTTP 429 lock)
- [x] Requesting a new code invalidates previous codes
- [x] Rate limiting per email (3/15min) and per IP (10/15min), silent + audited
- [x] Server-side sessions, hashed cookie value, revocable at any time
- [x] Cookie: HttpOnly + SameSite=Lax (+ `COOKIE_SECURE=true` under HTTPS)
- [x] Disabling/removing an allowlist entry revokes live sessions immediately
- [x] Full audit log: otp_requested / otp_denied / otp_rate_limited /
      otp_invalid / otp_locked / login_success / logout / allowlist changes
- [x] Admin cannot remove themselves from the allowlist (lockout guard)
- [x] Bootstrap: first admin seeded from `ADMIN_EMAIL` env at startup

> Development aid: with `DEBUG_EXPOSE_OTP=true` the request-otp response
> includes the code directly (used by automated tests). **Off by default;
> must never be enabled in production.**

## Configuration (env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ADMIN_EMAIL` | — | seeded into allowlist as admin at startup |
| `OTP_TTL_MINUTES` | 10 | code validity |
| `OTP_MAX_ATTEMPTS` | 5 | wrong entries before a code locks |
| `SESSION_TTL_DAYS` | 7 | session validity |
| `COOKIE_SECURE` | false | set true behind HTTPS |
| `DEBUG_EXPOSE_OTP` | false | dev only — echo code in API response |
