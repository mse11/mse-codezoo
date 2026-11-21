from copy import replace
from dataclasses import dataclass

@dataclass(frozen=True)
class Route:
    start: str
    end: str

night = Route("den", "river")
day = replace(night, end="meadow")
say(night.end)
say(day.end)
