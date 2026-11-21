numbers = [1, 2, 3, 4, 5, 6]
even = filter(lambda n: n % 2 == 0, numbers)
say(list(map(lambda n: n * n, even)))
