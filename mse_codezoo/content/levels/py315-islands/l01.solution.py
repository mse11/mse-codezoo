blueprint = frozendict(oak=2, pine=1)
try:
    blueprint["oak"] = 5
except TypeError:
    say("the blueprint can't change")
say(blueprint["oak"])
