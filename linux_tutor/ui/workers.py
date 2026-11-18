"""Run slow operations (container start-up, assessment checks) off the GUI thread."""
from __future__ import annotations

import logging
import traceback

from .qt import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class Task(QRunnable):
    def __init__(self, fn, *args, with_progress: bool = False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()
        self.with_progress = with_progress
        self.setAutoDelete(True)

    def _emit(self, signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:       # the receiving window was closed meanwhile
            pass

    def run(self):
        try:
            if self.with_progress:
                self.kwargs["progress"] = lambda msg: self._emit(self.signals.progress, msg)
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:   # report every failure to the UI
            log.error("background task failed: %s", traceback.format_exc())
            self._emit(self.signals.failed, str(exc) or exc.__class__.__name__)
        else:
            self._emit(self.signals.done, result)


_keep: set = set()


def run_task(fn, *args, on_done=None, on_error=None, on_progress=None, **kwargs) -> Task:
    task = Task(fn, *args, with_progress=on_progress is not None, **kwargs)
    sig = task.signals
    _keep.add(sig)          # keep the signal object alive until the task reports back
    if on_done:
        sig.done.connect(on_done)
    if on_error:
        sig.failed.connect(on_error)
    if on_progress:
        sig.progress.connect(on_progress)
    sig.done.connect(lambda *_: _keep.discard(sig))
    sig.failed.connect(lambda *_: _keep.discard(sig))
    QThreadPool.globalInstance().start(task)
    return task
