for i in range(3):
    step(1)
    if item_here() == "banana":
        say("yum")
    elif item_here() == "coconut":
        say("crack")
    else:
        say("hmm")
