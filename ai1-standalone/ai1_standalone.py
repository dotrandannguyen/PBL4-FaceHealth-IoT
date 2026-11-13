"""Run a standalone, file-based AI1 ArcFace registration/recognition system."""

from ai1_standalone_core.app import StandaloneApplication
from ai1_standalone_core.utils import configure_console


def main():
    configure_console()
    try:
        StandaloneApplication().run()
    except KeyboardInterrupt:
        print("\nAI1 standalone stopped.")
        return 0
    except Exception as exc:
        print(f"AI1 standalone could not start: {exc}")
        print("Check that buffalo_l and the AI1 Python dependencies are available.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
