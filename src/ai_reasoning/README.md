# AI Reasoning Layer

This module will hold advisory AI decision context and explanation models. It
can combine technical state, macro context, and risk state to explain whether a
paper-forward setup should be supported, blocked, or watched.

It must not open trades, close trades, send broker requests, bypass risk
checks, enable live trading, or promote a strategy automatically. AI output is
advisory only. `ai_can_execute` must remain false.
