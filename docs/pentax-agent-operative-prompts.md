# Copy/paste prompts for the physical operative

The test agent should use these messages (or equally explicit wording) rather than saying vague things such as "connect the camera".

## PC attachment

> **PHYSICAL ACTION REQUIRED — CAMERA TO PC**
>
> Please confirm no exposure is currently running. Disconnect the camera USB from the Polaris and connect it to the test PC. Leave the Polaris alone. Turn the camera on if needed. Do not open Benro Connect or OpenPolaris. Reply **PC CONNECTED** when complete. I will verify the camera from software before starting the test.

## Polaris attachment

> **PHYSICAL ACTION REQUIRED — CAMERA TO POLARIS**
>
> I have stopped the PC-side camera test processes. Please confirm no exposure is running, disconnect the camera USB from the PC and connect it to the Polaris camera USB path. Turn the camera on if needed. Do not open Benro Connect or OpenPolaris until I ask. Reply **POLARIS CONNECTED** when complete. I will verify fresh camera enumeration before starting the test.

## Substitute K-1 II for second pass

> **PHYSICAL ACTION REQUIRED — SWITCH BODY TO K-1 II**
>
> The K-3 III test batch is stopped. Please disconnect the K-3 III and attach the K-1 II to the host I specify next. Do not assume PC or Polaris from the previous test; wait for my attachment instruction.

## Camera power-cycle only

> **PHYSICAL ACTION REQUIRED — CAMERA POWER-CYCLE ONLY**
>
> Do not move the USB cable and do not restart the PC/Polaris. Turn only the camera off, wait until it is fully off, then turn it back on. Reply **CAMERA POWER-CYCLED** when complete.

## USB reconnect only

> **PHYSICAL ACTION REQUIRED — USB RECONNECT ONLY**
>
> No exposure is active. Leave the camera powered as it is. Disconnect and reconnect only the camera USB cable at its current host. Do not restart or power-cycle anything else. Reply **USB RECONNECTED** when complete.

## Armed destructive disconnect

> **FAULT-INJECTION TEST ARMED**
>
> Do not touch the camera yet. When I send **DISCONNECT NOW**, remove only the camera USB cable from the current host. Do not turn the camera off and do not reconnect until I ask.

## Principle

The operative performs the requested physical action; the agent verifies the resulting software state. A human confirmation never replaces enumeration/state verification.
