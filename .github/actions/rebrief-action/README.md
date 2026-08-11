# rebrief GitHub Action

Composite action that runs `rebrief scan` and posts or updates a summarized report as a pull request comment.

## Usage

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: ./.github/actions/rebrief-action
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          working-directory: .
```

Use `fetch-depth: 0` so git history is available for timeline and hotspot analysis.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | No | `${{ github.token }}` | Token used to create or update PR comments |
| `working-directory` | No | `.` | Directory passed to `rebrief scan` |
| `post-comment` | No | `true` | Post or update a PR comment with the report summary |
| `only-on-risk` | No | `false` | Only post when WARNING or CRITICAL risks are found |
| `skip-drafts` | No | `true` | Skip the action on draft pull requests |
| `python-version` | No | `3.12` | Python version for `setup-python` |
| `rebrief-version` | No | `""` | Optional pip pin (for example `rebrief==0.1.4`) |
| `use-local-package` | No | `false` | Install rebrief from the checked-out repo instead of PyPI |

## Outputs

| Output | Description |
|--------|-------------|
| `report-path` | Path to the generated `REBRIEF.md` file |
| `has-risks` | `true` when WARNING or CRITICAL findings exist |
| `truncated` | `true` when the PR comment was truncated for GitHub's size limit |
| `skipped` | `true` when execution was skipped because the PR is a draft |

## Workflow examples

### Label-gated (recommended)

Runs only when a PR has the `rebrief` label:

```yaml
name: rebrief

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled]

permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    if: contains(github.event.pull_request.labels.*.name, 'rebrief')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: ./.github/actions/rebrief-action
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          only-on-risk: false
          skip-drafts: true
```

Add the `rebrief` label to a pull request to trigger a scan in this repository.

### Always-on

```yaml
name: rebrief

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: ./.github/actions/rebrief-action
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          skip-drafts: true
```

### Only comment when risks are found

```yaml
- uses: ./.github/actions/rebrief-action
  with:
    only-on-risk: true
```

When `only-on-risk` is `true`, the action still runs the scan but skips posting a comment if both the CRITICAL and WARNING sections contain only `- None detected.`

## PR comment behavior

- Comments are tagged with `<!-- rebrief-ci-report -->` for idempotent upserts
- Existing tagged comments are updated instead of creating duplicates
- The posted summary includes sections 1, 4, and 5 from `REBRIEF.md` (overview, risks, checklist)
- Sections 2 and 3 are included in a collapsible `<details>` block when space allows
- Comments longer than GitHub's 65,536 character limit are truncated and the full `REBRIEF.md` is uploaded as a workflow artifact

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Comment not posted | Ensure `pull-requests: write` permission is set and `post-comment` is `true` |
| No comment on draft PR | Expected when `skip-drafts: true`; mark PR ready for review or set `skip-drafts: false` |
| Empty git timeline | Set `fetch-depth: 0` on `actions/checkout` |
| `rebrief.ci.comment` not found | Upgrade to a rebrief release that includes CI helpers, or set `use-local-package: true` |
| Permission denied on comment API | Confirm workflow `permissions` include `pull-requests: write` |
