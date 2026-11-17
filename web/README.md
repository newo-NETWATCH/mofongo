# Web

The Mofongo lost-and-found frontend. Vite + React 18 + TypeScript, React Router, plain CSS. Built output is served from S3 through CloudFront.

## Run it

```
cd web
npm install
npm run dev        # http://localhost:5173 (port is fixed: it is the Cognito callback and API CORS origin)
npm run typecheck
npm run build
```

Config comes from `web/.env` (gitignored). Copy `.env.example` to `.env`. All values are public (the Cognito app client has no secret).

## Layout

| Path | What |
|---|---|
| `src/config.ts` | Typed reader of the `VITE_*` variables |
| `src/auth.tsx` | Cognito OIDC (Authorization Code + PKCE), `RequireAuth`, `signOut` |
| `src/api.ts` | Typed client for the 10 routes, `uploadPhoto`, `ApiError` |
| `src/vocab.ts` | The 14 categories and 12 colors (docs/data-model.md 2.1, 2.2) |
| `src/image.ts` | Convert a photo to JPEG (S3 accepts only `image/jpeg`, up to 10 MB) |
| `src/App.tsx` | Routes and nav |
| `src/screens/` | One file per screen (see its README) |

## Auth notes

- The API requires the Cognito **ID token**. `api.ts` sends `Authorization: Bearer <id_token>`; the access token would be rejected.
- Tokens are kept in `sessionStorage` and renewed with the refresh token.
- Cognito's discovery document has no end-session endpoint, so sign-out clears the local user and then redirects to `<hosted domain>/logout`. The post-logout URL must be in the app client's allowed sign-out URLs.
- Redirect URI is `http://localhost:5173/` (the root), not `/callback`.
