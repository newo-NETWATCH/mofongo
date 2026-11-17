# Screens

App.tsx imports each screen as a NAMED export from `src/screens/<Name>.tsx`. Write the file with exactly this name and export:

| File | Export | Route | Data model |
|---|---|---|---|
| BrowseScreen.tsx | `BrowseScreen` | `/` (signed in) | 1.1 |
| ItemDetailScreen.tsx | `ItemDetailScreen` | `/items/:itemId` | 1.2 |
| PostItemScreen.tsx | `PostItemScreen` | `/post` | 1.3 |
| NewReportScreen.tsx | `NewReportScreen` | `/reports/new` | 1.4 |
| MyReportsScreen.tsx | `MyReportsScreen` | `/reports` | 1.5 |
| ReportDetailScreen.tsx | `ReportDetailScreen` | `/reports/:reportId` | 1.6 |
| AlertsScreen.tsx | `AlertsScreen` | `/alerts` | 1.7 |

Already written: `LandingScreen.tsx`, `CallbackScreen.tsx`.

Shared pieces to use, not redo:
- `../api` (`api.*`, `uploadPhoto`, `ApiError`, `describeError`, response types)
- `../vocab` (`CATEGORIES`, `COLORS`, `categoryLabel`, `colorLabel`, `COLOR_HINT`, `MAX_COLORS`)
- `../image` (`convertToJpeg` for the photo upload)
- `../auth` (`useAuth`)
- CSS classes in `../styles.css` (`.card`, `.grid`, `.notice`, `.notice-error`, `.muted`, `.chip`, `.primary`, `.field`, `.form`, `.thumb`)

Use `useParams()` for `:itemId` / `:reportId`. Show a placeholder when `item.photo` is missing.
