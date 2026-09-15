# Preview as a controlled stability variable

Preview is both a product requirement and a known source of extra PTP/network pressure. Treat it as an independent experimental variable.

Initial capture baselines run with preview OFF. Then E3 adds preview at controlled cadence and controlled timing relative to capture transitions.

The objective is not simply to prove that 'preview makes it worse'. Identify the exact preview request/restore/retry event and lifecycle phase that first diverges, if any. If preview is safe in some phases and unsafe in others, encode that deterministic phase policy rather than disabling it globally without evidence.
