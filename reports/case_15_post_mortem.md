# Incident Post-Mortem

**Case:** diagnostic authority preserved  
**Divergence step:** `entitlement_sync`  
**Root cause:** `webhook_missing`  
**Culprit logs:** c15-06

## Executive Summary
On 2026-03-13, the `b2b_saas_entitlement_provisioning` process for tenant T-4421 failed to complete successfully due to a missing webhook event. Although the initial `contract_signed` step was successful, the `entitlement_sync` step did not receive the necessary event, leading to an outdated entitlement state. This resulted in the `seat_activate` step being skipped and the license count remaining unchanged, despite the `tenant_provision` step reporting a misleading 'deferred' completion status.

## Incident Timeline
*   **2026-03-13T08:00:00Z** (`c15-01`): The `contract-service` recorded that a contract was signed for tenant T-4421.
*   **2026-03-13T08:00:01Z** (`c15-06`): The `audit-service` noted that the contract event was not observed by the entitlement service.
*   **2026-03-13T08:00:01Z** (`c15-02`): The `entitlement-service` detected an "Entitlement hash mismatch: expected v3, cache v2", indicating an outdated state.
*   **2026-03-13T08:00:02Z** (`c15-03`): The `provision-worker` reported "Tenant provisioning complete for tenant T-4421" with a `provision_state` of "deferred".
*   **2026-03-13T08:00:03Z** (`c15-04`): The `seat-service` skipped seat activation because "entitlement not ready".
*   **2026-03-13T08:00:03Z** (`c15-15`): The `license-service` confirmed that the "License count unchanged".

## Detected Divergence Step
The process diverged at the `entitlement_sync` step.

## Root Cause and Category
**Root Cause Category:** `webhook_missing`

The root cause of this incident is the failure of the contract event to be delivered to the entitlement service. Specifically, the `audit-service` log `c15-06` explicitly states "Contract event not observed by entitlement service", indicating a missing webhook or event delivery mechanism between the `contract-service` and the `entitlement-service`.

## Causal Chain
1.  The `contract_signed` step successfully completed, as evidenced by `c15-01` from the `contract-service`.
2.  However, the critical event signaling the contract signing was not received by the `entitlement-service`, as confirmed by `c15-06`.
3.  This lack of event delivery prevented the `entitlement-service` from updating its state, leading to an "Entitlement hash mismatch" (`c15-02`) when it attempted to process subsequent actions with outdated information.
4.  Despite the underlying issue, the `tenant_provision` step reported a misleading "complete" status with a "deferred" state (`c15-03`), which masked the actual failure in the entitlement synchronization.
5.  Consequently, the `seat_activate` step was skipped because the entitlement was not in a ready state (`c15-04`).
6.  Ultimately, the `license-service` confirmed that the license count remained unchanged (`c15-15`), indicating the complete failure of the provisioning process to activate seats.

## Impact
The primary impact was the failure to provision entitlements and activate seats for tenant T-4421, leading to a non-functional B2B SaaS entitlement for the customer. This directly affects customer onboarding and service availability. The misleading 'deferred' status from the `provision-worker` also created a false sense of progress, potentially delaying detection of the issue.

## Recommended Remediation
1.  **Investigate Webhook/Event Delivery:** Thoroughly investigate the event delivery mechanism from the `contract-service` to the `entitlement-service`. This includes checking webhook configurations, message queue health, and subscription statuses to identify why the contract signed event was not observed.
2.  **Implement Event Retries and Dead-Letter Queues:** Ensure robust retry mechanisms and dead-letter queues are in place for critical event deliveries to prevent single-point failures from halting the entire process.
3.  **Improve State Reporting for `tenant_provision`:** Re-evaluate the `provision_state: "deferred"` status. If this state indicates an incomplete or pending action that prevents subsequent steps, it should be reclassified or accompanied by clearer warnings to prevent false positives in process monitoring.
4.  **Monitoring and Alerting:** Enhance monitoring for critical event delivery failures between services, specifically for the `contract_signed` event to the `entitlement-service`. Implement alerts for `webhook_missing` scenarios or prolonged `entitlement hash mismatch` conditions.

## Confidence / Limitations
High confidence in the diagnosis. The `audit-service` log `c15-06` directly points to the contract event not being observed by the entitlement service, which is the critical missing piece in the causal chain. The subsequent logs (`c15-02`, `c15-04`, `c15-15`) are consistent with an entitlement state that was never correctly updated. The `provision_state: "deferred"` (`c15-03`) is noted as a misleading signal, but does not contradict the root cause.

## Evidence Table

| Log ID | Timestamp | Service | Message | Role |
|--------|-----------|---------|---------|------|
| c15-01 | 2026-03-13T08:00:00Z | contract-service | Contract signed for tenant T-4421 | evidence |
| c15-06 | 2026-03-13T08:00:01Z | audit-service | Contract event not observed by entitlement service | culprit + evidence |
| c15-02 | 2026-03-13T08:00:01Z | entitlement-service | Entitlement hash mismatch: expected v3, cache v2 | evidence |
| c15-03 | 2026-03-13T08:00:02Z | provision-worker | Tenant provisioning complete for tenant T-4421 | evidence |
| c15-04 | 2026-03-13T08:00:03Z | seat-service | Seat activation skipped: entitlement not ready | evidence |
| c15-15 | 2026-03-13T08:00:03Z | license-service | License count unchanged | evidence |

## Evidence Trace

1. **Claim:** Process diverged at step 'entitlement_sync'
   - **Supporting logs:** c15-06
   - **Source:** diagnosis

2. **Claim:** Root cause category is 'webhook_missing'
   - **Supporting logs:** c15-01, c15-06, c15-02, c15-03, c15-04, c15-15
   - **Source:** diagnosis

3. **Claim:** Diagnostic explanation: The 'contract_signed' step completed successfully (c15-01). However, the 'entitlement_sync' step failed to properly process the contract event, as indicated by 'c15-06' stating 'Contract event not observed by entitlement service'. This led to an 'Entitlement hash mismatch' (c15-02) because the entitlement service was working with an outdated state. Despite this, the 'tenant_provision' step reported 'complete' but with a 'deferred' state (c15-03), which is a false success signal for the overall process. Consequently, 'seat_activate' was skipped because 'entitlement not ready' (c15-04), and the license count remained unchanged (c15-15). The root cause is the missing webhook or event delivery from the contract service to the entitlement service, preventing the entitlement state from being correctly updated.
   - **Supporting logs:** c15-01, c15-06, c15-02, c15-03, c15-04, c15-15
   - **Source:** diagnosis

4. **Claim:** Culprit anchor — audit-service: Contract event not observed by entitlement service
   - **Supporting logs:** c15-06
   - **Source:** diagnosis

5. **Claim:** Supporting evidence — contract-service: Contract signed for tenant T-4421
   - **Supporting logs:** c15-01
   - **Source:** diagnosis

6. **Claim:** Supporting evidence — entitlement-service: Entitlement hash mismatch: expected v3, cache v2
   - **Supporting logs:** c15-02
   - **Source:** diagnosis

7. **Claim:** Supporting evidence — provision-worker: Tenant provisioning complete for tenant T-4421
   - **Supporting logs:** c15-03
   - **Source:** diagnosis

8. **Claim:** Supporting evidence — seat-service: Seat activation skipped: entitlement not ready
   - **Supporting logs:** c15-04
   - **Source:** diagnosis

9. **Claim:** Supporting evidence — license-service: License count unchanged
   - **Supporting logs:** c15-15
   - **Source:** diagnosis
