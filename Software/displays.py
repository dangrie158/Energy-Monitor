import dataclasses
import datetime
from typing import List, Optional, Tuple

from PIL import ImageDraw, ImageFont

from energy_stats import EnergyStatistics


@dataclasses.dataclass
class Display:

    title: str
    display_time: int = 3

    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        return NotImplemented

    def draw_centered_string(
        self, canvas: ImageDraw, y: int, text: str, font: ImageFont
    ):
        text_width, _ = canvas.textsize(text, font=font)
        canvas_width = canvas.im.size[0]
        canvas.text(
            (canvas_width / 2 - text_width / 2, y),
            text,
            font=font,
            fill="white",
        )

    @classmethod
    def from_config(cls, **kwargs):
        available_displays = {
            subclass.__name__: subclass for subclass in cls.__subclasses__()
        }
        try:
            display_type_name = kwargs.pop("type", "<undefined>")
            display_class = available_displays[display_type_name]
        except KeyError:
            raise AttributeError(
                f"Unknown display class: {display_type_name}. Available classes: {available_displays.keys()}"
            )

        return display_class(**kwargs)


@dataclasses.dataclass
class DailyPower(Display):
    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        big_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 25)
        normal_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 12)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 8)

        canvas.rectangle(
            (0, 0, canvas.im.size[0] - 1, canvas.im.size[1] - 1),
            outline="white",
            fill="black",
        )

        total_power = statistics.daily_power()
        unit = "Wh"
        if total_power > 9999:
            total_power /= 1000
            unit = "kWh"
        total_power_string = f"{total_power:04.2f}"
        self.draw_centered_string(canvas, 2, self.title, normal_font)
        self.draw_centered_string(canvas, 20, total_power_string, big_font)
        self.draw_centered_string(canvas, 50, unit, small_font)


@dataclasses.dataclass
class CurrentPower(Display):
    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        big_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 25)
        normal_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 12)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 8)

        canvas.rectangle(
            (0, 0, canvas.im.size[0] - 1, canvas.im.size[1] - 1),
            outline="white",
            fill="black",
        )

        total_power = statistics.live_power()
        unit = "W"
        if total_power > 9999:
            total_power /= 1000
            unit = "kW"
        total_power_string = f"{total_power:04.2f}"
        self.draw_centered_string(canvas, 2, self.title, normal_font)
        self.draw_centered_string(canvas, 20, total_power_string, big_font)
        self.draw_centered_string(canvas, 50, unit, small_font)


@dataclasses.dataclass
class PowerHistory(Display):
    num_bins: int = 20

    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        power_history = statistics.power_history(self.num_bins)
        oled_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
        canvas.rectangle(((0, 0), canvas.im.size), outline="white", fill="black")
        canvas.text((10, 10), "OLED-Display", font=oled_font, fill="white")


class DisplayList(List[Display]):
    _current_index = 0
    _current_display_active_since: Optional[datetime.datetime] = None

    def get_current_display(self):
        if len(self) == 0:
            return

        if self._current_display_active_since == None:
            self._current_display_active_since = datetime.datetime.now()

        # check if we need to go to the next display
        current_display = self[self._current_index]
        if (
            self._current_display_active_since
            + datetime.timedelta(seconds=current_display.display_time)
            < datetime.datetime.now()
        ):
            self._current_index += 1
            self._current_index %= len(self)
            current_display = self[self._current_index]
            self._current_display_active_since = datetime.datetime.now()

        return self[self._current_index]
