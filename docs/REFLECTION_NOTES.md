# Raw material for your reflection (NOT the reflection)
Your reflection should be in your own voice and about what you learned. These are facts from the build you can draw on.
Delete this file if you prefer not to keep it in the repo.

## Problems met, and what each taught
| What happened | Cause | Fix | Lesson |
|---|---|---|---|
| The brief assumed DataCo has suppliers and inventory | It has neither | Derived suppliers, simulated inventory, stated on every deliverable | Check that a dataset really contains what a design needs before building on it |
| Airflow and the pipeline needed different SQLAlchemy versions | Airflow pins 1.4; pandas/Prophet code needs 2.x | Tasks run in a separate virtualenv via ExternalPythonOperator | Isolate dependencies before they collide in production |
| A DAG callable failed with NameError | Airflow ships the function's source to the venv, so closures break | One self-contained top-level function | Know how the orchestrator executes your code |
| The What-If app could not import `src` | Streamlit puts only the script's folder on the path; a local test had masked it with PYTHONPATH | Add the project root to `sys.path` | Test the way it will be run |
| A fixed 90% on-time alert would fire hourly | Real on-time rate is about 42% | Alert on a significant drop from the 30-day baseline | Thresholds must come from the data, not from habit |
| Demand-spike alerts: 160 in 24 hours | 3-sigma on low-count demand is mostly noise | Minimum volume and absolute lift | Statistical rules need guards on small numbers |
| Slack reported success but nothing arrived | The URL in `.env` had the prefix twice; Slack returned an HTML page with HTTP 200 and the code accepted any 200 | Require the reply `ok`; regression test added | A passing mock test did not prove the real system worked; verify with the real service |
| Airflow web server died after a restart | Gunicorn start-up exceeded 120 seconds | Recreate; settings to raise the timeout are documented | The scheduler kept running, so the pipeline never stopped: separate "pipeline healthy" from "UI reachable" |

## Testing
26 automated tests (KPIs, anomalies, forecast and runway, what-if, alert rules, delivery against mock Slack and SMTP, loader
against the real DataCo layout). The Slack bug above was found by real use, not by tests, which is the strongest example
of why the tests were incomplete; the regression test now covers it. Still untested: email to a real provider, behaviour
at scale, forecast accuracy on real data.

## Operational observations
* Real on-time delivery under DataCo's rule is about 42%.
* Hourly runs took about 25 to 50 seconds; the first full run on real data took about 70 seconds.
* Containers stop when the PC sleeps; the data survives in the Docker volume.
* Alert digests can be noisy; deduplication keys prevent repeats but not volume.

## Prompts to answer in your own words
1. Which part did you own end to end, and what would you do differently?
2. Which failure surprised you most, and how did you find the cause?
3. What would you not trust in this system yet, and why?
