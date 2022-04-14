#!/usr/bin/env python3
import argparse
import dataclasses
import datetime
from functools import partial
from inspect import ismethod
import threading
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

import yaml

from aquisition import Channel
from displays import Display, DisplayList
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


class MqttMessagePayload(NamedTuple):
    name: str
    value: float
    unit: str


class MqttMessageTemplate(NamedTuple):
    topic: str
    payload: str


class EnergyMeter:
    logger = logging.getLogger("EnergyMeter")
    reader_thread: Optional[threading.Thread] = None

    def load_config(self, config_path: str):
        self.logger.debug(f"reading config from: {config_path}")
        with open(config_path) as config_file:
            config = yaml.load(config_file, yaml.Loader)

        self.logger.debug(f"read following config: {config}")

        try:
            self.mqtt_host = config["mqtt"]["host"]
            self.mqtt_port = config["mqtt"]["port"]
        except KeyError:
            raise AttributeError(
                f"you need to specify mqtt host and port in the config file"
            )

        self.mqtt_message_templates: List[MqttMessageTemplate] = []
        for message_config in config["mqtt"]["messages"]:
            self.mqtt_message_templates.append(
                MqttMessageTemplate(message_config["topic"], message_config["payload"])
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

        self.display_list = DisplayList()
        for display_config in config.get("displays", []):
            display = Display.from_config(**display_config)
            self.display_list.append(display)

    def initialize(self):
        display_port = i2c(port=1, address=self.display_address)
        self.display = ssd1306(display_port)

        self.adc = ADC(*self.adc_addresses)

        self.mqtt_client = MQTTClient()
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        self.mqtt_client.loop_start()

    def read_channels(self):
        while not self.should_stop.is_set():
            start_read = time.time()
            reading_map: Dict[Channel, float] = {}
            for channel in self.channels:
                channel_value = channel.read(self.adc)
                self.logger.debug(
                    f"new measurement from channel {channel.name}: \t{channel_value:2.3f} {channel.unit}"
                )
                reading_map[channel] = channel_value

                reading_message = MqttMessagePayload(
                    channel.name, channel_value, channel.unit
                )
                self.publish_mqtt_messages(reading_message)

            self.energy_statistics.add_reading(reading_map)

            # also publish a packet for the live power currently consumed
            live_power = self.energy_statistics.live_power()
            power_message = MqttMessagePayload("live_consumption", live_power, "W")
            self.publish_mqtt_messages(power_message)

            # also publish a packet for the daily power consumption
            daily_power = self.energy_statistics.daily_power()
            power_message = MqttMessagePayload("daily_consumption", daily_power, "Wh")
            self.publish_mqtt_messages(power_message)

            read_time = time.time() - start_read
            self.logger.info(
                f"Sampled {len(self.channels)} channels in {read_time} seconds"
            )
            if read_time < self.time_between_reads:
                # make sure to sample at a maximum every time_between_reads seconds
                self.should_stop.wait(self.time_between_reads - read_time)
            else:
                self.logger.warning(
                    f"Reading took more than {self.time_between_reads} seconds. It took {read_time} seconds"
                )

    def publish_mqtt_messages(self, measurement: MqttMessagePayload):
        for template in self.mqtt_message_templates:
            mqtt_topic = template.topic.format(**measurement._asdict())
            mqtt_payload = template.payload.format(**measurement._asdict())
            self.mqtt_client.publish(mqtt_topic, mqtt_payload)

    def update_display(self):
        current_display = self.display_list.get_current_display()

        with canvas(self.display) as draw:
            current_display.draw(canvas=draw, statistics=self.energy_statistics)

    def supervise_reader_thread(self):
        """
        make sure the reader thread exists and is running
        """
        if self.reader_thread is None or not self.reader_thread.is_alive():
            self.reader_thread = threading.Thread(target=self.read_channels)
            self.reader_thread.start()

    def run(self):
        self.should_stop = threading.Event()
        self.should_stop.clear()

        try:
            while not self.should_stop.is_set():
                self.supervise_reader_thread()
                self.update_display()
                # update the display with 1 fps max
                self.should_stop.wait(1)
        except KeyboardInterrupt:
            logging.info("shutdown signal received, stopping threads...")
            self.should_stop.set()
            self.mqtt_client.loop_stop()
            self.reader_thread.join()


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
