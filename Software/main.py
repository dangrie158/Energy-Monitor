#!/usr/bin/env python3
import dataclasses
import threading
import logging
import time
from typing import Dict, List

import yaml
import paho.mqtt.client as mqtt

from aquisition import Channel
from energy_stats import EnergyStatistics


class EnergyMeter:
    logger = logging.getLogger("EnergyMeter")

    def __init__(self):
        self.adc = DummyAdc()

    def load_config(self, config_path: str):
        with open(config_path) as config_file:
            config = yaml.load(config_file, yaml.Loader)

        try:
            mqtt_host = config["mqtt"]["host"]
            mqtt_port = config["mqtt"]["port"]
            self.mqtt_topic = config["mqtt"]["base_topic"]
        except KeyError:
            raise AttributeError(
                f"you need to specify mqtt host and port in the config file"
            )
        self.mqtt_client = mqtt.Client()
        # self.mqtt_client.connect(mqtt_host, mqtt_port)

        self.channels: List[Channel] = []
        for channel_config in config.get("channels", []):
            self.channels.append(Channel.from_config(channel_config))

        self.time_between_reads = config.get("sample_every", len(self.channels))
        self.energy_statistics = EnergyStatistics(
            self.channels, self.time_between_reads
        )

    def read_channels(self):
        while True:
            start_read = time.time()
            reading_map: Dict[Channel, float] = {}
            for channel in self.channels:
                channel_value = channel.read(self.adc)
                print(
                    f"new measurement from channel {channel.name}: {channel_value} {channel.unit}"
                )
                mqtt_channel = self.mqtt_topic.format(**dataclasses.asdict(channel))
                reading_map[channel] = channel_value
                self.mqtt_client.publish(mqtt_channel, channel_value)

            self.energy_statistics.add_reading(reading_map)
            read_time = time.time() - start_read
            self.logger.info(
                f"Sampled {len(self.channels)} channels in {read_time} seconds"
            )
            if read_time < self.time_between_reads:
                # make sure to sample at a maximum every time_between_reads seconds
                time.sleep(self.time_between_reads - read_time)
            else:
                self.logger.warning(
                    f"Reading took mora than {self.time_between_reads} seconds. It took {read_time} seconds"
                )

    def display_graphs(self):
        while True:
            time.sleep(1)
            print(
                self.energy_statistics.power_history(2),
                self.energy_statistics.daily_power(),
            )

    def run(self):
        reader_thread = threading.Thread(target=self.read_channels)
        display_thread = threading.Thread(target=self.display_graphs)
        reader_thread.start()
        display_thread.start()
        reader_thread.join()
        display_thread.join()


import numpy as np


class DummyAdc:
    def set_bit_rate(self, bitrate):
        self.bitrate = bitrate

    def set_pga(self, pga):
        self.pga = pga

    def read_raw(self, channel):
        if self.bitrate == 18:
            time.sleep(1 / 3.3)
        elif self.bitrate == 12:
            time.sleep(1 / 230)
        else:
            raise ValueError("unknown bitrate")
        if np.random.randint(0, 100) == 0:
            time.sleep(0.1)
        return np.random.normal(2**self.bitrate / 2, 2**self.bitrate / 2)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    meter = EnergyMeter()
    meter.load_config("config.yaml")
    meter.run()
