# LinkedIn: launch post

Attach: [demo video](../../docs/media/demo.gif) (or the final rendered
video per the script in plan/07-review-and-launch.md) and
[architecture-card.png](architecture-card.png).

---

Most self-healing ops demos sell the resolution. I built one that sells
proof of resolution instead.

AEGIS watches a real three-service checkout system, detects injected
faults with a plain rules engine, and hands off to a small team of LLM
agents that diagnose from live traces and logs. Low-risk fixes execute on
their own. Riskier ones wait on a signed human approval before anything
touches the system. Across three live runs per scenario, the average
time from fault to healed sat between 21 and 132 seconds depending on the
scenario, at under a cent of LLM cost per incident.

The part I actually care about: every step is a hash-chained event, every
approval is Ed25519-signed in the browser, and every incident can export
an evidence pack, a PDF timeline plus the raw signed event log, with
section headers mapped to the EU AI Act articles a system like this would
eventually need to satisfy (record-keeping, human oversight, incident
reporting). No compliance claim here, those obligations don't bite until
December 2027. But the runtime shape that would satisfy them is there
now, not bolted on later.

It also denies its own proposals when it isn't sure. Watching the policy
gate reject a low-confidence diagnosis and escalate to a human, live,
rather than guess, was the moment this stopped feeling like a demo and
started feeling like the actual point.

Repo, architecture, and the numbers behind every claim above:
github.com/Naresh23032003/AEGIS

#incidentresponse #llmagents #observability
