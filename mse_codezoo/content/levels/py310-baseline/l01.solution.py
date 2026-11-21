footprints = [("paw", 1), ("boot", 9), ("paw", 4)]
for footprint in footprints:
    match footprint:
        case ("paw", size) if size > 2:
            hide()
            say("big paw: hide")
        case ("paw", _):
            say("small paw")
        case ("boot", _):
            say("run!")
