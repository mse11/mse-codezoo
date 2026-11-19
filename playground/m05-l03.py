# every world has a different row: look before you grab
for i in range(5):
    step(1)
    if item_here() == "banana":
        grab()
