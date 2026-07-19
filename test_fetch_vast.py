import csv
import os
import tempfile
import unittest
from unittest.mock import Mock

import fetch_vast


class FetchVastTests(unittest.TestCase):
    def test_model_variants_and_prices(self):
        offers = [
            {"gpu_name": "NVIDIA H100 PCIe", "num_gpus": 2, "dph_total": 4.0},
            {"gpu_name": "H100_SXM5", "num_gpus": 8, "dph_total": 24.0},
            {"gpu_name": "NVIDIA H200 NVL", "num_gpus": 2, "dph_total": 8.0},
            {"gpu_name": "B200 SXM", "num_gpus": 8, "dph_total": 40.0},
            {"gpu_name": "Tesla A100-PCIE-80GB", "num_gpus": 4, "dph_total": 4.0},
            {"gpu_name": "GeForce RTX 4090", "num_gpus": 1, "dph_total": 0.4},
        ]
        summary = fetch_vast.summarize(offers)
        self.assertEqual(summary["H100"]["offer_count"], 2)
        self.assertEqual(summary["H100"]["available_gpus"], 10)
        self.assertEqual(summary["H100"]["price_median"], 2.5)
        for gpu in fetch_vast.REQUIRED_GPUS:
            self.assertIsNotNone(summary[gpu])

    def test_http_status_is_rejected(self):
        response = Mock(status_code=429, text="rate limited")
        session = Mock()
        session.post.return_value = response
        with self.assertRaisesRegex(fetch_vast.FetchError, "HTTP 429"):
            fetch_vast.fetch_offers("test-key", session=session)

    def test_invalid_response_shape_is_rejected(self):
        response = Mock(status_code=200, text="{}")
        response.json.return_value = {"machines": []}
        session = Mock()
        session.post.return_value = response
        with self.assertRaisesRegex(fetch_vast.FetchError, "response shape"):
            fetch_vast.fetch_offers("test-key", session=session)

    def test_failed_validation_preserves_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "gpu_prices.csv")
            original = "date,H100_median\n2026-06-22,2.0\n"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(original)
            with self.assertRaises(fetch_vast.FetchError):
                fetch_vast.append_csv({gpu: None for gpu in fetch_vast.TARGET_GPUS}, path)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), original)

    def test_valid_snapshot_is_written_atomically(self):
        item = {"price_median": 2.0, "price_min": 1.0, "price_dispersion": 2.0,
                "offer_count": 3, "available_gpus": 4}
        summary = {gpu: dict(item) for gpu in fetch_vast.TARGET_GPUS}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "gpu_prices.csv")
            fetch_vast.append_csv(summary, path, today="2026-07-19")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[-1][0], "2026-07-19")
            self.assertNotIn("", rows[-1][1:21])


if __name__ == "__main__":
    unittest.main()
