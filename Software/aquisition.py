from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable, Dict, List, Literal, NamedTuple, Tuple

import numpy as np

Aggregator = Callable[
    [
        List[float],
    ],
    float,
]


def average(collected_samples: List[float]) -> float:
    return float(np.asarray(collected_samples, dtype=np.float64).mean())


def rms(collected_samples: List[float]) -> float:
    values = np.asarray(collected_samples, dtype=np.float64)
    return float(np.sqrt(np.mean(np.square(values))))


_aggregators = {"average": average, "rms": rms}


class CalibrationPoint(NamedTuple):
    x: float
    y: float


@dataclass(frozen=True)
class Channel:
    """a human readable name of the channel"""

    name: str

    """the adc channel number"""
    channel: int

    """number of bits for the channel"""
    bits: Literal[12, 14, 16, 18]

    """x0, y0 of a line used to scale the raw ADC value to the apropriate unit"""
    calibration_points: Tuple[CalibrationPoint, CalibrationPoint]

    """programmable gain setting of the adc for this channel"""
    gain: Literal[1, 2, 4, 8] = 1

    """number of samples to collect when reading the channel"""
    samples: int = 1

    """The aggregation function used to convert the list of collected samples to a single value"""
    aggregator: Aggregator = average

    """A human readable string specifying the unit the scaled value is in"""
    unit: str = ""

    def read(self, adc) -> float:
        samples = []
        self._setup_for_reading(adc)
        for _ in range(self.samples):
            samples.append(adc.read_raw(self.channel))

        # it would be more efficient if we could scale after aggregation so we only need to transform
        # a single value, however this does not work for rms aggregation as we need to shift
        # to the correct y-intersect gefore transformation
        scaled_values = [self._scale_value(value) for value in samples]
        return self.aggregator(scaled_values)

    def _setup_for_reading(self, adc):
        adc.set_bit_rate(self.bits)
        adc.set_pga(self.gain)

    @cached_property
    def _m(self):
        # y = mx + b
        #     y2 - y1
        # m = -------
        #     x2 - x1
        dy = self.calibration_points[1].y - self.calibration_points[0].y
        dx = self.calibration_points[1].x - self.calibration_points[0].x
        return dy / dx

    @cached_property
    def _b(self):
        # y = mx + b
        # b = y - mx
        return self.calibration_points[1].y - (self._m * self.calibration_points[1].x)

    def _scale_value(self, value: float) -> float:
        return self._m * value + self._b

    @classmethod
    def from_config(cls, config: Dict[str, Any]):
        name = config.get("name", "?")
        if "bits" not in config:
            raise ValueError(
                f"you need to specify the number of bits for channel {name}"
            )
        num_bits = config.get("bits")
        if num_bits not in (12, 14, 16, 18):
            raise ValueError(f"invalid number of bits specified for channel {name}")

        calibration_point_values = config.pop("calibration_points", None)
        if calibration_point_values is None or len(calibration_point_values) != 2:
            raise ValueError(
                f"you need to specify exactly 2 calibration points for channel {name}"
            )
        if any(len(point) != 2 for point in calibration_point_values):
            raise ValueError(
                "each calibration point needs an x and y value for channel {name}"
            )
        calibration_points = (
            CalibrationPoint(*calibration_point_values[0]),
            CalibrationPoint(*calibration_point_values[1]),
        )

        aggregator_value = config.pop("aggregator", "average")
        if aggregator_value not in _aggregators:
            raise ValueError(
                f"the channel aggregator needs to be one of {_aggregators.keys()}"
            )
        aggregator = _aggregators[aggregator_value]

        return Channel(
            **config, calibration_points=calibration_points, aggregator=aggregator
        )
