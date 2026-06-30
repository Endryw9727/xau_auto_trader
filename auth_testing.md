# Auth Testing Playbook — Research Console

Auth model: JWT Bearer token (returned in response body, stored client-side in localStorage `rc_token`).
The backend also accepts the token via httpOnly cookie fallback, but the frontend uses the Authorization header.

## Seeded admin
- Email: admin@research.console
- Password: ResearchAdmin2025

## API tests (use external base or localhost:8001)
```
# login
curl -s -X POST $BASE/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@research.console","password":"ResearchAdmin2025"}'

# use token
TOKEN=... ; curl -s $BASE/api/auth/me -H "Authorization: Bearer $TOKEN"

# protected endpoint
curl -s -X POST $BASE/api/edge/significance-audit -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"symbols":["XAUUSD","EURUSD"]}'
```

## Expectations
- Login returns { token, user }. /me returns the same user.
- Wrong password returns 401; 5 failures -> 429 lockout for 15 min.
- /api/health returns { status:"ok", live_armed:false } and requires no auth.
