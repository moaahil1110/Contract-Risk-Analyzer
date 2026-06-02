# Priority 4 Security And Auth Hardening Plan

## Summary
The codebase already has Supabase login on the frontend, auth headers in `frontend/src/lib/api.js`, and `/history` is mostly user-scoped. The production gaps are backend-side: `analyse`, `status`, `clause detail`, `export`, and `upload-debug` can currently be reached by contract id without ownership enforcement, upload still accepts anonymous production requests, JWT verification can decode unsigned tokens when the secret is missing, and production CORS is still wildcard.

Supabase’s own docs are relevant here: secret/service keys bypass RLS, so this backend must enforce ownership itself even though database RLS exists. The exposed secret/service/JWT values also need rotation before deployment.

## Key Changes
- Centralize auth mode handling:
  - Keep `DEV_MODE=true` convenient locally, but make `DEV_MODE=false` fail closed.
  - In production, require `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` at startup.
  - Support both legacy HS256 JWTs through `SUPABASE_JWT_SECRET` and current Supabase asymmetric JWTs through JWKS.
  - Never decode JWTs without signature verification unless `DEV_MODE=true`.
  - Require `role=authenticated`, valid `sub`, valid `exp`, and expected audience for user access tokens.
- Add owner-scoped database helpers:
  - `get_contract_for_user(contract_id, user_id)`
  - `get_contract_with_clauses_for_user(contract_id, user_id)`
  - `get_active_analysis_job_for_contract(contract_id)` only after ownership is verified.
  - Use `WHERE id = contract_id AND user_id = user_id` instead of fetching by id and comparing later.
- Lock down routes:
  - `POST /upload`: production requires valid user; new uploads always store real `user_id`.
  - `POST /analyse/{contract_id}`: require user and owner check before enqueue.
  - `GET /analyse/{contract_id}/status`: require user and owner check.
  - `GET /analyse/{contract_id}`: require user and owner check.
  - `GET /analyse/{contract_id}/clauses/{clause_index}`: require user and owner check before returning clause text.
  - `GET /export/{contract_id}`: require user and owner check before generating PDF.
  - `/history` and `/history/{contract_id}`: keep protected, but fail closed in production if Supabase fails instead of silently falling back to memory.
  - `/upload-debug/{contract_id}`: disable in production; allow only dev owner/dummy-user access.
- Tighten production config:
  - Replace wildcard CORS with `ALLOWED_ORIGINS`.
  - Allow `http://localhost:3000` only for dev/local.
  - Disable FastAPI docs/OpenAPI in production unless explicitly enabled.
  - Keep `/health` public.
- Database defense in depth:
  - Add migration `005_security_auth_policies.sql`.
  - Enable RLS on `analysis_jobs`.
  - Add owner-based `SELECT` policy on `analysis_jobs` through `contracts.user_id`.
  - Add `idx_contracts_id_user` for fast owner-scoped lookups.
  - Do not force `contracts.user_id NOT NULL` yet, to avoid breaking old/dev anonymous rows; enforce non-null in production API instead.
- Frontend cleanup:
  - Keep existing auth headers.
  - Update polling failure handling to use `error_message`.
  - Treat `401` as login/session-expired and `404` as not found/no access.

## Secret Rotation And Supabase Setup
- Rotate exposed keys before deployment:
  - Create a new `sb_secret_...` key and update backend env.
  - Stop using the pasted legacy `service_role` JWT in the backend where possible.
  - Rotate/revoke exposed JWT signing material through Supabase Dashboard before public deployment.
- Use:
  - Frontend: publishable/anon key only.
  - Backend/worker: secret key only, stored in deployment secrets.
- Supabase docs: secret keys/service role bypass RLS and must stay server-side; leaked secret keys should be replaced, then deleted after all components use the new key.

Sources: [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys), [Supabase JWT signing keys](https://supabase.com/docs/guides/auth/signing-keys), [rotating legacy anon/service/JWT secrets](https://supabase.com/docs/guides/troubleshooting/rotating-anon-service-and-jwt-secrets-1Jq6yd).

## Test Plan
- Add backend auth/ownership tests:
  - Unauthenticated production upload returns `401`.
  - Authenticated upload stores the real `user_id`.
  - Dev unauthenticated upload still works through a deterministic dev user.
  - Owner can start analysis, poll status, fetch results, fetch clause details, and export.
  - Different user gets `404` for analyse/status/results/clause/export.
  - Missing/invalid JWT returns `401`.
  - Legacy HS256 tokens require `SUPABASE_JWT_SECRET`; asymmetric ES256/RS256 tokens verify through JWKS.
  - Production Supabase query failure returns service error, not memory fallback.
  - `upload-debug` is unavailable in production.
- Update existing API tests to provide fake authenticated users or enable explicit dev mode.
- Run:
  - `python3 -m compileall backend`
  - `python3 -m pytest backend/tests`
  - `cd frontend && npm run build`

## Assumptions
- Cross-user access returns `404`, not `403`, to avoid confirming whether a contract id exists.
- `DEV_MODE=true` keeps local testing easy, but ownership checks still run using a dummy dev user.
- Production allows no anonymous uploads.
- The backend can continue using a Supabase secret/service key, but every API route must enforce ownership before returning or mutating contract data.
- `SUPABASE_JWT_SECRET` is optional for projects using current Supabase asymmetric signing keys; `SUPABASE_JWKS_URL` can override the default JWKS endpoint if needed.
