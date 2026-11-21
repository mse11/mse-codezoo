errors = ExceptionGroup("hive", [ValueError("rain"), KeyError("wasp")])
try:
    raise errors
except* ValueError:
    say("rain handled")
except* KeyError:
    say("wasp handled")
