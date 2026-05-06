# Episode Auto-Label Prompt v1

Given sampled frames from a robot episode, return:

1. A concise episode caption.
2. Ordered task phases and optional LeRobot-style subtasks with frame ranges.
3. Success or failure assessment.
4. Visible objects.
5. Important frames for human review.

All labels are proposals and must be stored with `source = "vlm"` and
`review_status = "pending"`.
