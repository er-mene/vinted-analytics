"""
Backward compatibility stub.
Verification worker functionality is now unified inside app.tasks.vinted_worker.
"""
from app.tasks.vinted_worker import vinted_worker as verification_worker

__all__ = ["verification_worker"]
