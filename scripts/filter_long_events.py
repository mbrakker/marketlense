import sys

try:
    from scripts.duration_tools import THRESHOLD_SECONDS, main_filter
except ModuleNotFoundError:
    from duration_tools import THRESHOLD_SECONDS, main_filter


def main(threshold: int = THRESHOLD_SECONDS, top_n: int = 100) -> None:
    main_filter(threshold_seconds=threshold, top_n=top_n)


if __name__ == "__main__":
    threshold = THRESHOLD_SECONDS
    top = 50
    if len(sys.argv) > 1:
        try:
            threshold = int(sys.argv[1])
        except ValueError:
            threshold = THRESHOLD_SECONDS
    if len(sys.argv) > 2:
        try:
            top = int(sys.argv[2])
        except ValueError:
            top = 50
    main(threshold, top)
