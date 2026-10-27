"""Workers return values through a queue; only the Tk thread touches widgets."""
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue


class UiWorker:
    def __init__(self, owner):
        self.owner, self.closed = owner, False
        self.results = Queue()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='desktop-io')
        self.timer = owner.after(50, self.poll)

    def submit(self, work, success, failure):
        if self.closed:
            return
        future = self.pool.submit(work)
        def finished(result):
            try:
                value = result.result()
            except Exception as exc:
                self.results.put((failure, exc))
            else:
                self.results.put((success, value))
        future.add_done_callback(finished)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                callback, value = self.results.get_nowait()
                callback(value)
        except Empty:
            pass
        if not self.closed:
            self.timer = self.owner.after(50, self.poll)

    def close(self):
        self.closed = True
        self.owner.after_cancel(self.timer)
        # Cancel jobs not started; running durable writes finish without widgets.
        self.pool.shutdown(wait=False, cancel_futures=True)
