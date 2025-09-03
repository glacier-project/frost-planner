# Changelog

## 0.2.1 - 2025-09-03

- [8af6469] refactor(solver): centralize pre-computation in BaseSolver
- [5d1a667] refactor(examples): rename example scripts for clarity
- [8a74b6e] feat(examples): add runtime measurement to simple_job_shop.py
- [cd9fd51] feat(solver): implement genetic algorithm solver and optimize performance
- [b43275e] fix(solver): handle immutable job/task objects in stochastic solver
- [f284106] refactor(core): improve schedule validation and task retrieval
- [d21fae9] test(schedule): add comprehensive tests for schedule module
- [f3e8823] feat(core): make Task and Job models hashable and test _sort_tasks
- [3ac3e9e] refactor(core): make name attribute mandatory for Task, Job, and Machine
- [390bf14] test(metrics): add comprehensive tests for metrics module
- [6b6ba81] refactor(solver): improve code reusability and error handling

## 0.2.0 - 2025-09-03

- [477ac0c] refactor(generator): Explicitly initialize all InstanceConfiguration parameters
- [043c9ea] refactor(instance-handling): Standardize JSON loading/saving and refine CLI output
- [5b3ddee] documentation: Update README.md with installation, example, and documentation details
- [ef79d8f] chore: Relocate generated instances to data directory and cleanup resources
- [2f989a4] style(generator): Ensure dump_configuration lines are below 80 chars
- [6e5229d] style(visualization): Use custom print functions from utils
- [0fc9ab8] feature(utils): Add crule function for printing rules
- [f98f4f4] refactor(core): Rename job_id to id and freeze base models
- [4a828a3] refactor(solver): Adapt solver to use SchedulingInstance.get_suitable_machines and other fixes
- [22dc094] refactor(base, solver): Remove machines from Task and move get_suitable_machines to SchedulingInstance
- [69756e6] refactor(schedule): Add Schedule modification methods
- [3825a33] style(base): Remove extra newlines in frost_sheet/core/base.py
- [6518c63] fix(tests): Provide configuration to InstanceGenerator in test_dummy_solver
- [cadb4e6] fix(solver): Remove Task.start_time/end_time usage in _get_machine_intervals_for_task
- [54f1691] refactor(examples, metrics): Use Schedule job time queries
- [cbb293a] feat(schedule): Add job time query methods to Schedule
- [f60937e] refactor(base): Remove scheduled time attributes from Task and Job definitions
- [49b95cf] feat(metrics): Implement job-level metrics and display in simple_job_shop.py
- [746eb83] feature(job): Add due_date to Job and instance generation
- [43656b2] feature(visualization): Add instance visualization with DOT export
- [7d51136] refactor(examples): Sort tasks by start time in simple_job_shop.py output

## 0.1.0 - 2025-09-02

- [f6b9cc3] chore(resources): update generated instances
- [84ab40c] refactor(generator): improve instance generation readability and documentation
- [7709066] fix(solver): prevent task overlaps in _schedule_by_order
- [438e848] feat(generator): improve instance generation for multi-capability tasks
- [328f749] fix(solver): resolve capability and overlap issues in DummySolver
- [7c468f6] refactor(core, generator): add task mapping and refine type hints
- [c02dee8] style(docs): format README.md
- [0987c4f] feat(examples): enhance simple_job_shop example
- [4fa1b2d] refactor(core): reorganize base module and update type hints
- [404e717] refactor(core): move schedule validation to dedicated module
- [bbf57db] build(deps): add rich dependency
- [ad50ee5] feat(examples): update examples for refactored core and validation
- [83d2f1b] refactor(visualization): adapt gantt chart to new schedule structure
- [4c30753] refactor(solver): adapt to new ID and Machine object usage
- [59230f8] refactor(generator): update instance generation for new ID and naming conventions
- [62653c4] refactor(core): improve data model and add schedule validation
- [e719d04] refactor(solver): Adapt solver to use machine travel times and improve readability
- [e006d5c] feature(generator): Add support for generating instances with machine travel times
- [0a085bd] refactor(core): Update SchedulingInstance and Schedule data models

## 0.0.1

- [203721e] fix: README.md
- [2f0ceda] feat: add StochasticSolver and update examples
- [be11ae5] feat: add new scheduling instances and StochasticSolver draft.
- [937ac75] feat: add DummySolver.
