# Individual reflection

## 1. Engineering ownership
I set up and ran the whole system on my own machine. That meant getting WSL and Docker working on Windows, loading the 180,519 DataCo shipments into PostgreSQL, running the hourly Airflow pipeline, and connecting Superset, the What-If app and Slack alerts.

The part that took me longest to get working was Docker and WSL on Windows. At first I didn't understand what WSL was for, and the error messages told me something was wrong but not what to do about it.

One decision I would defend is saying openly, in the README, the deck and the demo, that the suppliers are derived and the inventory is simulated. DataCo has neither, and I did not want the results to look more real than they are.

## 2. System testing
Slack reported that the message was sent, but nothing showed up in the channel. A success message turned out not to be proof that it arrived. The URL in my .env file had the same prefix twice, so Slack sent back a web page instead of "ok". I fixed the URL, and the code now only counts a message as sent when Slack replies "ok".

I would still not trust email alerts, because I never tested them with a real account. I also have not checked how the system behaves with many more products than the roughly 1,500 SKUs I used, and I have not measured forecast accuracy on the real data.

## 3. Operational insights
The real data showed that only about 43% of deliveries are on time under DataCo's own rule. A fixed 90% on-time alert would have fired every hour, so the alerts now compare each hour against the 30-day baseline instead.

I would test with the real service early instead of relying only on mock tests.

---
*Drafted with help from an AI assistant (Claude), based on my project work and my own answers.*
