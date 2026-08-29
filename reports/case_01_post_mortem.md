# Incident Post-Mortem

**Case:** diagnostic authority preserved  
**Divergence step:** `inventory_reserve`  
**Root cause:** `sequence_skip`  
**Culprit logs:** c01-02

# Post-Mortem: ecommerce_checkout Process Failure (CASE ID: case_01)

## Executive Summary
During an `ecommerce_checkout` process, a critical step, `inventory_reserve`, was unexpectedly skipped due to a 'legacy fast-path enabled' configuration. This skip led directly to the subsequent `payment_authorize` step failing because no active inventory reservation was in place. The incident resulted in a failed checkout for the affected transaction.

## Incident Timeline
*   **2026-03-12T10:00:03Z**: The `inventory-service` logged that `Reservation skipped: legacy fast-path enabled` for correlation ID `ord-8812` (log `c01-02`). This indicates the `inventory_reserve` step was bypassed.
*   **2026-03-12T10:00:05Z**: The `payment-gateway` logged `Authorization failed: no active reservation` for the same correlation ID `ord-8812` (log `c01-03`). This failure occurred because the preceding `inventory_reserve` step was skipped.

## Detected Divergence Step
The process diverged at the `inventory_reserve` step.

## Root Cause and Category
**Root Cause Category**: `sequence_skip`

**Explanation**: The `inventory_reserve` step was explicitly skipped due to a 'legacy fast-path enabled' configuration, as indicated by log `c01-02`. This skip directly led to the `payment_authorize` step failing because there was 'no active reservation', as seen in log `c01-03`. The process diverged at the inventory reservation step because a required action was bypassed, causing a downstream failure.

## Causal Chain
1.  The `ecommerce_checkout` process initiated.
2.  The `cart_validate` step likely completed successfully (no logs provided for this step).
3.  During the expected `inventory_reserve` step, the `inventory-service` decided to skip the reservation due to a 'legacy fast-path enabled' configuration (log `c01-02`).
4.  The process proceeded to the `payment_authorize` step without an active inventory reservation.
5.  The `payment-gateway` attempted authorization but failed because there was 'no active reservation' (log `c01-03`).
6.  The `ecommerce_checkout` process failed.

## Impact
The immediate impact was a failed checkout transaction for the user associated with correlation ID `ord-8812`. This directly resulted in a negative user experience and a lost sale. Depending on the frequency of this 'legacy fast-path' activation, there could be a broader impact on conversion rates and revenue.

## Recommended Remediation
1.  **Investigate 'legacy fast-path'**: Determine the conditions under which the 'legacy fast-path' is enabled (as seen in log `c01-02`) and if it is still a necessary or intended feature. If not, disable or remove it.
2.  **Dependency Enforcement**: Implement stricter dependency checks between process steps. The `payment_authorize` step should explicitly verify the existence of an active inventory reservation before proceeding, rather than assuming it. This could involve a pre-check or a more robust error handling mechanism if the reservation is missing.
3.  **Alerting**: Establish monitoring and alerting for instances where the `inventory_reserve` step is skipped, especially if it's not an expected behavior.

## Confidence / Limitations
**Confidence**: High. The provided logs clearly show the `inventory_reserve` step being skipped (log `c01-02`) and the immediate downstream failure of `payment_authorize` directly attributing the failure to 'no active reservation' (log `c01-03`). The explanation from the `InvestigationResult` aligns perfectly with the log evidence.

**Limitations**: The scope of this post-mortem is limited to the provided logs. We do not have information on the frequency of this issue, the specific configuration that enables the 'legacy fast-path', or the broader impact on other transactions or services. Further investigation into the 'legacy fast-path' mechanism is required.

## Evidence Table

| Log ID | Timestamp | Service | Message | Role |
|--------|-----------|---------|---------|------|
| c01-02 | 2026-03-12T10:00:03Z | inventory-service | Reservation skipped: legacy fast-path enabled | culprit + evidence |
| c01-03 | 2026-03-12T10:00:05Z | payment-gateway | Authorization failed: no active reservation | evidence |

## Evidence Trace

1. **Claim:** Process diverged at step 'inventory_reserve'
   - **Supporting logs:** c01-02
   - **Source:** diagnosis

2. **Claim:** Root cause category is 'sequence_skip'
   - **Supporting logs:** c01-02, c01-03
   - **Source:** diagnosis

3. **Claim:** Diagnostic explanation: The 'inventory_reserve' step was explicitly skipped due to a 'legacy fast-path enabled' configuration, as indicated by log c01-02. This skip directly led to the 'payment_authorize' step failing because there was 'no active reservation', as seen in log c01-03. The process diverged at the inventory reservation step because a required action was bypassed, causing a downstream failure.
   - **Supporting logs:** c01-02, c01-03
   - **Source:** diagnosis

4. **Claim:** Culprit anchor — inventory-service: Reservation skipped: legacy fast-path enabled
   - **Supporting logs:** c01-02
   - **Source:** diagnosis

5. **Claim:** Supporting evidence — payment-gateway: Authorization failed: no active reservation
   - **Supporting logs:** c01-03
   - **Source:** diagnosis
