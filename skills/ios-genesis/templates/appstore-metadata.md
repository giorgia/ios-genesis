# App Store Connect — Metadata

Source of truth for the listing. `asc_sync.py` reads the values below: under each `###` heading, the first fenced block, or else the first inline code span. Everything else here is notes for humans.

Search indexes the **name, subtitle and keywords** only. Don't repeat in the keywords a word already in the name or subtitle. No Apple trademarks (AirPods, iPhone, Apple Watch, Siri, HealthKit, …) in those three fields (Guideline 5.2.5); factual compatibility text in the description is fine. No other platform's name in any field.

Version: <version>. Positioning: <one line, from the release interview>. ASO reasoning: `docs/aso-plan.md`.

---

## en-US

### App Name (max 30)
`<name>`

### Subtitle (max 30)
`<subtitle>`

### Promotional Text (max 170, editable without review)
`<promo>`

### Keywords (max 100, comma-separated, no spaces)
```
<word>,<word>,<word>
```

### Description (max 4000)
```
<description>
```

### What's New (max 4000)
```
<what's new: only what's new since the last shipped version, each claim backed by code or a recorded check>
```
