# Individual reflection

> Template. Replace every `[FILL IN: ...]` with your own words, then delete this note. Before pushing, check that none
> are left: `Select-String "FILL IN" docs\REFLECTION.md` should print nothing.

## 1. Engineering ownership
What I built and ran myself: [FILL IN: for example setting up WSL and Docker, loading the DataCo data, running the pipeline].

The part that took me longest to get working was [FILL IN: what it was], because [FILL IN: what turned out to be the cause].

A decision I made and would defend: [FILL IN: for example saying openly that suppliers are derived and inventory is simulated].

## 2. System testing
My automated tests passed, but real use found a bug they did not: [FILL IN: what happened with Slack, in your own words].
What I changed afterwards: [FILL IN].

What I still would not trust in this system: [FILL IN: for example email delivery, behaviour at scale, forecast accuracy on real data].

## 3. Operational insights
What the real data showed that I did not expect: [FILL IN: for example that about 43% of deliveries are on time].
How that changed the alerting: [FILL IN].

If I did this again I would: [FILL IN].

---
### Facts you can draw on (checked against this project)
* Real DataCo data: 180,519 shipments loaded, none dropped; suppliers derived (12), inventory simulated, unit cost assumed.
* Hourly pipeline: six Airflow tasks, typically 25 to 50 seconds per run; Prophet for the 40 largest series.
* Problems met: Airflow vs SQLAlchemy version conflict; Streamlit could not import the project package; a fixed 90% on-time
  alert would fire every hour; demand-spike alerts were noisy on low-volume items; a Slack webhook URL pasted with its
  prefix twice returned an HTML page that the code counted as success; Airflow's web server timed out and its login reset
  whenever the container was recreated; the first "below safety stock" figure (419) was inflated by a threshold mismatch.
* 26 automated tests; the Slack and threshold problems were found by real use and then covered by tests or documented.
* Not verified: email to a real provider, load beyond about 1,500 SKUs, forecast accuracy on real data.
