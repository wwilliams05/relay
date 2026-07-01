"""Double-click launcher for Relay.

A .pyw file opens with pythonw (no console window), so double-clicking this in
Explorer pops the Relay window straight up. Equivalent to running `relay ui`.
"""

from relay.gui import launch

if __name__ == "__main__":
    launch()
