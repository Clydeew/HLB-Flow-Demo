# HLB Flow demonstration

## Three-minute video

| Time | Show |
|---|---|
| 0:00–0:20 | Problem, supplied manual-time and cost benchmarks, named sample and simulation labels |
| 0:20–0:45 | Nova phone and extension order verification |
| 0:45–1:05 | Consent and six-month request |
| 1:05–1:40 | Bank application: actual Colab-trained LightGBM inference, contributions, affordability and policy |
| 1:40–2:15 | Offer, exact schedule, total repayment, explicit acceptance and synthetic authentication |
| 2:15–2:40 | Simulated payment reference, one loan and merchant confirmation |
| 2:40–3:00 | Metrics: supplied benchmarks versus measured demo timing, review-inclusive modelled cost, limitations |

## Five-minute risk demonstration

Choose Missing transaction evidence. Submit a new application. Show model skipped, no offer, no payment, and persisted review task. Restore Normal operation. Switch to Credit officer, add a fresh-evidence note and re-evaluate. Explain that no officer can approve through an unresolved mandatory identity/data failure.

Backup risks: identity mismatch, model unavailable, lost payment response, or order price changed after quote. Unknown payment status must be reconciled using the original reference. Show exactly one capture/loan in the audit trail.

## Before presenting

- Run app setup before the event so dependencies are cached.
- Load the extension manually in desktop Chrome and pin it.
- Use the same synthetic customer in merchant and extension.
- Check health and model version; keep the terminal running.
- Sign in to the bank as Presenter; set Normal operation.
- Start a new run before each demonstration; do not delete historical audit data.
- Rehearse with internet disabled after setup. All inference/services/assets are local.
- Keep a web-checkout fallback available and label it accurately.
- Do not claim production security, actual payment execution, or validated real default probabilities.

## Operating boundaries

Demo access uses a generated shared local code and explicit roles. Synthetic on-screen authentication codes are a teaching device. External identity and financial-data calls are simulators. Model scoring, feature contributions, affordability, order checks, API permissions, database changes, payment state and audit are actual executed code.
