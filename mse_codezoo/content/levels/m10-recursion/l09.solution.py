def total(logs):
    if not logs:
        return 0
    return logs[0] + total(logs[1:])


say(total([2, 3, 4]))
