from contextlib import contextmanager
import time
from threading import Thread, Event
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw


class DummyAdc:
    def __init__(self, addr1, addr2, bits=18):
        self.set_bit_rate(bits)

    def set_bit_rate(self, bitrate):
        self.bitrate = bitrate

    def set_pga(self, pga):
        self.pga = pga

    def read_raw(self, channel):
        if self.bitrate == 16:
            time.sleep(1 / 15)
        elif self.bitrate == 12:
            time.sleep(1 / 230)
        else:
            raise ValueError("unknown bitrate")
        if np.random.randint(0, 100) == 0:
            time.sleep(0.1)
        return np.random.normal(2**self.bitrate / 2, 2**self.bitrate / 2)


class i2c:
    def __init__(self, port, address):
        pass


class ssd1306:
    def __init__(self, i2c_port: i2c):
        self.bounding_box = (0, 0, 127, 63)

    @property
    def width(self):
        return (self.bounding_box[2] - self.bounding_box[0]) + 1

    @property
    def height(self):
        return (self.bounding_box[3] - self.bounding_box[1]) + 1

    @property
    def size(self):
        return (self.width, self.height)


cv2.namedWindow("display", cv2.WINDOW_KEEPRATIO | cv2.WINDOW_AUTOSIZE)
cv2.setWindowProperty("display", cv2.WND_PROP_TOPMOST, 1)


@contextmanager
def canvas(display: ssd1306):
    _image = Image.new("RGB", display.size, (0, 255, 0))
    yield ImageDraw.Draw(_image)
    _image = _image.resize(
        (display.size[0] * 2, display.size[1] * 2), resample=Image.NEAREST
    )
    cv2.imshow(
        "display",
        np.asarray(_image.getdata())
        .reshape((display.size[1] * 2, display.size[0] * 2, 3))
        .astype(np.uint8),
    )
    cv2.waitKey(1)


import logging


class MQTTClient:
    logger = logging.getLogger("MQTT Client")
    worker_thread: Optional[Thread] = None

    def connect(self, host: str, port: int):
        pass

    def publish(self, topic: str, payload: str):
        self.logger.debug(f"publishing message with topic {topic}: {payload}")

    def loop(self):
        while not self._thread_terminate.is_set():
            time.sleep(1)

    def loop_start(self):
        if self.worker_thread is not None:
            raise AssertionError("Loop already running")

        self._thread_terminate = Event()
        self.worker_thread = Thread(target=self.loop)
        self.worker_thread.start()

    def loop_stop(self):
        if self.worker_thread is None or not self.worker_thread.is_alive():
            raise AssertionError("Loop is not running")

        self._thread_terminate.set()
        self.worker_thread.join()
        self.worker_thread = None
