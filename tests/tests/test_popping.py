from collections import deque
from itertools import starmap, repeat
from collections.abc import Iterable
from typing import Any

import pytest


def pop_enumerate(n : int) -> Iterable[Any]:
    x = deque([i for i in range(2560)])
    return [x.popleft() for _ in range(n)]

def pop_starmap(n : int) -> Iterable[Any]:
    x = deque([i for i in range(2560)])
    return list(starmap(x.popleft, repeat((), n)))

@pytest.mark.parametrize("n", [1, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048])
def test_deque_popleft_array_func(n, benchmark):
    vals = benchmark(pop_enumerate, n)
    assert len(vals) == n

@pytest.mark.parametrize("n", [1, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048])
def test_deque_starmap_pop(n, benchmark):
    vals = benchmark(pop_starmap, n)
    assert len(vals) == n