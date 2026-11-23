"""Operator-only recovery for one fully refunded order that needs local revocation."""

import argparse
import asyncio
import logging

from app.google_play import GooglePlayError
from app.google_refund import reconcile_refunded_order
from app.logging_config import configure_logging, log_event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("order_no", help="The internal ChatStar order number, not the Google GPA ID")
    parser.add_argument("--confirm-revoke", action="store_true", required=True,
                        help="Explicitly approve revoking the app's benefits for this order")
    args = parser.parse_args()
    configure_logging()
    try:
        detail = asyncio.run(reconcile_refunded_order(args.order_no))
    except GooglePlayError as exc:
        raise SystemExit(f"Google Play could not verify the refund: {exc}") from exc
    except Exception:
        log_event(logging.getLogger(__name__), logging.ERROR, "refund.reconcile.failed", exc_info=True)
        raise SystemExit("Refund processing failed. See the error log above.") from None
    if detail is None:
        raise SystemExit("No change: the order is not a matching, fully refunded, locally paid Google Play order.")
    print(f"Processed {detail['order_no']}; deducted {detail['diamonds_revoked']} diamonds and saved a system message.")


if __name__ == "__main__":
    main()
