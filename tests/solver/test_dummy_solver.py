import pytest

from frost_sheet.core.base import SchedulingInstance
from frost_sheet.generator.instance_generator import (
    InstanceConfiguration,
    InstanceGenerator,
)
from frost_sheet.solver.dummy_solver import DummySolver


@pytest.mark.parametrize(
    "instance",
    [
        InstanceGenerator().create_instance(configuration=InstanceConfiguration())
        for _ in range(3)
    ],
)
class TestDummySolver:
    def test_schedule(self, instance: SchedulingInstance) -> None:
        solver = DummySolver(instance=instance)

        schedule = solver.schedule()

        assert schedule is not None
