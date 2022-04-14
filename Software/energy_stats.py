import datetime
import logging
from typing import Dict, List, Optional
from threading import RLock

from scipy import stats
import numpy as np

from aquisition import Channel


class EnergyStatistics:
    logger = logging.getLogger("EnergyStatistics")

    def __init__(self, channels: List[Channel], time_between_reads):
        self._lock = RLock()

        # first collect the current channels for whiole house consumption
        self.current_channels = [
            channel for channel in channels if channel.type == "current_phase"
        ]
        self.num_phase_current_channels = len(self.current_channels)
        # the append all pther channels to the end of the list
        self.current_channels += [
            channel for channel in channels if channel.type == "current_other"
        ]
        voltage_channels = [
            channel for channel in channels if channel.type == "voltage"
        ]
        if 0 <= len(voltage_channels) >= 2:
            raise ValueError("Only supports a single voltage channel")
        self.voltage_channel = voltage_channels[0]

        self.temporal_resolution = time_between_reads
        self._reset_daily_statistics()

    def _reset_daily_statistics(self):
        self.today = datetime.date.today()
        start_of_day = datetime.datetime(
            self.today.year, self.today.month, self.today.day, 0, 0, 0
        )
        end_of_day = datetime.datetime(
            self.today.year, self.today.month, self.today.day, 23, 59, 59
        )
        self.timestamps = np.arange(
            start_of_day,
            end_of_day,
            step=self.temporal_resolution,
            dtype="datetime64[s]",
        )

        num_samples_per_day = self.timestamps.shape[0]

        self.current_readings = np.full(
            (len(self.current_channels), num_samples_per_day), np.nan, dtype=np.float64
        )
        self.voltage_readings = np.full(
            (num_samples_per_day,), np.nan, dtype=np.float64
        )

        # calculate the start index, because we don't always start at 00:00
        self.current_reading_index = (
            datetime.datetime.now() - start_of_day
        ).seconds // self.temporal_resolution

    def add_reading(self, reading_map: Dict[Channel, float]):
        with self._lock:
            # if we're on a new day, reset the statistics before adding new values
            if self.timestamps[-1] < datetime.datetime.now():
                self._reset_daily_statistics()

            # check if we can still fit the data, oterwise issue a warning
            index = self.current_reading_index
            if index >= self.timestamps.shape[0]:
                self.logger.warn("Overflowing sample buffer. Discarding new reading")

            for channel, value in reading_map.items():
                if channel in self.current_channels:
                    channel_index = self.current_channels.index(channel)
                    self.current_readings[channel_index, index] = value
                elif channel == self.voltage_channel:
                    self.voltage_readings[index] = value
                else:
                    raise ValueError(f"unknown channel: {channel.name}")

            # adjust the timestanp with the actual measurememnt time
            self.timestamps[index] = datetime.datetime.now()

            self.current_reading_index += 1

    def get_current_channels_for_name(self, channel_name: Optional[str]) -> List[int]:
        # if the channel name is None we want to calculate total power
        # so we return the indices of the first N channels
        if channel_name is None:
            return list(range(self.num_phase_current_channels))

        matching_channels = [
            channel for channel in self.current_channels if channel.name == channel_name
        ]
        if len(matching_channels) == 0:
            raise ValueError(f"Unknown Channel: {channel_name}")
        return [self.current_channels.index(matching_channels[0])]

    def daily_power(self, channel_name: Optional[str] = None) -> float:
        """
        calculates the total power consumption so far in watthours
        """
        # sometimes the "leading edge" of the timestamp array may lead from the next value,
        # and the delta is therefor negative leading to unexpected results. If we clip negatve values
        # to 0 here, they are effectively ignored in the sum calculation below

        with self._lock:
            return float(
                np.sum(self.power_history(num_bins=1, channel_name=channel_name))
            )

    def power_history(self, num_bins: int, channel_name: Optional[str] = None):
        """
        calculates the average power consumption in watthours for each measurement
        """
        # sometimes the "leading edge" of the timestamp array may lead from the next value,
        # and the delta is therefor negative leading to unexpected results. If we clip negatve values
        # to 0 here, they are effectively ignored in the sum calculation below
        current_channel_indices = self.get_current_channels_for_name(channel_name)

        with self._lock:
            timedeltas = np.clip(
                (self.timestamps[1:] - self.timestamps[:-1]).astype(np.float64), 0, None
            )
            total_current = np.sum(
                self.current_readings[current_channel_indices], axis=0
            )
            power = total_current[:-1] * self.voltage_readings[:-1] * timedeltas
            power_statistic = stats.binned_statistic(
                self.timestamps[:-1].astype(np.uint64), power, np.nansum, bins=num_bins
            )

            return power_statistic.statistic / 3600

    def live_power(self, channel_name: Optional[str] = None) -> float:
        """
        return the live (current) power consumption in watts
        """
        current_channel_indices = self.get_current_channels_for_name(channel_name)
        last_reading_index = self.current_reading_index - 1
        last_total_current = np.sum(
            self.current_readings[current_channel_indices, last_reading_index]
        )
        last_voltage = self.voltage_readings[last_reading_index]
        return last_total_current * last_voltage

    def live_voltage(self) -> float:
        """
        return the live (current) voltage in Vrms
        """
        last_reading_index = self.current_reading_index - 1
        last_voltage = self.voltage_readings[last_reading_index]
        return last_voltage

    def current_history(self, num_bins: int):
        with self._lock:
            current_statistics = stats.binned_statistic(
                self.timestamps.astype(np.uint64),
                self.current_readings,
                np.nanmean,
                bins=num_bins,
            )

            return {
                channel: current_statistics.statistic[index]
                for index, channel in enumerate(self.current_channels)
            }

    def voltage_history(self, num_bins: int):
        with self._lock:
            voltage_statistic = stats.binned_statistic(
                self.timestamps.astype(np.uint64),
                self.current_readings,
                np.nanmean,
                bins=num_bins,
            )
            return {self.voltage_channel: voltage_statistic.statistic}
