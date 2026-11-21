def dance(template):
    parts = []
    for part in template:
        if isinstance(part, str):
            parts.append(part)
        elif "wasp" in str(part.value):
            parts.append("???")
        else:
            parts.append(str(part.value))
    return "".join(parts)

where = "left of the oak"
say(dance(t"Flowers are {where}!"))
sneaky = "wasp nest"
say(dance(t"Go to the {sneaky}"))
