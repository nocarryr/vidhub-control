import random
import string

def random_string(num_chars=8):
    return ''.join((random.choice(string.printable) for i in range(num_chars)))

def get_random_values(n, value_type=None):
    if value_type is None:
        value_type = random.choice([str, int, float])
    if value_type is str:
        s = set((random_string() for i in range(n)))
        while len(s) < n:
            s.add(random_string())
    elif value_type is int:
        maxint = 100
        if n > maxint:
            maxint = n * 4
        s = set((random.randint(0, maxint) for i in range(n)))
        while len(s) < n:
            s.add(random.randint(0, maxint))
    elif value_type is float:
        s = set((random.random() * 100. for i in range(n)))
        while len(s) < n:
            s.add(random.random() * 100.)
    return s
