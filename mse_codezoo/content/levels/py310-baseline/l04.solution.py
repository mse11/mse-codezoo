with (
    open("basket.txt", "w") as basket,
    open("ladder.txt", "w") as ladder,
):
    basket.write("3 bananas")
    ladder.write("put back")
