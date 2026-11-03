"""Launch the local UI using the same entry point as ui.serve."""
from .serve import main

if __name__ == "__main__":
    raise SystemExit(main())
