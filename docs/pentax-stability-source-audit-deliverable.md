# Source audit deliverable

A source-audit agent should return concrete rows in the repository CSV templates plus a short issue/comment summary containing exact source paths/functions and any uncertainties.

Do not return only prose such as "there are several timeouts" or "probably a race". The static inventories exist so another agent can verify and the hardware matrix can target exact boundaries.
