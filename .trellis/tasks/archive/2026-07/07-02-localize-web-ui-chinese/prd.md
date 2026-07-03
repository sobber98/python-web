# Localize web UI to Chinese

## Goal

Localize the existing web management UI from English to Simplified Chinese so Chinese-speaking operators can use the platform naturally.

## Requirements

- Translate visible text in `login.html` and `dashboard.html` to Simplified Chinese.
- Set page language attributes to Chinese.
- Keep technical identifiers, API routes, CSS class names, dependency examples, and backend status values unchanged unless displayed through explicit UI labels.
- Keep the existing layout and responsive design intact.
- Update page tests to assert Chinese text renders.

## Acceptance Criteria

- [ ] Login page visible copy is in Simplified Chinese.
- [ ] Dashboard visible copy is in Simplified Chinese.
- [ ] Empty state, buttons, labels, hints, confirmation text, and status helper text are localized.
- [ ] Backend API responses and stored status values remain unchanged.
- [ ] Existing tests pass and page rendering test checks Chinese text.

## Out of Scope

- Multi-language switching.
- Backend/API localization.
- Translating package names, dependency examples, routes, or status enum values stored in data.
