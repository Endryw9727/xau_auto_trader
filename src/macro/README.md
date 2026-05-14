# Macro Fundamental Layer

This module will hold macro and fundamental context for research and paper
trading. Planned inputs include DXY bias, US yield bias, risk sentiment, and
high-impact event awareness such as CPI, NFP, FOMC, and Powell speeches.

It must not generate orders by itself. It must not contact brokers, store API
keys, enable live trading, or bypass the risk engine. For now it is advisory
only and safe for paper/research workflows.
