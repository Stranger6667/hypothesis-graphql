from hypothesis import strategies as st


class ViolationTracker:
    """Tracks violation injection state to guarantee at least one per query."""

    def __init__(self) -> None:
        self.has_injected = False

    def should_inject(self, draw: st.DrawFn) -> bool:
        """Decide whether to inject a violation."""
        if self.has_injected:
            return draw(st.booleans())
        draw(st.just(True))
        return True

    def mark_injected(self) -> None:
        """Mark that a violation was actually injected."""
        self.has_injected = True
