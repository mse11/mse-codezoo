logs = [("oak", 3), ("pine", 1), ("birch", 2)]
shortest_first = sorted(logs, key=lambda log: log[1])
say([name for name, size in shortest_first])
