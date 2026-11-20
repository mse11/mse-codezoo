def there_and_back(n):
    if n == 0:
        grab()
        turn_left()
        turn_left()
        return
    step(1)
    there_and_back(n - 1)
    step(1)


there_and_back(3)
