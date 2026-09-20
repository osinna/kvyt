from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    owner: str


REGISTRY: dict[str, ScenarioSpec] = {
    spec.name: spec
    for spec in (
        ScenarioSpec("silent-500", "gateway"),
        ScenarioSpec("pagination-off-by-one", "catalog"),
        ScenarioSpec("contract-drift", "catalog"),
        ScenarioSpec("bola-booking", "booking"),
        ScenarioSpec("mass-assignment", "identity"),
        ScenarioSpec("no-rate-limit", "gateway"),
        ScenarioSpec("hold-never-expires", "booking"),
        ScenarioSpec("double-booking", "booking"),
        ScenarioSpec("webhook-replay", "payment"),
        ScenarioSpec("stale-cache", "catalog"),
    )
}


class UnknownScenarioError(RuntimeError):
    def __init__(self, name: str) -> None:
        known = ", ".join(sorted(REGISTRY))
        super().__init__(
            f"Unknown BUG_SCENARIO '{name}'. Known scenarios: {known}"
        )
        self.name = name


class ScenarioSet:
    """Scenarios active for one service instance."""

    def __init__(self, names: list[str], owner: str) -> None:
        self._own: set[str] = set()
        for name in names:
            spec = REGISTRY.get(name)
            if spec is None:
                raise UnknownScenarioError(name)
            if spec.owner == owner:
                self._own.add(name)

    def active(self, name: str) -> bool:
        return name in self._own

    def as_list(self) -> list[str]:
        return sorted(self._own)


def parse_scenarios(raw: str, owner: str) -> ScenarioSet:
    names = [item.strip() for item in raw.split(",") if item.strip()]
    return ScenarioSet(names, owner)
