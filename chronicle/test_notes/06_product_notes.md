# Product Decisions & User Research Notes

## The "Zero Effort" Principle — 2024-06-25
Every feature decision must pass: does this require effort from the user?
If yes, cut it or redesign until it doesn't.
Examples of things cut because they required effort:
- Manual tagging of notes (cut: auto-tagging via domain inference)
- Setting memory importance (cut: compound salience score decides automatically)
- Choosing which notes to surface (cut: algorithm decides, user just sees results)
The product only wins if it feels magical. Magic = things happen without asking.

## User Interview #1 — Priya, freelance designer — 2024-07-15
Uses Notion for everything. Has 3 years of notes.
"I know I've solved this client's problem before but I can't find the note"
Key quote: "I search, I get 40 results, I give up"
Pain: too many results, not ranked by relevance to current work
Willingness to pay: "I'd pay $20/month if it actually worked"
Feature request: works with Notion (strong request, mentioned 3 times)
Action: prioritise Notion integration for v2.

## User Interview #2 — Rajan, backend engineer — 2024-07-16
Uses Obsidian + Dataview. 2000+ notes.
"My notes are perfectly organised but I never look at them"
Key quote: "The problem is remembering that the note EXISTS"
Pain: organisation solves the wrong problem — discoverability is the real issue
Willingness to pay: $15/month, would pay more for team version
Feature request: IDE plugin (VS Code sidebar)
Action: add to roadmap after core product is stable.

## User Interview #3 — Sarah, product manager — 2024-07-18
Uses Bear notes. Much smaller note volume (~200 notes).
"I constantly write the same research notes in different meetings"
Key quote: "I wish something would just tell me I already wrote this"
Pain: duplicate effort, not missing context
This validates the duplicate detection (low novelty gate) in SnowMemory.
Willingness to pay: $25/month ("saves me 2 hours a week easily")
Feature request: Slack integration — capture notes directly from Slack.

## Pricing Research — 2024-08-01
Surveyed 40 waitlist users on pricing.
Results:
- $9/month: 78% would pay
- $19/month: 61% would pay
- $29/month: 34% would pay
- $49/month: 12% would pay
Decision: launch at $19/month. Good conversion, not leaving money on table.
Annual plan: $190/year (saves ~$38, 2 months free) — add after 3 months of data.
Free tier: 50 memories — enough to feel the value, not enough to replace Pro.

## The "Wow Moment" Definition — 2024-08-14
Analysed beta user behaviour to find the activation moment.
Users who reached "wow" all shared one behaviour: they queried something they
were actively working on AND got back a memory from more than 60 days ago
that was directly relevant.
Time to wow: median 8 minutes after first file upload.
Users who churned: 70% never uploaded more than 1 file.
Activation metric: user uploads 3+ files AND runs 3+ queries in first session.
Onboarding goal: get users to activation metric in first 10 minutes.

## Why We Don't Show Scores to Users — 2024-09-20
Early version showed "relevance score: 0.73" next to each result.
User research finding: numbers made users trust results LESS not more.
"What does 0.73 mean? Is that good?"
Decision: replaced with visual dots (●●●○○) and removed numbers entirely.
Qualitative beats quantitative in consumer UI. Engineers are the exception.
Keep scores in API response for power users and debugging.
