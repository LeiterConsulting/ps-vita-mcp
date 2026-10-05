# Private iPhone Companion guide

The iPhone Companion application remains private. This public guide describes its intended connection workflow and the Vita's implemented pairing contract. It does not include the app's source, Swift packages, Xcode project, signing material, builds or private handoff archives. Application distribution is managed separately from this repository; the public MIT license covers the published project source, not the private phone implementation.

As of October 5, 2026, Resident 0.1.2 / Control 0.3.4 / Starter 01.06 are installed on the test Vita. Matching startup, a physically displayed code and graceful challenge timeout passed. Successful individual confirmation, saved reconnect, actual phone interoperability, revocation persistence and overlay privacy are still open hardware gates. Development and device testing are paused. Use an approved private app build whose accepted protocol and native build identities match the test; do not change its allowlist solely because a PC build passes.

## Prepare the Vita

Use the [manual setup guide](GETTING-STARTED.md) to install the matched components. After normal boot, load Control through Starter once, wait for **MODULES LOADED**, and verify the network services from the PC. Reboot ends that runtime session. Do not boot-load Control or repeat its module-load action in the same boot.

Keep phone and Vita on the same trusted local network. The native API uses HTTP without transport encryption. Resident's pairing API normally uses port 17866; Control inspection normally uses 17867. File-manager FTP is a separate service and is not the phone pairing endpoint. A private app version may show different screens; the sequence below documents the native contract.

## Pair with physical approval

1. In the already loaded Starter, press SQUARE to open its short pairing window.
2. Start **Pair a Vita** in a compatible private app and use the Vita's address. The client sends a fresh ID/nonce request; the Vita shows its label.
3. Check that label. Release controls for at least half a second, then press CROSS once to approve. CIRCLE rejects/closes the request.
4. Enter the six-digit code in the requesting client immediately, preserving leading zeros. Keep Starter open until the request completes. Do not share the code in chat or issue reports.
5. A successful confirmation returns an individual credential once. The requesting app stores it privately for reconnect; the code is not returned by status or screen APIs.

The original request expires after 120 seconds. Approval and retry do not restart that deadline. After an expired or rejected challenge, use a fresh nonce and new physical approval. The clean native timeout already passed; successful confirmation and storage still need acceptance. Codes and credential tokens must never be published.

## Inspection permissions and privacy

Individual pairing permits Resident status and Control status, power-status and on-demand screen inspection. It does not grant file access, synthetic input, work-power changes or app launch/quit commands. The existing PC administrator pairing remains a separate authority. Future phone control would need its own ownership and device qualification.

Starter is excluded from capture and synthetic input. The native privacy implementation also blocks screen reads during an approved/completed challenge until its original deadline. A denied screen read while pairing is expected. Positive capture outside Starter and privacy under LiveArea overlays/cached thumbnails still require device tests; do not treat the implementation or an error response as proof of all those cases.

## Reconnect and Forget

The individual credential has an exact 90-day inactivity window. Successful supported inspection renews it through the Resident authority used by both services; a failed renewal must not report an extension. These persistence and renewal behaviors pass host fixtures but still need native saved-reconnect acceptance. They do not keep the Vita awake or replace normal runtime activation after reboot.

Starter's TRIANGLE view lists paired phones. Choose an entry, press CROSS, release briefly, then CROSS again to confirm **Forget**. Both services should then reject that credential, including after reboot. This physical revocation flow and reboot persistence remain pending tests. Do not use a PC input gesture to approve or forget a phone.

## Resolve connection problems

| Symptom | Next action |
| --- | --- |
| Services unavailable | Check Wi-Fi, wake the Vita manually, verify Resident and one-time Control activation; use the current address. |
| New native identity refused | Compare the private app's accepted build identities with the exact installed reports; review the allowlist before changing it. |
| No physical code shown | Keep Starter foreground, release controls before CROSS, and retain the sanitized error/diagnostic result. |
| Expired code | Close the old window and open a new physical exchange with a fresh nonce. |
| Confirmation reply lost | Retain the original request binding; do not blindly create another credential. The contract permits exact recovery within the original deadline, subject to device qualification. |
| Screen refused during pairing | Allow the original challenge window to end and use an allowed foreground application. |
| Credential expired, forgotten or renewal unavailable | Re-pair with physical approval after investigating the error; keep raw credentials out of logs. |

The [protocol](PAIRING.md), [device gate record](PAIRING-DEVICE-TESTS.md) and [PC-side guide](PC-SIDE.md) provide the public implementation details and limits. They enable interoperability without publishing the private iPhone code.
