# The definitions that the jq command of the conformance cases can use
# (harness_test.go). $status is the exit status of the last lilrae command.

# envelope($command; $status): the result envelope of the CLI for $command:
# schema version 1, and ok exactly when the exit status is 0.
def envelope($command; $status):
  .command == $command and .schema_version == 1 and .ok == ($status == 0);

# doctor_counts($status): each count of a doctor result equals the number of
# checks with its status, and the exit status is 0 exactly when no check
# failed.
def doctor_counts($status):
  (reduce .checks[].status as $s ({}; .[$s] += 1)) as $tally
  | .counts as $counts
  | all("pass", "warn", "fail", "skip"; ($tally[.] // 0) == $counts[.])
    and (($tally.fail // 0) == 0) == ($status == 0);
