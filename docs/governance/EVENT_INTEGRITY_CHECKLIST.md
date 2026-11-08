# Event Integrity and Disclosure Checklist

**Status: PARTICIPANT-CONFIRMED BUILD WINDOW OPEN; exact organiser timestamps and event-specific instructions still need documentary evidence.** The supplied `Problemstatemnt(2).pdf` is authoritative for the general rules it contains. The applicable organiser announcement remains authoritative for exact dates, exceptions and event-specific instructions.

## General rules confirmed from the supplied PDF

- [x] Development must occur during the official build window communicated for the event. Pre-window work will not count; substantial pre-window development may result in disqualification.
- [x] Research, planning, interviews and discussion may occur before the window unless event-specific instructions state otherwise.
- [x] Organisers may inspect repository access, commit history, file metadata, demonstrations and other timing evidence.
- [x] Existing libraries, APIs, frameworks, datasets and open-source components may be used in accordance with their licences.
- [x] Templates, boilerplate and previously created code must be clearly disclosed.
- [x] AI/no-code/low-code tools are permitted unless stated otherwise; significant tools and AI-generated components must be disclosed.
- [x] The project must be the team's own work; copied, misleading or falsely represented submissions may be disqualified.
- [x] Participants must respect software licences, intellectual property, data protection and user privacy.
- [x] Individual contributions and all submitted links/evidence must be truthful.

## Participant confirmation

The participant stated on 2026-11-08 that the official build window had started and submission was in two days. Event-window implementation proceeded after that statement. The original organiser announcement and exact official timestamp were not attached, so retain them as separate evidence. The precise submission cutoff and official timezone must not be inferred.

## Event-specific items still requiring documentary confirmation

- [ ] Official build-window start and end, with timezone.
- [ ] Confirmation that the disclosed pre-window planning archive, synthetic fixtures and helper script may be retained.
- [ ] Any specific AI-assistance disclosure format or restrictions beyond the supplied general rules.
- [ ] External API, hosted model, cloud storage and data-egress restrictions.
- [ ] Exact submission deadline, repository visibility and judge-access instructions.
- [ ] Any event-specific rules that override or add to the supplied PDF.

## Record of verification

See `BUILD_WINDOW_LOG.csv` and `BUILD_ACTIVITY_LOG.csv` for participant statement, source, evidence and follow-up actions. Do not fill unknown fields by assumption.

## Pre-window material disclosure

See `AI_AND_REUSE_DISCLOSURE.md`. The Phase 00/01 planning archives are AI-assisted planning/scaffolding and synthetic demo material prepared before the participant confirmed that the window was open. Later functional API, application, verification and frontend work is separately recorded as AI-assisted event-window implementation. Do not present the pre-window material as event-window code.

## Build-integrity rule

**Implementation may proceed based on the participant's confirmation that the window is open.** Preserve truthful activity and commit history, do not invent timestamps, and update the log if an organiser's official announcement clarifies start/end times or rules.
