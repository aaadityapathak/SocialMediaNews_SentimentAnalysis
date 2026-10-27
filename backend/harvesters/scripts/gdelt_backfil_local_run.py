"""Compatibility entry point for the modular, bounded GDELT backfill."""

from gdelt_retrieve.backfill import main, process_single_day

__all__ = ["main", "process_single_day"]

if __name__ == "__main__":
    main()
