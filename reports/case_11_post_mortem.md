# Incident Post-Mortem

**Case:** diagnostic authority preserved  
**Divergence step:** `seat_allocate`  
**Root cause:** `config_drift`  
**Culprit logs:** c11-04, c11-05

## Executive Summary

During a `b2b_saas_provisioning` process, the `seat_allocate` step failed to execute, leading to the customer being unable to log in and not receiving a welcome email. The root cause has been identified as `config_drift`, specifically a tenant being marked inactive due to a pending billing synchronization, which prevented seat allocation despite the contract being signed and the tenant created.

## Incident Timeline

*   **2026-03-12T20:00:00Z**: Contract signed (log `c11-01`).
*   **2026-03-12T20:00:01Z**: Tenant created (log `c11-02`).
*   **2026-03-12T20:00:02Z**: Billing profile reported as pending (log `c11-03`).
*   **2026-03-12T20:00:03Z**: Tenant marked inactive pending billing sync (log `c11-04`).
*   **2026-03-12T20:00:04Z**: Seat allocation skipped due to inactive tenant flag (log `c11-05`).
*   **2026-03-12T20:00:05Z**: Welcome email never triggered (log `c11-06`).
*   **2026-03-12T20:00:06Z**: Customer reported inability to log in (log `c11-07`).

## Detected Divergence Step

The process diverged at the `seat_allocate` step.

## Root Cause and Category

The root cause category is `config_drift`. The specific issue was that the tenant was marked as inactive pending a billing synchronization (log `c11-04`), which is a configuration or rule that prevented the `seat_allocate` step from proceeding (log `c11-05`).

## Causal Chain

1.  The `contract_signed` (log `c11-01`) and `tenant_create` (log `c11-02`) steps completed successfully.
2.  Immediately after tenant creation, the `billing-service` reported a pending billing profile (log `c11-03`).
3.  This pending billing status led to the `audit-service` marking the tenant as inactive, awaiting billing synchronization (log `c11-04`).
4.  Due to the tenant's inactive flag, the `seat-service` skipped the `seat_allocate` step (log `c11-05`).
5.  The failure to allocate seats prevented the `welcome_email` from being triggered (log `c11-06`).
6.  Ultimately, the customer was unable to log in (log `c11-07`), indicating a complete failure of the provisioning process.

## Impact

*   **Customer Impact**: The customer was unable to log in to the service and did not receive a welcome email, leading to a poor onboarding experience and service unavailability.
*   **Business Impact**: Delayed customer activation and potential churn due to immediate service failure.
*   **Operational Impact**: Manual intervention likely required to rectify the tenant's status and complete provisioning.

## Recommended Remediation

1.  **Review Billing Sync Logic**: Investigate the rules that mark a tenant inactive pending billing sync. Determine if this is the intended behavior for newly signed contracts or if there's a configuration that needs adjustment to allow initial seat allocation before full billing sync completion.
2.  **Process Flow Adjustment**: Evaluate if the `seat_allocate` step should be decoupled from the 'inactive' tenant flag, especially for initial provisioning, or if there should be a grace period.
3.  **Monitoring and Alerting**: Implement monitoring for tenants marked inactive immediately after creation, especially when the `contract_signed` and `tenant_create` steps have completed successfully.
4.  **Documentation Update**: Ensure that the expected behavior of the `b2b_saas_provisioning` process regarding billing status and tenant activation is clearly documented for all stakeholders.

## Confidence / Limitations

The diagnosis is based on the provided immutable `InvestigationResult` and corroborated by the retrieved logs. The explanation clearly links the `config_drift` to the tenant's inactive status and the subsequent failure of seat allocation. The evidence logs `c11-04` and `c11-05` directly support the identified culprit. No limitations or ambiguities were found in the provided diagnosis or logs.

## Evidence Table

| Log ID | Timestamp | Service | Message | Role |
|--------|-----------|---------|---------|------|
| c11-01 | 2026-03-12T20:00:00Z | contract-service | Contract signed | evidence |
| c11-02 | 2026-03-12T20:00:01Z | tenant-service | Tenant created | evidence |
| c11-03 | 2026-03-12T20:00:02Z | billing-service | Billing profile pending | evidence |
| c11-04 | 2026-03-12T20:00:03Z | audit-service | Tenant marked inactive pending billing sync | culprit + evidence |
| c11-05 | 2026-03-12T20:00:04Z | seat-service | Seat allocation skipped: tenant flag inactive | culprit + evidence |
| c11-06 | 2026-03-12T20:00:05Z | email-service | Welcome email never triggered | evidence |
| c11-07 | 2026-03-12T20:00:06Z | support-bot | Customer cannot log in | evidence |

## Evidence Trace

1. **Claim:** Process diverged at step 'seat_allocate'
   - **Supporting logs:** c11-04, c11-05
   - **Source:** diagnosis

2. **Claim:** Root cause category is 'config_drift'
   - **Supporting logs:** c11-01, c11-02, c11-03, c11-04, c11-05, c11-06, c11-07
   - **Source:** diagnosis

3. **Claim:** Diagnostic explanation: The 'contract_signed' and 'tenant_create' steps completed successfully. However, the 'seat_allocate' step was skipped because the tenant was marked as inactive, as indicated by log 'c11-05'. This 'inactive' flag was set due to a pending billing sync (log 'c11-04'), which suggests a configuration or rule (config_drift) caused the tenant to be in a state that prevented seat allocation, despite the contract being signed and tenant created. This divergence then led to the 'welcome_email' not being triggered and the customer being unable to log in.
   - **Supporting logs:** c11-04, c11-05
   - **Source:** diagnosis

4. **Claim:** Culprit anchor — audit-service: Tenant marked inactive pending billing sync
   - **Supporting logs:** c11-04
   - **Source:** diagnosis

5. **Claim:** Culprit anchor — seat-service: Seat allocation skipped: tenant flag inactive
   - **Supporting logs:** c11-05
   - **Source:** diagnosis

6. **Claim:** Supporting evidence — contract-service: Contract signed
   - **Supporting logs:** c11-01
   - **Source:** diagnosis

7. **Claim:** Supporting evidence — tenant-service: Tenant created
   - **Supporting logs:** c11-02
   - **Source:** diagnosis

8. **Claim:** Supporting evidence — billing-service: Billing profile pending
   - **Supporting logs:** c11-03
   - **Source:** diagnosis

9. **Claim:** Supporting evidence — email-service: Welcome email never triggered
   - **Supporting logs:** c11-06
   - **Source:** diagnosis

10. **Claim:** Supporting evidence — support-bot: Customer cannot log in
   - **Supporting logs:** c11-07
   - **Source:** diagnosis
