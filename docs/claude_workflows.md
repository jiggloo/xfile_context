# Workflows for Claude Code

## Documentation Updates

Documentation should reside in its most-appropriate destination. For example, engineering design decisions
should be documented in the TDD. For example, usage instructions should be documented in the README.

Overlapping documentation between the different phases should be relatively low in order to practically
minimize the effort of keeping the documentation in sync. For example, engineering design decisions should
not be documented in the PRD or the README. For example, usage instructions should not be
documented in the TDD.

Earlier phases can have higher-level description in order to allow more-concrete implementation in later
phases. For example, the PRD describes user flow as a high-level description of usage instructions
without restricting usage instructions in the README later.

Later phases can link to related documentation in earlier phases. For example, the README can link to
engineering design decisions in the TDD. Earlier phases CANNOT link to documentation in later phases.
For example, the TDD cannot link to the README because the TDD will be completed before the README is
even created.

Documentation in Github Issues should not be considered its own phase. Github Issues support the development
of documentation in the last phase. Github Sub-Issues are a special type of Github Issue that are "child"
items of other Github Issues.

## Github Issue Creation

If Claude Code creates a Github Issue with known dependencies to other Github Issues, then the dependencies
MUST be reflected in the Relationships of the Github Issue.

Claude Code MUST check the latest Github documentation to ensure that it is using the correct commands
to use the Relationships feature of Github Issues.

New Github Issues created by Claude Code MUST have the `initial` label. 

## Github Issue Initial Review

Github Issues with the `initial` label MUST be reviewed before development can start.

To complete a review, Claude Code MUST do the following:
- **Break down the issue into smaller tasks if needed.** The issue description MUST have a `Tasks` section listing
  the smaller tasks or that further breakdown was not needed.
- **Estimate the complexity of the issue in number of days of effort.** The issue description MUST have an
  `Estimated Complexity` section indicating the estimate
- **Dependencies to other Github Issues.** The dependencies MUST be reflected in Relationships of the issue
  (similar to the Github Issue Creation workflow).
- **References to relevant documentation.** The issue description MUST have a `References` section listing the
  referenced documentation.

If the estimated complexity is High (>5 days), then turn the task breakdown into Github Sub-Issues. The
sub-issues MUST have a child-parent relationship with the issue it was created for.

Once the review is completed, the `initial` label MUST be removed from the issue.

## Git Development Workflow

Development MUST be associated with a single Github Issue. If there is no associated issue, then ask the user to
find one or create one.

Development MUST NOT start if the associated Github Issue has the `initial` label. Complete the Github Issue
Initial Review workflow first so that the `initial` label is removed.

All development MUST be in a separate feature branch that is later merged into the default/main branch through
the Github pull-request (PR) process. The feature branch name must be prefixed with `issue-N-` where `N` is the issue number.
All new feature branches must be created from the latest default/main branch in Github.

After Claude Code completes its initial implementation of a Github issue, the work must be pushed to Github and
a PR created. The PR must include Github keywords that will close the issue once the PR is merged. 

The initial implementation MUST also include documentation updates. This acts as a clean
state for automated steps to be taken before human review. The automated steps must be:
1. Completion of all PR checks
2. A multi-agent review of the pull request with independent agents for each specialization:
   Code Quality, Completeness, Documentation, Security/Safety. Changes made by the agents MUST be consolidated
   into a single Git commit and pushed to the pull request. The commit message MUST include the consolidated
   review summary of the multiple agents.
3. If the PR has >200 lines added or changed, then step 2 MUST be repeated so that there are two reviews.

The multi-agent reviews MUST take into account:
- The contents of the Github Issue include comments and discussions.
- The contents of any parent Github Issue if there is a parent (including comments and discussions).
- Portions of the TDD relevant to the Github Issue
- Portions of the PRD relevant to the Github Issue

Any further agent-based work on the pull request MUST also take into account the contents of the
commit messages in the pull request's commit history.

### Versioning

The project follows semantic versioning with a pre-1.0 scheme that tracks story completion:

**Version Format**: `0.MINOR.PATCH`

- **PATCH version** (0.0.N): Incremented after each Task PR is merged
  - The PATCH number corresponds to the task number (e.g., 0.0.11 = Task 1.1 complete)
  - Story PR: A pull request that implements one of the stories defined in TDD Section 3.4

- **MINOR version** (0.1.0): Incremented when all TDD stories in Section 3.4 are complete
  - Version 0.1.0 indicates the project has met all features listed in TDD
  - This represents the minimum viable product ready for production deployment

**Version Update Process**:
1. After a Task PR is merged to the main branch, the version MUST be updated
2. Update `pyproject.toml` version field manually
3. The version update SHOULD be included in the Task PR itself before merge
   - If version update is missed, it can be corrected via a separate PR following normal Git Development Workflow
4. Version updates do NOT require their own Github Issue unless there are complications (e.g., correcting an incorrectly set version)

**Example Version Progression**:
- 0.0.1 - Task 0.1 complete
- 0.0.2 - Task 0.2 complete
- ...
- 0.0.11 - Story 1.1 complete
- ...
- 0.1.0 - All stories complete, ready for production

**Version 0.2.0 and beyond**: Features beyond the initial TDD scope will follow standard semantic versioning.
