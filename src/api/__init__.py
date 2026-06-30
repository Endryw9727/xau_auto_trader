"""Read-only research API layer over the validation pipeline.

This package exposes the existing diagnostic/edge pipeline as JSON for the
research console UI. It never imports execution code, never sends orders and
cannot arm execution: every response advertises ``live_armed = false``.
"""
