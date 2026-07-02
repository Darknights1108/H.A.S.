# Magic Link Authentication with Email Allowlist

## Overview

HAS uses passwordless **magic-link authentication**: staff sign in by clicking a
one-time link sent to their email. Access is restricted by an **admin-managed
allowlist** — only pre-approved email addresses can ever receive a login link.
Successful login establishes a **server-side session** referenced by an
HttpOnly cookie.

This document describes the flow, data model, and security measures.

## Login flow

```
User                     Frontend                Backend                    Email
 |  enter email            |                        |                         |
 |------------------------>| POST /auth/request-link|                         |
 |                         |----------------------->| 1 allowlist check       |
 |                         |                        | 2 rate-limit check      |
 |                         |                        | 3 create one-time token |
 |                         |                        |   (store SHA-256 hash)  |
 |                         |                        |------------------------>| magic link
 |  generic message        |<-- 200 (always same) --|                         |
 |                         |                        |                         |
 |  click link in inbox    |                        |                         |
 |------------------------>| /auth/verify?token=... |                         |
 |                         | POST /auth/verify      |                         |
 |                         |----------------------->| 4 hash & look up token  |
 |                         |                        | 5 check expiry/used/    |
 |                         |                        |   allowlist still on    |
 |                         |                        | 6 mark token USED       |
 |                         |                        | 7 mark email verified   |
 |                         |                        | 8 create session row    |
 |                         |<- Set-Cookie (HttpOnly)|                         |
 |  redirected by role     |                        |                         |
```

1. **Allowlist check** — the email must exist in `allowed_email` and be
   `enabled`. Otherwise nothing is sent; the API still returns the same generic
   message ("Please check your email. If this email is allowed, a login link
   will be sent."), so an attacker cannot probe which emails are registered.
2. **Rate limiting** — max 3 link requests per email and 10 per IP within a
   15-minute window. Excess requests are silently dropped (and audited).
3. **Token generation** — `secrets.token_urlsafe(48)` (~64 random chars).
   Only its **SHA-256 hash** is stored (`login_token.token_hash`), with a
   **15-minute expiry**. A database leak therefore exposes no usable tokens.
4-5. **Verification** — the presented token is hashed and looked up; it must be
   unexpired, never used, and its email must still be enabled in the allowlist.
6. **Single use** — `used_at` is set in the same transaction; a second click on
   the same link fails with 401.
7. **Email ownership proof** — first successful login stamps
   `allowed_email.verified_at`.
8. **Session** — a new random value goes into the `has_session` cookie
   (**HttpOnly, SameSite=Lax, Secure in production**); the database stores only
   its hash in `user_session` with a 7-day expiry. Sessions are server-side, so
   disabling or removing an email **revokes its sessions immediately**.

The frontend proxies `/api/*` through the Next.js server to the FastAPI
backend, so the cookie is first-party (no cross-origin cookie issues).

## Data model

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `allowed_email` | admin-managed allowlist | email (unique), role, enabled, added_by, added_at, verified_at |
| `login_token` | one-time magic-link tokens | token_hash (unique), email, expires_at, used_at, request_ip |
| `user_session` | server-side sessions | token_hash (unique), email, role, expires_at, revoked_at |
| `auth_log` | audit trail | event, email, ip, detail, created_at |

Roles: `admin`, `interviewer`, `lecturer`, `supervisor`, `user`.
`admin` unlocks management endpoints (applications review, jobs, emails,
allowlist, slot generation). All other roles are "staff": they can sign in and
manage **their own** interview slots — the backend derives the acting
interviewer identity from the session, so staff cannot act on behalf of others.

## API routes

| Route | Access | Purpose |
|-------|--------|---------|
| `POST /api/auth/request-link` | public | request magic link (generic response) |
| `POST /api/auth/verify` | public | redeem token → session cookie |
| `GET /api/auth/me` | session | current session info |
| `POST /api/auth/logout` | session | revoke session, clear cookie |
| `GET/POST /api/auth/allowlist` | admin | list / add allowed emails |
| `PATCH/DELETE /api/auth/allowlist/{id}` | admin | enable/disable/re-role / remove (revokes sessions) |

## Security measures checklist

- [x] No link sent to emails outside the allowlist
- [x] Uniform generic response — no user enumeration
- [x] Token: long random, stored **hashed**, 15-min expiry, **single-use**
- [x] Rate limiting per email (3/15min) and per IP (10/15min), silent + audited
- [x] Server-side sessions, hashed cookie value, revocable at any time
- [x] Cookie: HttpOnly + SameSite=Lax (+ `COOKIE_SECURE=true` under HTTPS)
- [x] Disabling/removing an allowlist entry revokes live sessions immediately
- [x] Audit log: link requested/denied/rate-limited, login success,
      token invalid, logout, allowlist add/update/remove (with actor)
- [x] Admin cannot remove themselves from the allowlist (lockout guard)
- [x] Bootstrap: first admin seeded from `ADMIN_EMAIL` env at startup

> Development aid: with `DEBUG_EXPOSE_MAGIC_LINK=true` the request-link
> response includes the link directly (used by automated tests and local dev
> without checking the inbox). **This must be off in production.**

## Configuration (env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ADMIN_EMAIL` | — | seeded into allowlist as admin at startup |
| `MAGIC_LINK_TTL_MINUTES` | 15 | link validity |
| `SESSION_TTL_DAYS` | 7 | session validity |
| `COOKIE_SECURE` | false | set true behind HTTPS |
| `DEBUG_EXPOSE_MAGIC_LINK` | false | dev only — echo link in API response |
