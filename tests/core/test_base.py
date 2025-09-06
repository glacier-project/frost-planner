import pytest

from frost_sheet.core.base import Task, _sort_tasks


def test_sort_tasks_empty_list() -> None:
    """Test sorting an empty list of tasks."""
    tasks: list[Task] = []
    sorted_tasks = _sort_tasks(tasks)
    assert sorted_tasks == []


def test_sort_tasks_single_task_no_dependencies() -> None:
    """Test sorting a single task with no dependencies."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    tasks = [task]
    sorted_tasks = _sort_tasks(tasks)
    assert sorted_tasks == [task]


def test_sort_tasks_multiple_tasks_no_dependencies() -> None:
    """Test sorting multiple tasks with no dependencies."""
    task1 = Task(id="T1", name="Task 1", processing_time=10)
    task2 = Task(id="T2", name="Task 2", processing_time=10)
    tasks = [task1, task2]
    sorted_tasks = _sort_tasks(tasks)
    # Order might vary, but both should be present and valid
    assert len(sorted_tasks) == 2
    assert task1 in sorted_tasks
    assert task2 in sorted_tasks


def test_sort_tasks_linear_dependencies() -> None:
    """Test sorting tasks with linear dependencies (A -> B -> C)."""
    task_c = Task(id="T3", name="Task C", processing_time=10, dependencies=["T2"])
    task_b = Task(id="T2", name="Task B", processing_time=10, dependencies=["T1"])
    task_a = Task(id="T1", name="Task A", processing_time=10)
    tasks = [task_c, task_b, task_a]
    sorted_tasks = _sort_tasks(tasks)
    assert sorted_tasks == [task_a, task_b, task_c]


def test_sort_tasks_branching_dependencies() -> None:
    """Test sorting tasks with branching dependencies (A -> B, A -> C)."""
    task_b = Task(id="T2", name="Task B", processing_time=10, dependencies=["T1"])
    task_c = Task(id="T3", name="Task C", processing_time=10, dependencies=["T1"])
    task_a = Task(id="T1", name="Task A", processing_time=10)
    tasks = [task_b, task_c, task_a]
    sorted_tasks = _sort_tasks(tasks)
    assert sorted_tasks[0] == task_a
    assert {task_b, task_c} == set(sorted_tasks[1:])  # Order of B and C can vary


def test_sort_tasks_converging_dependencies() -> None:
    """Test sorting tasks with converging dependencies (A -> C, B -> C)."""
    task_c = Task(id="T3", name="Task C", processing_time=10, dependencies=["T1", "T2"])
    task_a = Task(id="T1", name="Task A", processing_time=10)
    task_b = Task(id="T2", name="Task B", processing_time=10)
    tasks = [task_c, task_a, task_b]
    sorted_tasks = _sort_tasks(tasks)
    assert sorted_tasks[-1] == task_c
    assert {task_a, task_b} == set(sorted_tasks[:-1])  # Order of A and B can vary


def test_sort_tasks_complex_dag() -> None:
    """Test sorting a more complex DAG."""
    t1 = Task(id="T1", name="T1", processing_time=2)
    t2 = Task(id="T2", name="T2", processing_time=2, dependencies=["T1"])
    t3 = Task(id="T3", name="T3", processing_time=2, dependencies=["T1"])
    t4 = Task(id="T4", name="T4", processing_time=2, dependencies=["T2", "T3"])
    t5 = Task(id="T5", name="T5", processing_time=2, dependencies=["T4"])
    tasks = [t5, t4, t3, t2, t1]
    sorted_tasks = _sort_tasks(tasks)
    # T1 must be first, T5 must be last. T2 and T3 can be in any order after T1.
    # T4 must be after T2 and T3.
    assert sorted_tasks[0] == t1
    assert sorted_tasks[-1] == t5
    assert sorted_tasks.index(t4) > sorted_tasks.index(t2)
    assert sorted_tasks.index(t4) > sorted_tasks.index(t3)


def test_sort_tasks_cycle_detection() -> None:
    """
    Test that _sort_tasks detects and raises ValueError for cycles.
    """
    task_a = Task(id="T1", name="Task A", processing_time=10, dependencies=["T2"])
    task_b = Task(id="T2", name="Task B", processing_time=10, dependencies=["T1"])
    tasks = [task_a, task_b]
    with pytest.raises(
        ValueError,
        match="Graph has no tasks without dependencies, indicating a cycle "
        "or an invalid DAG.",
    ):
        _sort_tasks(tasks)


def test_sort_tasks_no_initial_dependencies() -> None:
    """
    Test that _sort_tasks raises ValueError if no task has initial dependencies
    (not a DAG).
    """
    # This scenario implies a graph where all nodes have incoming edges, which
    # is a cycle or disconnected components that cannot be started.
    task_a = Task(id="T1", name="Task A", processing_time=10, dependencies=["T2"])
    task_b = Task(id="T2", name="Task B", processing_time=10, dependencies=["T3"])
    task_c = Task(id="T3", name="Task C", processing_time=10, dependencies=["T1"])
    tasks = [task_a, task_b, task_c]
    with pytest.raises(
        ValueError,
        match="Graph has no tasks without dependencies, indicating a cycle "
        "or an invalid DAG.",
    ):
        _sort_tasks(tasks)


def test_sort_tasks_disconnected_components() -> None:
    """Test sorting tasks with disconnected components."""
    task_a = Task(id="T1", name="Task A", processing_time=10)
    task_b = Task(id="T2", name="Task B", processing_time=10)
    task_c = Task(id="T3", name="Task C", processing_time=10, dependencies=["T1"])
    task_d = Task(id="T4", name="Task D", processing_time=10, dependencies=["T2"])
    tasks = [task_c, task_d, task_a, task_b]
    sorted_tasks = _sort_tasks(tasks)
    # A and B must come before C and D respectively. The relative order of A/B
    # and C/D can vary.
    assert len(sorted_tasks) == 4
    assert sorted_tasks.index(task_c) > sorted_tasks.index(task_a)
    assert sorted_tasks.index(task_d) > sorted_tasks.index(task_b)
