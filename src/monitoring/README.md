# Monitoring And Telegram Layer

This module will hold report and notification models for local paper-forward
monitoring. Planned outputs include daily summaries, signal reports, warning
messages, STOP messages, and open/closed trade summaries.

It must not execute trades, call broker APIs, store Telegram tokens in code, or
enable live trading. Telegram integration, when added later, must remain
notification-only unless a separate future task explicitly changes the scope.
