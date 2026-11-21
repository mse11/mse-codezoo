def weigh(log: int | float) -> str:
    if not isinstance(log, int | float):
        raise TypeError("not a log")
    return f"{log} kg"

say(weigh(2.5))
try:
    weigh("oak")
except TypeError:
    say("the scale says no")
