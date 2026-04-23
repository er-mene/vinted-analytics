import time
import random
import logging
import threading
from app.db.database import get_items_to_verify, mark_item_as_sold, clear_queue, delete_listing
from app.services.vinted_service import check_item_status, ItemStatus

MAX_BATCH_SIZE = 10

class VerificationWorker:
    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        logging.info("Verification worker started.")

    def stop(self):
        """Stop the worker and wait briefly for the background thread to exit."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.thread = None
        logging.info("Verification worker stopped.")

    def run_loop(self):
        """Main verification loop."""
        while self.running:
            try:
                clear_queue()
                items = get_items_to_verify(MAX_BATCH_SIZE)

                if not items:
                    time.sleep(30)
                    continue

                logging.info("Verification worker checking %s items.", len(items))

                for item in items:
                    if not self.running:
                        break
                    try:
                        status = check_item_status(item["url"])
                    except Exception as e:
                        logging.info("Verification failed for listing %s. ", item["id"])
                        continue
                    if status == ItemStatus.REMOVED:
                        delete_listing(item["id"])
                        logging.info("Listing %s removed.", item["id"])
                    elif status == ItemStatus.SOLD:
                        mark_item_as_sold(item["id"])
                        logging.info("Listing %s marked as sold.", item["id"])
                    elif status == ItemStatus.ERROR:
                        logging.warning("Verification failed for listing %s.", item["id"])
                    time.sleep(random.uniform(10, 15))
            except Exception:
                logging.exception("Verification worker loop failed.")
                time.sleep(10)


verification_worker = VerificationWorker()
