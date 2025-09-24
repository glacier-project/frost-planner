import pytest

from frost_sheet.core.base import SchedulingInstance, TaskStatus
from frost_sheet.generator.instance_generator import InstanceConfiguration, InstanceGenerator
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.genetic_solver import GeneticAlgorithmSolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.executor.static_executor import StaticExecutor
from frost_sheet.solver.base_solver import BaseSolver

@pytest.mark.parametrize(
    "instance",
    [
        InstanceGenerator().create_instance(configuration=InstanceConfiguration())
        for _ in range(3)
    ],

)
@pytest.mark.parametrize(
    "solver",
    [
        # GeneticAlgorithmSolver,
        DummySolver,
        # StochasticSolver
    ],
)
class TestStaticExecutor:

    def test_executor_ctor(self, instance: SchedulingInstance, solver: type[BaseSolver]):
        executor = StaticExecutor(solver=solver(instance=instance))
        all_tasks = [t for job in instance.jobs for t in job.tasks]

        executor = StaticExecutor(solver=solver(instance=instance))
        next_tasks = executor.next_ready_tasks()

        assert len(next_tasks) > 0 
        assert len(next_tasks) <= len(all_tasks)

    def test_run_all_tasks(self, instance: SchedulingInstance, solver: type[BaseSolver]):
        
        executor = StaticExecutor(solver=solver(instance=instance))
        all_tasks = [t for job in instance.jobs for t in job.tasks]

        all_scheduled_tasks = []
        while True:
            next_tasks = executor.next_ready_tasks()
            if not next_tasks:
                break
            for scheduled_task, machine in next_tasks:
                all_scheduled_tasks.append(scheduled_task)
                executor.task_completed(scheduled_task)
            executor.update_task_status()

        assert len(all_scheduled_tasks) == len(all_tasks)
        assert all(t.status == TaskStatus.COMPLETED for t in all_tasks)