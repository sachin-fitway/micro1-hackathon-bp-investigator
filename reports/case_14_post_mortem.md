# Incident Post-Mortem

**Case:** diagnostic authority preserved  
**Divergence step:** `usage_aggregate`  
**Root cause:** `false_success_signal`  
**Culprit logs:** c14-02

## Executive Summary
On 2026-03-12, the `b2b_saas_usage_billing` process experienced a critical failure during the `usage_aggregate` step. Although the aggregation service reported successful completion, the billing data was marked as 'skipped', leading to incorrect billing for a customer and an invoice remaining in a 'draft_only' state. This incident was caused by a false success signal, where the system indicated successful operation despite failing to perform its core function.

## Incident Timeline
*   **2026-03-12T23:00:01Z (c14-02)**: The `aggregate-service` reported "Aggregation complete" for `correlation_id` `prov-4421`, but with `billing_state`: `skipped`.
*   **2026-03-12T23:00:03Z (c14-08)**: The `billing-service` logged "Invoice total matches generated PDF" for `correlation_id` `prov-4421`, but the `internal_state` was `draft_only`.
*   **2026-03-12T23:00:04Z (c14-05)**: The `support-bot` logged "Customer billed wrong amount" for `correlation_id` `prov-4421`.

## Detected Divergence Step
The divergence occurred at the `usage_aggregate` step of the `b2b_saas_usage_billing` process.

## Root Cause and Category
The root cause category is `false_success_signal`. The `aggregate-service` (c14-02) reported "Aggregation complete" which is typically a success signal, but the accompanying metadata `"billing_state": "skipped"` indicates that the aggregation did not process the data for billing as expected. This misleading success signal allowed the process to continue, leading to downstream failures.

## Causal Chain
1.  The `usage_aggregate` step, executed by the `aggregate-service`, processed data for `correlation_id` `prov-4421`.
2.  Despite reporting "Aggregation complete" (c14-02), the service internally set `billing_state` to `skipped` within the same log entry. This constitutes a false success signal.
3.  Because the aggregation was skipped, the subsequent `invoice_generate` step likely used outdated or incorrect data, or the `invoice_deliver` step was impacted by the `draft_only` state.
4.  The `billing-service` generated an invoice (c14-08) that, while matching its generated PDF, remained in an `internal_state` of `draft_only` due to the skipped aggregation.
5.  Ultimately, this led to a customer being billed the wrong amount (c14-05), as reported by the `support-bot`.

## Impact
*   **Customer Impact**: At least one customer was billed an incorrect amount (c14-05), leading to potential dissatisfaction and requiring manual correction. This directly impacts customer trust and satisfaction.
*   **Operational Impact**: The invoice remained in a `draft_only` state (c14-08) despite being generated, indicating a failure in the automated billing and delivery process. This likely required manual intervention to resolve the billing discrepancy and deliver a correct invoice.
*   **Financial Impact**: Incorrect billing can lead to revenue leakage or overcharging, both of which have direct financial implications for the business and its customers.

## Recommended Remediation
1.  **Enhance Success Signal Validation**: Modify the `aggregate-service` to explicitly check the `billing_state` metadata. If `billing_state` is `skipped` or any other non-success state, the service should log an error and/or emit a failure signal instead of a success signal (c14-02).
2.  **Introduce State-Based Process Halting**: Implement a mechanism in the `b2b_saas_usage_billing` process to halt or flag the process as failed if critical metadata, such as `billing_state`, indicates an incomplete or skipped operation at any stage.
3.  **Alerting for `draft_only` Invoices**: Implement an alert for the `billing-service` when an invoice is generated but remains in `draft_only` state (c14-08) for an unexpected duration, indicating a potential process failure.
4.  **Automated Reconciliation**: Develop automated checks to reconcile aggregated usage data with generated invoices to catch discrepancies before customer impact.

## Confidence / Limitations
Our confidence in this diagnosis is high, as the `culprit_log_ids` (c14-02) directly show a contradiction between the log message ("Aggregation complete") and its associated metadata (`"billing_state": "skipped"`). This directly explains the downstream issues of incorrect billing (c14-05) and the `draft_only` invoice state (c14-08). The explanation provided by the `InvestigationResult` is fully supported by the retrieved logs. No limitations were identified in the diagnostic process.

## Evidence Table

| Log ID | Timestamp | Service | Message | Role |
|--------|-----------|---------|---------|------|
| c14-02 | 2026-03-12T23:00:01Z | aggregate-service | Aggregation complete | culprit + evidence |
| c14-05 | 2026-03-12T23:00:04Z | support-bot | Customer billed wrong amount | evidence |
| c14-08 | 2026-03-12T23:00:03Z | billing-service | Invoice total matches generated PDF | evidence |

## Evidence Trace

1. **Claim:** Process diverged at step 'usage_aggregate'
   - **Supporting logs:** c14-02
   - **Source:** diagnosis

2. **Claim:** Root cause category is 'false_success_signal'
   - **Supporting logs:** c14-02, c14-05, c14-08
   - **Source:** diagnosis

3. **Claim:** Diagnostic explanation: The 'usage_aggregate' step reported 'Aggregation complete' (c14-02), which is a success signal. However, the metadata within the same log entry explicitly states 'billing_state': 'skipped'. This indicates a false success signal, as the aggregation step did not perform its intended function of preparing data for billing, leading to the customer being billed the wrong amount (c14-05) and the invoice remaining in a 'draft_only' state (c14-08) despite being 'generated' and 'emailed'.
   - **Supporting logs:** c14-02, c14-05, c14-08
   - **Source:** diagnosis

4. **Claim:** Culprit anchor — aggregate-service: Aggregation complete
   - **Supporting logs:** c14-02
   - **Source:** diagnosis

5. **Claim:** Supporting evidence — support-bot: Customer billed wrong amount
   - **Supporting logs:** c14-05
   - **Source:** diagnosis

6. **Claim:** Supporting evidence — billing-service: Invoice total matches generated PDF
   - **Supporting logs:** c14-08
   - **Source:** diagnosis
