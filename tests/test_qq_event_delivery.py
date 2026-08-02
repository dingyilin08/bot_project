# -*- coding: utf-8 -*-
import unittest

from Tool.qq_event_delivery import send_event_with_retry


class _SequenceSender:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _SleepRecorder:
    def __init__(self):
        self.delays = []

    async def __call__(self, delay):
        self.delays.append(delay)


class QQEventDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_with_exponential_backoff_until_send_succeeds(self):
        sender = _SequenceSender(
            [RuntimeError("first"), RuntimeError("second"), {"id": "sent"}]
        )
        sleep = _SleepRecorder()

        result = await send_event_with_retry(
            sender,
            attempts=3,
            initial_delay=0.25,
            sleep=sleep,
        )

        self.assertEqual({"id": "sent"}, result)
        self.assertEqual(3, sender.calls)
        self.assertEqual([0.25, 0.5], sleep.delays)

    async def test_raises_last_error_after_attempts_are_exhausted(self):
        sender = _SequenceSender([RuntimeError("still unavailable")])
        sleep = _SleepRecorder()

        with self.assertRaisesRegex(RuntimeError, "still unavailable"):
            await send_event_with_retry(sender, attempts=2, sleep=sleep)

        self.assertEqual(2, sender.calls)
        self.assertEqual([0.5], sleep.delays)

    async def test_rejects_invalid_retry_configuration(self):
        with self.assertRaises(ValueError):
            await send_event_with_retry(_SequenceSender([None]), attempts=0)
        with self.assertRaises(ValueError):
            await send_event_with_retry(_SequenceSender([None]), initial_delay=-1)


if __name__ == "__main__":
    unittest.main()
