for text in ["2", "two", "1"]:
    try:
        step(int(text))
        grab()
    except ValueError:
        say("What is " + text + "?")
