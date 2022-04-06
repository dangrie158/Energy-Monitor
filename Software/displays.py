import dataclasses
import datetime
from typing import List, Optional

from PIL import ImageDraw, ImageFont

from energy_stats import EnergyStatistics


@dataclasses.dataclass
class Display:

    title: str
    display_time: int = 3
    channel_name: Optional[str] = None

    big_font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 25)
    normal_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 11)
    small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 8)
    extrasmall_font = ImageFont.truetype("DejaVuSans.ttf", 8)

    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        canvas.rectangle(
            (0, 0, canvas.im.size[0] - 1, canvas.im.size[1] - 1),
            outline="white",
            fill="black",
        )
        self.draw_centered_string(canvas, 2, self.title, self.normal_font)

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
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 8)

        super().draw(canvas, statistics)

        total_power = statistics.daily_power(self.channel_name)
        unit = "Wh"
        if total_power > 9999:
            total_power /= 1000
            unit = "kWh"
        total_power_string = f"{total_power:04.2f}"
        self.draw_centered_string(canvas, 20, total_power_string, big_font)
        self.draw_centered_string(canvas, 50, unit, small_font)


@dataclasses.dataclass
class CurrentPower(Display):
    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        super().draw(canvas, statistics)

        total_power = statistics.live_power(self.channel_name)
        unit = "W"
        if total_power > 9999:
            total_power /= 1000
            unit = "kW"
        total_power_string = f"{total_power:04.2f}"
        self.draw_centered_string(canvas, 20, total_power_string, self.big_font)
        self.draw_centered_string(canvas, 50, unit, self.small_font)


@dataclasses.dataclass
class PowerHistory(Display):
    num_bins: int = 24

    def draw(self, canvas: ImageDraw, statistics: EnergyStatistics):
        super().draw(canvas, statistics)

        chart_padding_x = 3
        chart_padding_y = 18
        chart_height = 35
        chart_width = canvas.im.size[0] - (2 * chart_padding_x)

        power_history = statistics.power_history(self.num_bins, self.channel_name)
        bin_width = chart_width / self.num_bins

        max_value = max(power_history)
        if max_value == 0:
            # we don't yet have enough data for any reasonable chart
            self.draw_centered_string(canvas, 30, "no data", self.normal_font)
            return

        # draw the bars as solid filled rectangles
        for bin_number, bin in enumerate(power_history):
            bar_height = int(round((bin / max_value) * chart_height))
            bar_start = (
                chart_padding_x + (bin_width * bin_number) + 1,
                chart_padding_y + (chart_height - bar_height),
            )
            bar_end = (
                chart_padding_x + (bin_width * (bin_number + 1)) - 1,
                chart_padding_y + chart_height,
            )
            canvas.rectangle((*bar_start, *bar_end), fill="white")

        # draw with black through the bars to make them look like blocks
        cross_line_distance = 2
        for line_index in range(1, (chart_height // cross_line_distance) + 1):
            line_height = (
                chart_padding_y
                + (cross_line_distance * line_index)
                - (cross_line_distance // 2)
            )
            canvas.line(
                (
                    chart_padding_x,
                    line_height,
                    canvas.im.size[0] - chart_padding_x,
                    line_height,
                ),
                fill="black",
            )

        # draw an hour-legend on the bottom marking every 4th hour
        for hour in range(0, 24, 4):
            label_position = (
                chart_padding_x + (chart_width / 24 * hour),
                chart_padding_y + chart_height + 1,
            )
            canvas.text(
                label_position, f"{hour:02d}", font=self.extrasmall_font, fill="white"
            )


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
