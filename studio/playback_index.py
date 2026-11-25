"""Indexed subtitle intervals for playback and a small timeline viewport."""
from bisect import bisect_left, bisect_right


class IntervalIndex:
    def __init__(self, cues, end=None):
        self.source = cues
        self.items = tuple(sorted(cues, key=lambda c: c.start))
        self.starts = tuple(c.start for c in self.items)
        self.by_id = {cue.id: cue for cue in self.items}
        size = 1
        while size < len(self.items):size *= 2
        self.size = size
        self.maximum = [float('-inf')] * (2 * size)
        for i, cue in enumerate(self.items):
            self.maximum[size + i] = end(cue) if end else cue.end
        for i in range(size - 1, 0, -1):
            self.maximum[i] = max(self.maximum[i * 2], self.maximum[i * 2 + 1])

    def intersect(self, lo, hi):
        """Return intervals touching a range, including old long overlapping cues."""
        stop = bisect_right(self.starts, hi)
        if not stop:return []
        result = []
        stack = [(1, 0, self.size)]
        while stack:
            node, left, right = stack.pop()
            if left >= stop or self.maximum[node] < lo:continue
            if right - left == 1:
                result.append(self.items[left])
                continue
            mid = (left + right) // 2
            stack.append((node * 2 + 1, mid, right))
            stack.append((node * 2, left, mid))
        return result

    def active(self, time):
        return [cue for cue in self.intersect(time, time) if cue.start <= time < cue.end]


def indexed_snap(value, points, tolerance):
    i = bisect_left(points, value)
    nearby = points[max(0, i-1):i+1]
    nearest = min(nearby, key=lambda t: abs(t-value), default=value)
    return nearest if abs(nearest-value) <= tolerance else value
