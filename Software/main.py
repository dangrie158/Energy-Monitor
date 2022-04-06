#!/usr/bin/env python3
import argparse
import dataclasses
import threading
import logging
import time
from pathlib import Path
from typing import Dict, List

import yaml
from PIL import ImageFont

from aquisition import Channel
from energy_stats import EnergyStatistics

try:
    from adc import ADCPi as ADC
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    from paho.mqtt.client import Client as MQTTClient
except ImportError:
    logging.getLogger().warning("Running in MOCKING MODE without real hardware access")
    from mocks import DummyAdc as ADC  # type: ignore
    from mocks import i2c, canvas, ssd1306  # type: ignore
    from mocks import MQTTClient  # type: ignore


class EnergyMeter:
    logger = logging.getLogger("EnergyMeter")

    def load_config(self, config_path: str):
        self.logger.debug(f"reading config from: {config_path}")
        with open(config_path) as config_file:
            config = yaml.load(config_file, yaml.Loader)

        self.logger.debug(f"read following config: {config}")

        try:
            self.mqtt_host = config["mqtt"]["host"]
            self.mqtt_port = config["mqtt"]["port"]
            self.mqtt_topic = config["mqtt"]["base_topic"]
        except KeyError:
            raise AttributeError(
                f"you need to specify mqtt host and port in the config file"
            )

        self.adc_addresses = config.get("adc_addresses", [0x68, 0x69])
        if len(self.adc_addresses) != 2:
            raise AttributeError("you need to specify exactly 2 adc chip addresses")

        self.display_address = config.get("display_address", 0x3C)

        self.channels: List[Channel] = []
        for channel_config in config.get("channels", []):
            self.channels.append(Channel.from_config(channel_config))

        self.time_between_reads = config.get("sample_every", len(self.channels))
        self.energy_statistics = EnergyStatistics(
            self.channels, self.time_between_reads
        )

    def initialize(self):
        display_port = i2c(port=1, address=self.display_address)
        self.display = ssd1306(display_port)

        self.adc = ADC(*self.adc_addresses)

        self.mqtt_client = MQTTClient()
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)

    def read_channels(self):
        while not self.should_stop.is_set():
            start_read = time.time()
            reading_map: Dict[Channel, float] = {}
            for channel in self.channels:
                channel_value = channel.read(self.adc)
                self.logger.debug(
                    f"new measurement from channel {channel.name}: \t{channel_value:2.3f} {channel.unit}"
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
                self.should_stop.wait(self.time_between_reads - read_time)
            else:
                self.logger.warning(
                    f"Reading took mora than {self.time_between_reads} seconds. It took {read_time} seconds"
                )

    def update_display(self):
        oled_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
        with canvas(self.display) as draw:
            draw.rectangle(self.display.bounding_box, outline="white", fill="black")
            draw.text((10, 10), "OLED-Display", font=oled_font, fill="white")

    def run(self):
        self.should_stop = threading.Event()
        self.should_stop.clear()

        reader_thread = threading.Thread(target=self.read_channels)

        reader_thread.start()

        try:
            while not self.should_stop.is_set():
                self.update_display()
                # update the display with 1 fps max
                self.should_stop.wait(1)
        except KeyboardInterrupt:
            logging.info("shutdown signal received, stopping threads...")
            self.should_stop.set()

        reader_thread.join()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument(
        "--config",
        type=Path,
        help="path to the configfile to load the settings from",
        default=Path("config.yaml"),
    )
    parser.add_argument("--verbose", "-v", action="count", default=0)
    args = parser.parse_args()

    log_level = logging.ERROR
    if args.verbose == 1:
        log_level = logging.WARNING
    elif args.verbose == 2:
        log_level = logging.INFO
    elif args.verbose >= 3:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level)

    meter = EnergyMeter()
    meter.load_config(args.config)
    meter.initialize()
    meter.run()
