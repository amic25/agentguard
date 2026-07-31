# GitLab CI

Add AgentGuard as a GitLab CI job to scan the repository, enforce a severity
threshold, and retain a machine-readable report.

## Example job

Copy [`gitlab-ci.yml`](gitlab-ci.yml) into your project's `.gitlab-ci.yml`, or
merge the `agentguard` job into an existing pipeline:

```yaml
image: python:3.13-slim

stages:
  - security

agentguard:
  stage: security
  before_script:
    - python -m pip install --disable-pip-version-check agentguard-sast
  script:
    - agentguard scan . --format json --output agentguard-report.json --fail-on high
  artifacts:
    when: always
    paths:
      - agentguard-report.json
    expire_in: 1 week
```

The job installs AgentGuard from PyPI, scans the checkout, and writes the JSON
report to `agentguard-report.json`. `artifacts.when: always` retains the report
even when the severity threshold fails the job. Adjust `expire_in` to match your
project's retention policy.

## Threshold and exit codes

`--fail-on high` exits with status `1` when a High or Critical finding is
present, which makes the GitLab job fail. Use another severity (`critical`,
`medium`, or `low`) to change the gate, or `--fail-on none` to publish the
report without failing on findings.

AgentGuard uses these exit codes:

- `0`: the scan completed and no finding reached the configured threshold;
- `1`: at least one finding reached the threshold;
- `2`: the scan could not complete, for example because of invalid arguments or
  an unreadable target.

## Report limitations

The JSON file is an ordinary GitLab job artifact for downloading or processing
in later jobs. AgentGuard does not currently emit GitLab's native SAST report
schema, so this example does not populate GitLab security dashboards or merge
request security widgets.
