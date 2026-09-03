"""Phase 0-a sleep-loop stub — Phase 1 replaces this with the polling pipeline.

Runnable as `python -m worker` so the compose worker service has a real
entrypoint to exec into (`docker compose exec worker id`).
"""

import time

if __name__ == "__main__":
    while True:
        time.sleep(3600)
