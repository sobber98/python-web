# Directory Structure

> How frontend code is organized in this project.

---

## Overview

The frontend is a standalone React 18 + TypeScript SPA built with Vite. It lives in `frontend/` and is served by FastAPI from the generated `app/static/app/` directory.

- Pages own routing-level data fetching and layout.
- Feature components for managed apps live under `components/apps/`.
- Reusable presentational primitives live under `components/ui/`.
- API access, query hooks, and formatting helpers live under `lib/`.
- Tests live under `src/test/`.

---

## Directory Layout

```text
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── vitest.config.ts
├── tailwind.config.cjs
├── postcss.config.cjs
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── types.ts
    ├── lib/
    │   ├── api.ts
    │   ├── queries.ts
    │   └── format.ts
    ├── components/
    │   ├── AppLayout.tsx
    │   ├── ProtectedRoute.tsx
    │   ├── Logo.tsx
    │   ├── apps/
    │   │   ├── AppSidebar.tsx
    │   │   ├── UploadCard.tsx
    │   │   ├── ControlCard.tsx
    │   │   └── LogsCard.tsx
    │   └── ui/
    │       ├── Button.tsx
    │       ├── Card.tsx
    │       ├── Field.tsx
    │       ├── StatusBadge.tsx
    │       ├── ProgressBar.tsx
    │       ├── ConfirmDialog.tsx
    │       └── Feedback.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── DashboardPage.tsx
    │   └── SettingsPage.tsx
    └── test/
        ├── setup.ts
        └── pages.test.tsx
```

---

## Module Organization

- **Page components** (`src/pages/`) correspond to routes and compose feature components.
- **Feature components** (`src/components/apps/`) are specific to app management and may use query hooks directly.
- **UI primitives** (`src/components/ui/`) must stay presentation-only: no `fetch`, no domain types beyond simple props.
- **Server state** belongs in TanStack Query hooks in `src/lib/queries.ts`; avoid duplicating server data in React state.
- **API calls** must go through the typed client in `src/lib/api.ts`.
- **Display mappings** (status labels, stage labels, time formatting) belong in `src/lib/format.ts`.

---

## Naming Conventions

- Components: `PascalCase.tsx`.
- Hooks: `useSomething` exported from `src/lib/queries.ts`.
- Types: `PascalCase` interfaces in `src/types.ts`.
- Query keys: centralized in `queryKeys` in `src/lib/queries.ts`.
- Utility functions: `camelCase` in `src/lib/`.
- Import alias: `@/` maps to `src/`.

---

## Build Output

`npm run build` writes to `../app/static/app` with Vite `base=/static/app/`. In Docker the build stage sets `BUILD_OUT_DIR=dist` and the runtime image copies the output into `app/static/app`. The output directory is gitignored.
