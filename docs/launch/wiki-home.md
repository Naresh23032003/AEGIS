# AEGIS

A self-healing incident operations platform that shows its work. It watches a
real three-service stack, detects injected faults with a plain rules engine,
diagnoses them with LLM agents reading live metrics, logs and traces, fixes
low-risk problems on its own, routes risky ones through a signed human
approval, and writes every step to a hash-chained log you can replay.

## The two page overview

**[Read it here](https://github.com/Naresh23032003/AEGIS/blob/main/docs/launch/aegis-overview.pdf)**
(opens in the browser) or
[download the PDF](https://github.com/Naresh23032003/AEGIS/raw/main/docs/launch/aegis-overview.pdf).

Page one is what it does, the loop it runs, and the numbers from actual runs.
Page two is the half that does not work: the one scenario that never heals, the
two-word key mismatch underneath it, and why that test is left failing in CI.

## Start here

| Page                                                                                                       | What is in it                              |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| [README](https://github.com/Naresh23032003/AEGIS#readme)                                                   | Quickstart, the loop, measured results     |
| [Architecture](https://github.com/Naresh23032003/AEGIS/blob/main/docs/architecture.md)                     | Diagram and a paragraph per layer          |
| [Decision records](https://github.com/Naresh23032003/AEGIS/tree/main/docs/adr)                             | The eight decisions behind it              |
| [Final verification](https://github.com/Naresh23032003/AEGIS/blob/main/docs/reports/FINAL_VERIFICATION.md) | Runtime checks, defect list, pasted output |

## Running it

Docker and Python 3.12 are the only prerequisites, and the default
configuration needs no API key.

```
git clone https://github.com/Naresh23032003/AEGIS.git
cd AEGIS
cp .env.example .env
make up
```

Open <http://localhost:3000>, go to **chaos**, and press **inject fault** on
the **crash** card. Then try the **latency** card and watch it get it wrong.
