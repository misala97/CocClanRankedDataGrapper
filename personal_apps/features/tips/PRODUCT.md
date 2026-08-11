# Product

## Register

product

## Platform

web

## Users

A single user: a bike/moped delivery courier tracking their own tip
income. Primary context is **mobile, immediately after finishing a
shift** — logging needs to be fast, one-handed, and tolerant of being
done tired or outdoors. Secondary context is a more relaxed review of
patterns and history, often on desktop, which the user genuinely enjoys
rather than tolerates.

## Product Purpose

A precise personal record of what each shift actually paid — cash tips,
online tips, deliveries, and trips — turned into three efficiency
numbers (€/hour, €/delivery, €/trip) and cross-checked against when and
in what conditions the shift happened (weekday, time of day, weather,
bike). Success is being able to answer, at a glance, "was this shift
worth it" and "when should I actually be working."

## Positioning

The one place that turns every logged shift into an honest, three-way
answer — per hour, per delivery, per trip — instead of a single vague
"good shift" feeling.

## Brand Personality

**Field-instrument.** Rugged, high-contrast, precise — closer to a bike
computer or a weatherproof gear display than a SaaS dashboard. Built for
a fast, confident glance, not a boardroom pitch.

## Anti-references

The purple/cyan dark-theme look already used across this codebase
(overview.html, the current tips page, and elsewhere) is an explicit
anti-reference — it's the generic default this redesign is deliberately
moving away from. This page also shares no visual identity with
coc_stats or with any other personal app in this repo (gym, pubquiz,
quizbank); each stands on its own.

## Design Principles

Logging always outranks reviewing — the fastest thing on the page is
finishing a shift and getting the numbers down, and nothing pushes that
action down or slows it up. Every rate stands with its two siblings —
€/hour, €/delivery, and €/trip are never shown alone, since they're one
combined judgment rather than competing headlines. Patterns stay
comparable, not tabbed away — weekday, time of day, weather, and bike
sit side by side so a combined pattern is visible without hunting for
it. Built like an instrument, not a dashboard — precise and glanceable
under real conditions (tired, one-handed, outdoors), not styled for a
boardroom. Nothing borrowed — this page's look owes nothing to any
other page in this codebase.

## Accessibility & Inclusion

Standard good practice: solid contrast (≥4.5:1 body text), keyboard and
touch-friendly controls, and a reduced-motion alternative for any
animation. No unusual requirements — single-user app.
