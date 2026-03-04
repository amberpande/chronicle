# Frontend & UX Notes

## Why Next.js App Router Not Pages Router — 2024-06-18
Chose App Router for new layouts API and React Server Components.
RSC reduces client JS bundle — important for initial load performance.
Tradeoff: Clerk middleware setup is slightly different with App Router.
Clerk config: add `middleware.ts` at root, not inside `/pages`.
Key gotcha: `useUser()` hook only works in Client Components — add `"use client"` directive.

## Drag and Drop File Upload — 2024-07-22
Used `react-dropzone` for file upload component.
npm: `npm install react-dropzone`
Supports: click to upload AND drag and drop in same component.
Added visual feedback: border turns blue on drag-over, green on successful upload.
Show file name + size before confirming upload.
Rejected files (wrong type/too large) show red error message inline.

## Loading States — Don't Leave Users Hanging — 2024-08-10
Users abandoning during ingestion because no progress feedback.
Added three states to every async operation:
1. Loading spinner with descriptive text ("Processing your notes...")
2. Success toast with result summary ("12 memories stored")
3. Error toast with actionable message ("File too large. Max 10MB")
Library: `react-hot-toast` for toasts — 1KB, zero config.
npm: `npm install react-hot-toast`
Rule: every button click must give visual feedback within 200ms.

## The Query Results Design — 2024-09-05
First version showed raw memory content in a list. Users confused.
Iterated to card layout with:
- First 150 characters of content (truncated with "...")
- Relevance indicator (dots: ●●●○○)
- Expand button to see full memory
- Age indicator ("3 months ago")
User testing feedback: "I immediately knew which ones were worth reading"
Key insight: show enough to recognise, not so much it overwhelms.

## Mobile Responsive Failure — 2024-09-28
App completely unusable on mobile — side-by-side layout broke below 768px.
Fix: Changed two-column layout to single column on mobile using Tailwind breakpoints.
`<div className="flex flex-col md:flex-row gap-6">`
Added bottom sheet for query panel on mobile — slides up from bottom.
25% of waitlist signups were on mobile. Cannot ignore mobile.

## Dark Mode Implementation — 2024-10-18
Added dark mode using Tailwind's `dark:` variant + `next-themes`.
npm: `npm install next-themes`
Wrap app in `ThemeProvider`. Toggle button in header.
Persists preference to localStorage.
One bug: flash of wrong theme on first load (FOUC).
Fix: add `suppressHydrationWarning` to html tag and set default theme server-side.
Most PKM users prefer dark mode — worth the effort.
