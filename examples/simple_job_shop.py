from frost_sheet.core.base import Task, Job, Machine, _generate_unique_task_ids
from frost_sheet.generator.instance_generator import InstanceGenerator
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.visualization.gantt import plot_gantt_chart

def test():
    # Create some machines
    machine1 = Machine(machine_id="1", name="Machine 1", capabilities=["cutting", "welding"])
    machine2 = Machine(machine_id="2", name="Machine 2", capabilities=["painting"])
    machine3 = Machine(machine_id="3", name="Machine 3", capabilities=["assembly"])

    # Create some tasks 
    task1 = Task(task_id="1", name="Task 1", processing_time=5, dependencies=[], requires=["cutting"], machines=["1"], start_time=1)
    task2 = Task(task_id="2", name="Task 2", processing_time=3, dependencies=["1"], requires=["welding"], machines=["1"], start_time=2)
    task3 = Task(task_id="3", name="Task 3", processing_time=4, dependencies=["1"], requires=["painting"], machines=["2"], start_time=3)
    task4 = Task(task_id="4", name="Task 4", processing_time=2, dependencies=["2", "3"], requires=["assembly"], machines=["3"], start_time=6)

    # Create a job
    job = Job(job_id="1", name="Job 1", tasks=[task4, task3, task2, task1])

    # Print the job details
    print(f"Job ID: {job.job_id}, Name: {job.name}, Priority: {job.priority}")
    print(f"Job Tasks: {job.tasks}")
    print(f"Job Start Time: {job.start_time}, End Time: {job.end_time}")

    task1.start_time = 2
    task1.end_time = task1.start_time + task1.processing_time

    job = _generate_unique_task_ids([job])[0]

    print(f"Job ID: {job.job_id}, Name: {job.name}, Priority: {job.priority}")
    print(f"Job Tasks: {job.tasks}")
    print(f"Job Start Time: {job.start_time}, End Time: {job.end_time}")

def main():
    generator = InstanceGenerator()
    jobs, machines = generator.create_instance()
    machine_dict = {m.machine_id: m for m in machines}

    for job in jobs:
        print(f"Generated Job: {job.name} with ID: {job.job_id}")
        for task in job.tasks:
            print(f"|-->Task: {task.name} with ID: {task.task_id}, Processing Time: {task.processing_time}, Requires: {task.requires}, Dependencies: {task.dependencies}")
    for machine in machines:
        print(f"Generated Machine: {machine.name} with ID: {machine.machine_id} and capabilities: {machine.capabilities}")

    solver = DummySolver(
        tasks=[t for j in jobs for t in j.tasks],
        machines=machines
    )

    schedule = solver.schedule()
    for job in jobs:
        print(f"Job {job.name} schedule:")
        for task in job.tasks:
            for m, tasks in schedule.machine_schedule.items():
                for t in tasks:
                    if t.task == task:
                        print(f"|--> Task {task.name} starts at {t.start_time} and ends at {t.end_time} on Machine {machine_dict[m].name}")

    plot_gantt_chart(schedule)

if __name__ == "__main__":
    main()