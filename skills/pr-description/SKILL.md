---
name: pr-description
description: Write or revise a GitHub PR description or Phabricator test plan. Use before `gh pr create`, `gh pr edit --body`, or `moz-phab submit --test-plan`.
---

# PR Description

## Audience

The reader is another engineer, or the author themselves, opening this PR
today or years from now with little context on the change. Test every
sentence: could that reader understand why this matters? If not, replace an
internal name with what the thing does ("the server that delivers Firefox
updates to users") or drop the sentence.

## Voice

Write in the author's first person. Talk like a peer explaining the change,
not a report generator. Never start with "This PR...".

## Writing rules

1. No em-dashes. Use a comma, a period, or rewrite the sentence.
2. No hedging. Never write "seems", "likely", "probably", "appears to", "I
   think", or "it seems like". State observations as facts. Exception: when a
   threat or outcome is genuinely unconfirmed, name the uncertainty precisely
   instead of asserting it. "A potential attacker" is not hedging, it is
   accurate. "An attacker" when no exploitation was confirmed is overclaiming.
3. No inflated adjectives. Avoid pivotal, groundbreaking, exceptional,
   outstanding, remarkable, stellar, incredible, amazing, fantastic,
   tremendous. Let the work speak for itself.
4. Short sentences. If a sentence joins more than one independent clause with
   "and", "but", or "which", split it.
5. Active voice, named agency. Never "improvements were made", "work was
   done", "it was decided". Name who does what.
6. Outcomes, not steps. Ask "what changes because of this?", not "what will
   be done?".
   - Bad (step): "We will refactor CookieStorage.cpp to use the new
     MozStorageConnection API."
   - Good (outcome): "Firefox will eliminate a class of
     corruption-on-shutdown bugs that have triggered S2 incidents in each of
     the last three releases."
7. Explain or replace internal names.
   - Bad: "We are migrating the nsICookieService bindings off of the legacy
     IDB backend."
   - Good: "We are migrating Firefox's cookie storage to an async API. This
     removes the manual locking that causes intermittent failures in
     automation and unblocks a class of shutdown-corruption bugs."
8. Quantify, and be brief. Use numbers and relative framing: "fixed 2 of 11
   open network regressions", "~15% reduction in P50 load time on metered
   connections". Never pad.

## Content

Include only what the diff and CI can't already show.

1. **Why**: 1-3 sentences plus the bug or issue link.
2. **Why this approach**: rejected alternatives. Leave this out if there was
   no real choice.
3. **Evidence**: end-to-end runs (staging task, try push, release run),
   benchmarks with before/after numbers, manual checks. Never unit tests,
   linters, type checks, or anything else CI already runs on the PR.
4. **Merge order**: required whenever the change spans more than one repo.
   Write it as a numbered list. Each entry is the full PR URL
   (`https://github.com/<owner>/<repo>/pull/<n>`) or full Phabricator URL
   (`https://phabricator.services.mozilla.com/D<n>`). Never a short form like
   `owner/repo#123` or a bare repo name. Never drop this section to save
   words, and don't count it toward the word budget. This is the only place
   that documents merge-order PR text; the rules don't repeat it.

   Keep it in sync: when a PR joins or leaves the set, update the Merge order
   section in every PR in the list, not just the new one. For each PR: fetch
   its current body first (`gh pr view <n> --json body`), replace only the
   Merge order section, and keep the rest of the body untouched, including
   any wording the author added by hand. Report which PRs were updated. The
   list and the order are identical across all PRs in the set, and each PR
   marks its own line with "← this PR".
5. **Risks / follow-ups**: only if they apply.

## Editing an existing description

The author may have edited the body by hand since it was last written. Always
fetch the current body first with `gh pr view <n> --json body` and treat it
as the source of truth. Change only the section that needs updating, usually
Evidence. Never regenerate the whole body. Keep the author's wording, even
where it breaks these rules.

## Don't

- Walk through files one by one.
- Restate what the diff already shows.
- Explain basics a reviewer of this repo already knows.
- Hedge.
- Add empty sections.
- Use a heading where one paragraph is enough.

## Budget

About 150 words of prose. That is a ceiling, not a target. If one sentence
says it, stop there. Log excerpts are 5 lines or fewer, each with a `#L<N>`
anchor pointing at the exact line, for example:
```
https://firefox-ci-tc.services.mozilla.com/tasks/<id>/runs/0/logs/public/logs/live.log#L276
```

## Missing rationale

If the prompt doesn't give the why or the rejected alternatives, stop and
report back asking for them. Don't invent them.

## Test plan variant

For `moz-phab submit --test-plan`, write evidence only, same budget as above.

## Self-check

Before submitting, reread the body as a skeptical reviewer seeing it for the
first time, and cut anything that doesn't earn its place.

## Examples

**Bad** (current verbose style):

> ## Summary
>
> This PR updates the retry logic.
>
> ### Files changed
> - `src/retry.py`: added exponential backoff
> - `src/config.py`: added new retry config
> - `tests/test_retry.py`: added tests
>
> ### Test results
> ```
> 14 passed in 2.31s
> ```

**Good**:

> Retry requests now back off exponentially instead of retrying every 500ms.
> The flat interval was overwhelming the update server during its weekly
> restart window. That caused a 20-minute spike in 503s each time
> ([Bug 1234567](https://bugzilla.mozilla.org/show_bug.cgi?id=1234567)).
>
> I considered a fixed longer interval first. That would slow down the
> common case where the server recovers in under a second.
>
> Verified on staging: 0 503s over three restart windows, down from ~400 per
> window.
> https://firefox-ci-tc.services.mozilla.com/tasks/abc123/runs/0/logs/public/logs/live.log#L88
